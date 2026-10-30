"""Import finished board boundaries from a dedicated Edge.Cuts DXF."""
from pathlib import Path
import ezdxf
from ezdxf.path import make_path
from shapely.geometry import LineString
from shapely.ops import polygonize_full, unary_union


def load_outline(path: Path):
    doc = ezdxf.readfile(path)
    # Unitless DXF requires an explicit choice rather than silently assuming mm.
    factors = {4: 1.0, 1: 25.4, 5: 10.0, 6: 1000.0}
    if doc.units not in factors:
        raise ValueError("Outline DXF must declare supported physical units (prefer millimeters).")
    factor = factors[doc.units]
    lines = []
    for entity in doc.modelspace():
        if entity.dxftype() not in {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}:
            raise ValueError(f"Outline contains unsupported {entity.dxftype()} entity; export only Edge.Cuts.")
        points = list(make_path(entity).flattening(distance=0.001/factor))
        if any(abs(p.z) > 1e-9 for p in points):
            raise ValueError("Outline must lie in the XY plane.")
        lines.append(LineString([(p.x*factor, p.y*factor) for p in points]))
    if not lines:
        raise ValueError("Outline DXF is empty.")
    polygons, cuts, dangles, invalid = polygonize_full(unary_union(lines))
    if not cuts.is_empty or not dangles.is_empty or not invalid.is_empty or polygons.is_empty:
        raise ValueError("Outline has open, dangling or invalid contours; join them in KiCad first.")
    # Return distinct closed rings, keeping internal cutouts separate.
    rings = {}
    for polygon in polygons.geoms:
        for ring in [polygon.exterior, *polygon.interiors]:
            shape = LineString(ring.coords)
            rings[shape.normalize().wkb] = shape
    return list(rings.values())
