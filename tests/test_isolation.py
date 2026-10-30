import pytest
from shapely.geometry import Point, box
from shapely.ops import unary_union

from pcb_isolator.isolation import IsolationSettings, generate_isolation, load_settings


def test_pass_spacing_and_footprint_clearance():
    copper = box(0, 0, 10, 5)
    settings = IsolationSettings()
    paths = generate_isolation(copper, settings)
    assert len(paths) == 5
    for index, path in enumerate(paths):
        assert path.distance(copper) == pytest.approx(0.0375 + index * 0.050000025, abs=0.00003)
        assert path.buffer(settings.width_mm / 2, quad_segs=64).intersection(copper).area < 1e-10
    assert settings.cleared_width_mm() == pytest.approx(0.275, abs=1e-6)


def test_tight_gap_does_not_cross_neighbor():
    copper = unary_union([box(0, 0, 1, 3), box(1.04, 0, 2, 3)])
    settings = IsolationSettings()
    for path in generate_isolation(copper, settings):
        assert path.distance(copper) >= settings.width_mm / 2
        assert path.buffer(settings.width_mm / 2).intersection(copper).area < 1e-10
        # 0.04 mm slot cannot accommodate a 0.075 mm laser footprint.
        assert path.intersection(box(1.001, 0.1, 1.039, 2.9)).is_empty


def test_internal_clearance_is_included():
    copper = Point(0, 0).buffer(5, quad_segs=128).difference(Point(0, 0).buffer(1, quad_segs=128))
    path = generate_isolation(copper, IsolationSettings(lines=1))[0]
    assert len(path.geoms) == 2
    assert path.distance(copper) >= 0.0375


@pytest.mark.parametrize("kwargs", [{"width_mm": 0}, {"width_mm": float("nan")},
                                      {"overlap_percent": 100}, {"lines": 0}, {"lines": 2.5}])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        IsolationSettings(**kwargs)


def test_project_configuration():
    assert load_settings("config.toml") == IsolationSettings()
