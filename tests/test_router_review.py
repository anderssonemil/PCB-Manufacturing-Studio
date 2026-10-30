import json
from pathlib import Path
import pytest

from pcb_isolator.router_review import parse_draft,write_router_review,write_job_index,copper_svg_path


def test_review_parses_actual_commands_and_peck_depths():
    text='(Test)\nN10M03\nN20G00Z12.000\nN30G00X3.000Y4.000\nN40G1Z-0.700F127.0\nN50G00Z1.000\nN60G1Z-1.400F127.0\nN70G00Z12.000\nN80M05\nN90M30\n%\n'
    segments,plunges=parse_draft(text,[0,0])
    assert segments==[{'from':[0,0],'to':[3,4],'rapid':True,'z':12}]
    assert [p['z'] for p in plunges]==[-0.7,-1.4]
    assert [p['feed'] for p in plunges]==[127,127]


def test_review_rejects_unexpected_speed_command():
    with pytest.raises(ValueError,match='spindle-speed'):
        parse_draft('N10M03S16000\n',[0,0])


def test_copper_overlay_uses_router_origin_and_preserves_voids():
    from shapely.geometry import Polygon
    geometry=Polygon([(3,4),(13,4),(13,14),(3,14)],holes=[[(5,6),(7,6),(7,8),(5,8)]])
    drawing=copper_svg_path(geometry,(3,4))
    assert drawing.count('M')==2 and drawing.count(' Z')==2
    assert '0.0000,-0.0000' in drawing and '10.0000,-10.0000' in drawing
    assert '2.0000,-2.0000' in drawing


def test_existing_router_review():
    root=Path('jobs/Transducer Connectors and ADC board/20261018T192509Z-9e5426/outputs/router-draft-20261018T195504Z-e6a18e')
    if not root.exists():
        pytest.skip('Personal reference job absent')
    destination=write_router_review(root)
    page=destination.read_text(encoding='utf-8')
    assert '__DATA__' not in page
    data=json.loads((root/'review-data.json').read_text(encoding='utf-8'))
    assert [p['holes'] for p in data['programs'][:3]]==[2,32,18]
    assert data['programs'][-1]['title']=='Board profile'
    assert data['programs'][1]['pin_avoidance']['travel_clearance_mm']==12
    assert sorted(set(p['z'] for p in data['programs'][1]['plunges']))==[-1.9,-1.4,-0.7]


def test_job_index_lists_available_review(tmp_path):
    root=Path('jobs/Transducer Connectors and ADC board')
    if not root.exists():
        pytest.skip('Personal reference job absent')
    destination=write_job_index(Path('jobs'),tmp_path/'jobs.html')
    text=destination.read_text(encoding='utf-8')
    assert 'Transducer Connectors and ADC board' in text
    assert 'Open router review' in text
    assert 'file:///' in text
