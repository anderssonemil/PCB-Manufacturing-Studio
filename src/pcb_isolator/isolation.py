"""Generate successive contours outside the union of retained copper."""
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import tomllib

from shapely.geometry.base import BaseGeometry
from shapely.affinity import scale


@dataclass(frozen=True)
class IsolationSettings:
    width_mm: float = 0.075
    overlap_percent: float = 33.3333
    lines: int = 5
    width_y_mm: float | None = None
    lane_spacing_mm: float | None = None
    adaptive: bool = False

    def __post_init__(self):
        if not isfinite(self.width_mm) or self.width_mm <= 0:
            raise ValueError("Laser width must be a finite positive number.")
        if not isfinite(self.overlap_percent) or not 0 <= self.overlap_percent < 100:
            raise ValueError("Overlap must be between 0 (inclusive) and 100 (exclusive).")
        for value in (self.width_y_mm,self.lane_spacing_mm):
            if value is not None and (not isfinite(value) or value<=0):raise ValueError("Directional widths and lane spacing must be positive and finite.")
        if type(self.lines) is not int or not 1 <= self.lines <= 50:
            raise ValueError("Number of isolation lines must be an integer from 1 to 50.")

    @property
    def directional(self):return self.width_y_mm is not None

    @property
    def spacing_mm(self):
        if self.lane_spacing_mm is not None:return self.lane_spacing_mm
        return self.width_mm * (1 - self.overlap_percent / 100)

    def cleared_width_mm(self, lines=None):
        count = self.lines if lines is None else lines
        return self.width_mm + (count - 1) * self.spacing_mm


def load_settings(path: Path) -> IsolationSettings:
    with Path(path).open("rb") as stream:
        config = tomllib.load(stream)
    return IsolationSettings(
        width_mm=config["laser"]["effective_width_mm"],
        overlap_percent=config["laser"]["overlap_percent"],
        lines=config["isolation"]["lines"],
        width_y_mm=config["laser"].get("width_y_mm"),
        lane_spacing_mm=config["laser"].get("lane_spacing_mm"),
        adaptive=config["laser"].get("adaptive",False),
    )


def generate_isolation(copper: BaseGeometry, settings: IsolationSettings):
    if copper.is_empty or not copper.is_valid or copper.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Isolation requires valid nonempty copper polygons.")
    # A tiny additional offset accommodates polygonal approximation of round
    # buffer joins. This protects the imported polygon geometry, not unknown
    # manufacturing variation or Gerber tessellation error.
    guard = max(0.00002, settings.width_mm * 0.0001)
    contours = []
    first=None
    if settings.directional:
        first=scale(scale(copper,xfact=2/settings.width_mm,yfact=2/settings.width_y_mm,origin=(0,0)).buffer(1,quad_segs=128),xfact=settings.width_mm/2,yfact=settings.width_y_mm/2,origin=(0,0)).buffer(guard,quad_segs=64)
    if settings.adaptive and first is not None:
        from .adaptive_isolation import plan_lanes
        from .narrow_isolation import add_narrow_fallback
        return add_narrow_fallback(copper,plan_lanes(first,settings),settings)
    for index in range(settings.lines):
        distance = settings.width_mm / 2 + index * settings.spacing_mm + guard
        # Buffer the entire union, not each pad independently: offset regions
        # merge in tight gaps instead of paths crossing neighboring copper.
        boundary = (first.buffer(index*settings.spacing_mm,quad_segs=64) if index else first).boundary if first is not None else copper.buffer(distance, quad_segs=64).boundary
        contours.append(boundary)
    return contours


def footprint_buffer(geometry,settings,guard=0):
    """Swept provisional process footprint, in fixed artwork/machine axes."""
    if not settings.directional:return geometry.buffer(settings.width_mm/2+guard,quad_segs=64)
    x,y=settings.width_mm/2,settings.width_y_mm/2
    return scale(scale(geometry,xfact=1/x,yfact=1/y,origin=(0,0)).buffer(1,quad_segs=128),xfact=x,yfact=y,origin=(0,0)).buffer(guard,quad_segs=64)


def footprint_layers(contours,settings):
    """Cache per-layer review sweeps for this immutable generated plan."""
    key=(settings.width_mm,settings.width_y_mm)
    cached=getattr(contours,'_review_sweeps',None)
    if cached is not None and cached[0]==key:return cached[1]
    areas=[footprint_buffer(shape.simplify(.0002),settings) for shape in contours]
    if hasattr(contours,'__dict__'):contours._review_sweeps=(key,areas)
    return areas


def planned_footprint(contours,settings):
    """Layer-wise sweep for review; avoids costly noding of overlapping lanes."""
    from shapely.ops import unary_union
    return unary_union(footprint_layers(contours,settings))


def isolation_diagnostics(copper,contours,settings):
    if not settings.directional:return {}
    from shapely.ops import unary_union
    first=planned_footprint(contours,settings)
    missing=copper.boundary.difference(first.buffer(.003))
    warnings=['Trial process model: painted widths vary; etched copper is not calibrated. Keep artwork axes aligned with the laser. Tight gaps may fit fewer requested lanes.']
    if settings.adaptive:
        warnings.append('Adaptive spacing may increase above target, up to 0.12 mm based on broad coupon trials. Overlap varies with direction and spacing. Curved transitions are approximate; inspect the planned removal.')
    fallback=getattr(contours,'metadata',{}).get('narrow_fallback')
    overcut=first.intersection(copper)
    if fallback:
        warnings.append('Narrow-gap fallback: two passes 0.005 mm apart. The calibrated burn is wider than some design gaps and removes intended copper; inspect orange overcut areas before engraving.')
    locations=[]
    if missing.length>.05:
        warnings.append('Some intended copper edges are not reached by the planned clearing. Requested clearances may remain smaller or uncleared. Inspect marked regions for residual copper bridges; more lanes cannot fix an undersized gap.')
        for part in (missing.geoms if hasattr(missing,'geoms') else [missing]):
            if part.length>.01:
                point=part.interpolate(.5,normalized=True);locations.append([point.x,point.y])
    return {'predicted_overcut_area_mm2':overcut.area,'adaptive':getattr(contours,'metadata',{}),'model':'provisional_ellipse','width_x_mm':settings.width_mm,'width_y_mm':settings.width_y_mm,'lane_spacing_mm':settings.spacing_mm,'uncovered_edge_length_mm':missing.length,'locations':locations,'warnings':warnings}
