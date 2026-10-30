import json
from pathlib import Path
import pytest

from pcb_isolator.operation_guide import build_data,write_html


def test_tested_package_guide(tmp_path):
    package=Path('../first-board-test')
    if not package.exists():
        pytest.skip('Personal test package absent')
    data=build_data(package)
    assert len(data['steps'])==8
    assert [s.get('filename') for s in data['steps'] if s.get('program')]==[
        '01-1_8.mmg','02-0500.mmg','03-1000.mmg','04-2p54mm.mmg']
    assert [(p['x'],p['y']) for p in data['pins']]==[(0,0),(120,0)]
    assert len(data['programs']['02-0500.mmg']['plunges'])==96
    destination=tmp_path/'guide.html'
    write_html(data,destination)
    text=destination.read_text(encoding='utf-8')
    assert '__DATA__' not in text
    assert 'localStorage' in text and 'job.job_key' in text
    assert 'Mark done &amp; Next' in text
    assert 'Reset Z zero on TOP OF THE PCB' in text
    assert 'https://' not in text and '<script src=' not in text
