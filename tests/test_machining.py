from pathlib import Path
import ezdxf
import pytest

from pcb_isolator.drills import load_drills
from pcb_isolator.outline import load_outline


def drill_file(tmp_path, body, units='METRIC'):
    path = tmp_path/'test.drl'
    path.write_text(f'M48\n{units}\nT1C1.0\n%\nG90\nG05\nT1\n{body}\nM30\n')
    return path


def test_drill_units_and_omitted_axis(tmp_path):
    features = load_drills(drill_file(tmp_path, 'X1.0Y2.0\nX3.0', 'INCH'))
    assert len(features) == 2
    assert features[1].diameter_mm == pytest.approx(25.4)
    assert features[1].x == pytest.approx(76.2)
    assert features[1].y == pytest.approx(50.8)


def test_slot(tmp_path):
    features = load_drills(drill_file(tmp_path, 'X1.0Y2.0G85X3.0Y2.0'))
    assert len(features) == 1
    assert features[0].end == (3, 2)


def test_empty_drill_category_is_valid(tmp_path):
    assert load_drills(drill_file(tmp_path, '')) == []


def test_routed_slot(tmp_path):
    features = load_drills(drill_file(tmp_path, 'G00X1.0Y2.0\nM15\nG01X3.0Y2.0\nM16'))
    assert len(features) == 1
    assert features[0].end == (3, 2)


@pytest.mark.parametrize('body', ['G91\nX1.0Y2.0', 'X100Y200', 'G02X1.0Y2.0', 'R3X1.0Y2.0', 'G01X1.0Y2.0'])
def test_unsupported_drill_commands_rejected(tmp_path, body):
    with pytest.raises(ValueError):
        load_drills(drill_file(tmp_path, body))


def test_outline_and_cutout(tmp_path):
    doc = ezdxf.new('R2010'); doc.units = 4
    doc.modelspace().add_lwpolyline([(0,0),(10,0),(10,5),(0,5)], close=True)
    doc.modelspace().add_circle((3,2), 1)
    path = tmp_path/'edge.dxf'; doc.saveas(path)
    rings = load_outline(path)
    assert len(rings) == 2
    assert max(r.length for r in rings) == pytest.approx(30)


def test_open_outline_rejected(tmp_path):
    doc = ezdxf.new('R2010'); doc.units = 4
    doc.modelspace().add_line((0,0),(10,0))
    path = tmp_path/'edge.dxf'; doc.saveas(path)
    with pytest.raises(ValueError, match='open'):
        load_outline(path)


def test_existing_drill_files():
    root = Path('local-boards/pi-transducer')
    if not (root/'Pi Transducer-PTH.drl').exists():
        pytest.skip('Personal reference files absent')
    assert len(load_drills(root/'Pi Transducer-PTH.drl')) == 39
    assert len(load_drills(root/'Pi Transducer-NPTH.drl')) == 4


def test_combined_preview(tmp_path):
    from pcb_isolator.machining_preview import write_machining_preview
    copper = tmp_path/'copper.gbr'
    copper.write_text('%FSLAX46Y46*%\n%MOMM*%\n%TF.FileFunction,Copper,L2,Bot*%\n%ADD10C,4*%\n%LPD*%\nD10*\nX0Y0D03*\nM02*\n')
    drill = drill_file(tmp_path, 'X0.0Y0.0').read_text().replace('T1C1.0', 'T1C3.3')
    drill_path = tmp_path/'holes.drl'; drill_path.write_text(drill)
    destination = tmp_path/'combined.html'
    write_machining_preview(copper, [drill_path], destination)
    html = destination.read_text(encoding='utf-8')
    assert 'id="hole-0"' in html
    assert 'data-hole="0"' in html
    assert 'id="save-selection" disabled' in html
    assert '"pin_diameter_mm": 3.175' in html
    assert '"one_file_per_tool": true' in html
    assert '__JOB__' not in html
