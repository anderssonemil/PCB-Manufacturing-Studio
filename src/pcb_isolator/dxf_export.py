"""Fit isolation contours to native DXF lines, arcs and circles."""
from collections import Counter
from dataclasses import dataclass
from math import acos, ceil, cos, degrees, isfinite, pi, sin, tan, atan2
from pathlib import Path

import ezdxf
import numpy as np
import shapely
from shapely.geometry import LineString


@dataclass
class Primitive:
    kind: str
    start: tuple
    end: tuple
    center: tuple = (0, 0)
    radius: float = 0
    angle: float = 0
    sweep: float = 0

    def samples(self, sag=0.000001):
        if self.kind == "LINE":
            return [self.start, self.end]
        step = 2 * acos(max(-1, min(1, 1-sag/self.radius)))
        count = max(8, ceil(abs(self.sweep) / max(step, 1e-8)))
        angles = np.linspace(self.angle, self.angle+self.sweep, count+1)
        points = np.column_stack((self.center[0]+self.radius*np.cos(angles),
                                  self.center[1]+self.radius*np.sin(angles)))
        points[0] = self.start
        points[-1] = self.end
        return points


def fit_line(points, tolerance):
    delta = points[-1]-points[0]
    length2 = float(delta @ delta)
    if length2 < 1e-20:
        return None
    t = ((points-points[0]) @ delta) / length2
    closest = points[0] + np.clip(t, 0, 1)[:, None]*delta
    if np.max(np.linalg.norm(points-closest, axis=1)) > tolerance:
        return None
    if np.any(np.diff(t) < -1e-10):
        return None
    return Primitive("LINE", tuple(points[0]), tuple(points[-1]))


