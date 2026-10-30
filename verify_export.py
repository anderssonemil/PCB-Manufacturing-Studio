"""Read back the sample export and verify scale, audit, and copper clearance."""
from pathlib import Path
import json
from math import radians, pi

import ezdxf
from ezdxf import bbox
import shapely
from shapely.geometry import LineString

from pcb_isolator.dxf_export import Primitive
from pcb_isolator.importer import load_copper
from pcb_isolator.isolation import generate_isolation, load_settings


def main():
    destination = Path("generated/isolation.dxf")
    report = json.loads(destination.with_suffix(".report.json").read_text())
    copper = load_copper(Path(report["source"])).geometry
    settings = load_settings(Path("config.toml"))
    contours = generate_isolation(copper, settings)
    doc = ezdxf.readfile(destination)
    assert doc.units == 4, "DXF must declare millimeters"
    assert not doc.audit().has_errors, "DXF audit failed"
    expected = contours[-1].bounds
    bounds = bbox.extents(doc.modelspace())
    actual = (bounds.extmin.x, bounds.extmin.y, bounds.extmax.x, bounds.extmax.y)
    assert max(abs(a-b) for a, b in zip(actual, expected)) <= report["curve_tolerance_mm"]
    forbidden = copper.buffer(settings.width_mm/2+0.000001, quad_segs=64)
    shapely.prepare(forbidden)
    violations = 0
    for entity in doc.modelspace():
        kind = entity.dxftype()
        if kind == "LINE":
            points = [entity.dxf.start.xy, entity.dxf.end.xy]
        else:
            center, radius = entity.dxf.center, entity.dxf.radius
            angle = radians(entity.dxf.start_angle) if kind == "ARC" else 0
            sweep = radians((entity.dxf.end_angle-entity.dxf.start_angle)%360) if kind == "ARC" else 2*pi
            from math import cos, sin
            start = (center.x+radius*cos(angle), center.y+radius*sin(angle))
            end = (center.x+radius*cos(angle+sweep), center.y+radius*sin(angle+sweep))
            points = Primitive(kind, start, end, center.xy, radius, angle, sweep).samples()
        if shapely.intersects(forbidden, LineString(points)):
            violations += 1
    assert violations == 0, f"{violations} entities failed conservative copper clearance"
    print(f"PASS: DXF readback, audit, millimeter scale, bounds, and {len(doc.modelspace())} entities checked for copper clearance")
    print("Bounds (mm):", actual)


if __name__ == "__main__":
    main()
