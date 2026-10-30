from math import pi

import ezdxf
from ezdxf import bbox
import numpy as np
import pytest
from shapely.geometry import LineString, Point, box

from pcb_isolator.dxf_export import export_dxf, fit_contour
from pcb_isolator.isolation import IsolationSettings, generate_isolation


def test_native_circle():
    angles = np.linspace(0, 2*pi, 1025)
    points = np.column_stack((4+2*np.cos(angles), 7+2*np.sin(angles)))
    fitted = fit_contour(points, 0.001)
    assert len(fitted) == 1
    assert fitted[0].kind == "CIRCLE"
    assert fitted[0].center == pytest.approx((4, 7))
    assert fitted[0].radius == pytest.approx(2)


@pytest.mark.parametrize("direction", [1, -1])
def test_arc_and_line(direction):
    angles = np.linspace(0, direction*pi/2, 257)
    points = np.column_stack((2*np.cos(angles), 2*np.sin(angles)))
    fitted = fit_contour(points, 0.001)
    assert fitted[0].kind == "ARC"
    assert fitted[0].sweep == pytest.approx(direction*pi/2)
    source = LineString(points)
    actual = LineString(fitted[0].samples())
    assert source.hausdorff_distance(actual) < 0.001


def test_export_roundtrip_and_scale(tmp_path):
    copper = box(0, 0, 10, 5)
    settings = IsolationSettings(lines=2)
    paths = generate_isolation(copper, settings)
    target = tmp_path / "board.dxf"
    report = export_dxf(copper, paths, settings, target)
    doc = ezdxf.readfile(target)
    assert doc.units == 4
    assert set(e.dxftype() for e in doc.modelspace()) == {"LWPOLYLINE"}
    assert len(doc.modelspace())==2
    assert all(e.closed and any(abs(p[2])>0 for p in e.get_points('xyb')) for e in doc.modelspace())
    assert {e.dxf.layer for e in doc.modelspace()} == {"ISOLATION_01", "ISOLATION_02"}
    bounds = bbox.extents(doc.modelspace())
    expected = paths[-1].bounds
    assert (bounds.extmin.x, bounds.extmin.y, bounds.extmax.x, bounds.extmax.y) == pytest.approx(expected, abs=0.001)
    assert not doc.audit().has_errors
    assert report["entities"]["ARC"] > 0


def test_circle_export(tmp_path):
    copper = Point(0, 0).buffer(2, quad_segs=256)
    settings = IsolationSettings(lines=1)
    target = tmp_path / "pad.dxf"
    export_dxf(copper, generate_isolation(copper, settings), settings, target)
    assert len(ezdxf.readfile(target).modelspace().query("CIRCLE")) == 1


def test_clearance_fallback(tmp_path):
    # A straight approximation of this shallow outward bend would cross copper.
    copper = box(0, 0, 10, 1).union(box(4, 1, 6, 1.0003))
    settings = IsolationSettings(lines=1)
    path = LineString([(0, 1.03752), (5, 1.038), (10, 1.03752)])
    target = tmp_path / "safe.dxf"
    report = export_dxf(copper, [path], settings, target, tolerance=0.001)
    assert report["clearance_fallbacks"] == 1
    assert report["entities"] == {"LINE": 2}
