from math import pi
from pathlib import Path
import pytest
from shapely.geometry import Point
from pcb_isolator.importer import load_copper
from pcb_isolator.preview import write_preview


def gerber(units="MM", clear=False):
    return (f"%FSLAX46Y46*%\n%MO{units}*%\n%TF.FileFunction,Copper,L2,Bot*%\n"
            "%ADD10C,2*%\n%ADD11C,1*%\n%LPD*%\nD10*\nX0Y0D03*\n"
            + ("%LPC*%\nD11*\nX0Y0D03*\n" if clear else "") + "M02*\n")


def save(tmp_path, source):
    path = tmp_path / "sample.gbr"
    path.write_text(source)
    return path


def test_clear_polarity_preserves_hole(tmp_path):
    geometry = load_copper(save(tmp_path, gerber(clear=True))).geometry
    assert not geometry.contains(Point(0, 0))
    assert geometry.contains(Point(0.75, 0))
    assert geometry.area == pytest.approx(pi * 0.75, rel=0.002)


def test_inches_converted_to_mm(tmp_path):
    geometry = load_copper(save(tmp_path, gerber("IN"))).geometry
    assert geometry.bounds == pytest.approx((-25.4, -25.4, 25.4, 25.4))


def test_reject_mask(tmp_path):
    with pytest.raises(ValueError, match="Expected copper"):
        load_copper(save(tmp_path, gerber().replace("Copper,L2,Bot", "Soldermask,Bot")))


def test_preview(tmp_path):
    destination = write_preview(save(tmp_path, gerber(clear=True)), tmp_path / "preview.html")
    text = destination.read_text(encoding="utf-8")
    assert 'fill-rule="evenodd"' in text
    assert "__PATHS__" not in text
    assert "2.000 × 2.000 mm" in text
    assert 'data-pass="5"' in text
    assert 'id="lines"' in text
    import re
    assert not re.search(r"__[A-Z]+__", text)


def test_real_board():
    path = Path("local-boards/pi-transducer/Pi Transducer-B_Cu.gbr")
    if not path.exists():
        pytest.skip("Personal reference board not present")
    layer = load_copper(path)
    assert layer.geometry.is_valid
    assert layer.source_units == "mm"
    # Copper's outer profile strokes in this revision run from X26.994 to X113.916.
    assert layer.geometry.bounds[0] == pytest.approx(26.994)
    assert layer.geometry.bounds[2] == pytest.approx(113.916)