def fit_arc(points, tolerance, closed=False):
    if len(points) < 5:
        return None
    a, b, c = points[0], points[len(points)//(3 if closed else 2)], points[-1 if not closed else 2*len(points)//3]
    # Solve relative to the first point to avoid cancellation far from origin.
    u, v = b-a, c-a
    matrix = 2*np.array([u, v])
    if abs(np.linalg.det(matrix)) < 1e-12:
        return None
    center = a + np.linalg.solve(matrix, [u@u, v@v])
    vectors = points-center
    radii = np.linalg.norm(vectors, axis=1)
    radius = float(radii[0])
    if not isfinite(radius) or radius <= 0:
        return None
    angles = np.unwrap(np.arctan2(vectors[:, 1], vectors[:, 0]))
    increments = np.diff(angles)
    sweep = float(angles[-1]-angles[0])
    if abs(sweep) < 1e-6 or abs(sweep) > 2*pi+1e-7:
        return None
    if np.any(increments*np.sign(sweep) < -1e-9):
        return None
    # Bound deviation between vertices too, not only radial error at vertices.
    error = float(np.max(np.abs(radii-radius)))
    sag = radius*(1-cos(float(np.max(np.abs(increments)))/2))
    if error+sag > tolerance:
        return None
    if closed and abs(abs(sweep)-2*pi) > 1e-7:
        return None
    return Primitive("CIRCLE" if closed else "ARC", tuple(points[0]), tuple(points[-1]),
                     tuple(center), radius, float(angles[0]), sweep)


def fit_contour(coordinates, tolerance):
    points = np.asarray(coordinates, dtype=float)
    circle = fit_arc(points, tolerance, closed=True) if np.allclose(points[0], points[-1], atol=1e-10, rtol=0) else None
    if circle:
        return [circle]
    result = []
    index = 0
    while index < len(points)-1:
        best = Primitive("LINE", tuple(points[index]), tuple(points[index+1]))
        best_end = index+1
        # Each fit type has a separate growing search so that a failed line
        # cannot prematurely terminate the search for a rounded section.
        for fitter, minimum in ((fit_line, 2), (fit_arc, 5)):
            end = index+minimum-1
            if end >= len(points):
                continue
            candidate = fitter(points[index:end+1], tolerance)
            if candidate is None:
                continue
            low = end
            high = min(len(points)-1, index+2*(end-index))
            while high > low:
                trial = fitter(points[index:high+1], tolerance)
                if trial is None:
                    break
                low, candidate = high, trial
                high = min(len(points)-1, index+2*(high-index))
            if high > low:
                while high-low > 1:
                    mid = (low+high)//2
                    trial = fitter(points[index:mid+1], tolerance)
                    if trial is None:
                        high = mid
                    else:
                        low, candidate = mid, trial
            if low > best_end:
                best, best_end = candidate, low
        result.append(best)
        index = best_end
    return result


def export_dxf(copper, contours, settings, destination: Path, tolerance=0.001):
    if not isfinite(tolerance) or not 0 < tolerance <= 0.01:
        raise ValueError("Curve tolerance must be greater than zero and at most 0.01 mm.")
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    doc.header["$MEASUREMENT"] = 1
    model = doc.modelspace()
    # Samples approximate a true arc by <= 1 micrometer. Expanding the
    # forbidden area by that amount conservatively checks the native curve.
    sag = 0.000001
    from .isolation import footprint_buffer
    forbidden = footprint_buffer(copper,settings,sag)
    shapely.prepare(forbidden)
    counts = Counter()
    fallbacks = 0
    for number, contour in enumerate(contours, 1):
        narrow=(number-1) in getattr(contours,"fallback_indices",set())
        active_forbidden=copper.buffer(sag) if narrow else forbidden
        layer = f"ISOLATION_{number:02}"
        doc.layers.new(layer, dxfattribs={"color": 1})
        parts = list(contour.geoms) if hasattr(contour, "geoms") else [contour]
        for part in parts:
            if part.is_empty:continue
            coordinates = np.asarray(part.coords)
            joined=[]
            for primitive in fit_contour(coordinates, min(tolerance,.0005) if narrow else tolerance):
                if primitive.kind=='ARC':
                    # Bulges connect the exact endpoints. Validate that actual
                    # curve, rather than a best-fit circle with snapped endpoints.
                    a=np.asarray(primitive.start);b=np.asarray(primitive.end);delta=b-a
                    center=(a+b)/2+np.array([-delta[1],delta[0]])/(2*tan(primitive.sweep/2))
                    primitive.center=tuple(center);primitive.radius=float(np.linalg.norm(a-center))
                    primitive.angle=atan2(a[1]-center[1],a[0]-center[0])
                if shapely.intersects(active_forbidden, LineString(primitive.samples(sag))):
                    # Reject an approximation that approaches copper. Restore
                    # the original vertices between this fit's exact endpoints.
                    start = np.flatnonzero(np.all(coordinates == primitive.start, axis=1))[0]
                    ends = np.flatnonzero(np.all(coordinates == primitive.end, axis=1))
                    end = next((int(i) for i in ends if i > start), len(coordinates)-1)
                    replacements = [Primitive("LINE", tuple(a), tuple(b)) for a, b in zip(coordinates[start:end], coordinates[start+1:end+1])]
                    fallbacks += 1
                else:
                    replacements = [primitive]
                for item in replacements:
                    joined.append(item)
                    counts[item.kind] += 1
            if len(joined)==1 and joined[0].kind=='CIRCLE':
                item=joined[0];model.add_circle(item.center,item.radius,dxfattribs={'layer':layer})
            elif joined:
                closed=np.allclose(coordinates[0],coordinates[-1],atol=1e-10,rtol=0)
                vertices=[(*item.start,tan(item.sweep/4) if item.kind=='ARC' else 0) for item in joined]
                if not closed:vertices.append((*joined[-1].end,0))
                model.add_lwpolyline(vertices,format='xyb',close=bool(closed),dxfattribs={'layer':layer})
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(destination)
    return {"entities": dict(counts), "clearance_fallbacks": fallbacks,
            "units": "mm", "curve_tolerance_mm": tolerance}
