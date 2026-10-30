import json
import pytest
from pcb_isolator.app_backend import read_board,generate,default_router,export_preview
from pcb_isolator.clearance import measure_clearance
from test_job_outputs import make_job


def test_pins_removed_policy_generates_without_keepouts(tmp_path):
    selection=make_job(tmp_path);board=read_board(tmp_path);router=default_router()
    router['alignment_pins'].update(xy_margin_mm=20,height_above_board_mm=90)
    result=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,
                    {'width':.075,'overlap':33.3333,'lines':1},router,make_laser=False,
                    output_folder=tmp_path/'preview')
    assert result.get('clearance_diagnostic') is None
    report=json.loads((result['record']/'router/router-report.json').read_text())
    for program in report['programs']:
        if 'pin_avoidance' in program:
            policy=program['pin_avoidance']
            assert policy['policy']=='pins_removed_before_machining'
            assert policy['keepout_radius_mm']==0 and policy['detoured_travels']==0
            assert policy['travel_clearance_mm']==5.08
    assert 'REMOVE ALL PINS' in result['router_review'].read_text(encoding='utf-8')
    final=export_preview(result,tmp_path/'final')
    assert final['router_review'].exists()


def test_segment_clearance_uses_nearest_point_and_envelope():
    from types import SimpleNamespace
    config=default_router();config['alignment_pins'].update(tool_envelope_diameter_mm=4,pins_removed_before_machining=False)
    config['machine'].update(origin_x_mm=0,origin_y_mm=0)
    moves=[{'g':0,'x':-5,'y':5},{'g':1,'x':5,'y':5}]
    d=measure_clearance([('profile',moves,2)],[SimpleNamespace(id='pin',x=0,y=0)],3,config)
    assert d['closest_xy']==[0,5]
    assert d['available_gap_mm']==pytest.approx(1.5)
    assert d['maximum_margin_mm']==pytest.approx(1.497)
    assert d['tool_diameter_mm']==2
    assert d['tool_envelope_diameter_mm']==4
