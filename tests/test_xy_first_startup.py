import json
from pathlib import Path
import re
import pytest
from pcb_isolator.router import load_machining,xy_first_startup,write_draft,prepare_router_drafts
from pcb_isolator.router_animation import parse_motions
from pcb_isolator.router_review import parse_draft
from pcb_isolator.app_backend import write_toml
from test_job_outputs import make_job


def test_startup_skips_virtual_staging_detour_only(tmp_path):
    config=load_machining(Path('machining.toml'))
    config['machine'].update(origin_x_mm=10,origin_y_mm=20)
    moves=[{'g':0,'z':12},{'g':0,'x':5,'y':22},{'g':0,'x':15,'y':25},
           {'g':0,'z':.5},{'g':1,'z':-.7,'f':127},{'g':0,'z':1},
           {'g':0,'z':-.5},{'g':1,'z':-1.4,'f':127},{'g':0,'z':12},
           {'g':0,'x':18,'y':25},{'g':0,'x':20,'y':25},{'g':0,'z':.5},
           {'g':1,'z':-1.9,'f':127},{'g':0,'z':12}]
    planned,info=xy_first_startup(moves,config)
    assert planned[:2]==[moves[2],moves[0]]
    assert planned[2:]==moves[3:]  # Every peck and subsequent pin detour retained.
    assert info['first_work_xy_mm']==[5,5]
    target=tmp_path/'test.mmg.draft';write_draft(target,moves,config,'Test')
    text=target.read_text();assert text.index('G00X5.000Y5.000')<text.index('G00Z12.000')
    motions=parse_motions(text,[-10,0])
    assert motions[0]['to']==[5,5,12]
    assert motions[0]['initial_z_unknown']
    segments,_=parse_draft(text,[-10,0])
    assert segments[0]['from']==[5,5]  # No fictional route from unknown gantry XY.


def test_all_tool_files_position_xy_before_z_and_spoilboard_starts_at_datum(tmp_path):
    selection=make_job(tmp_path)
    selection['alignment_ids'].reverse()
    (tmp_path/'outputs/pcb-job.json').write_text(json.dumps(selection))
    config=load_machining(Path('machining.toml'))
    config['machine'].update(origin_x_mm=3,origin_y_mm=3)
    config['alignment_pins'].update(xy_margin_mm=.1,tool_envelope_diameter_mm=1)
    settings=tmp_path/'router.toml';write_toml(settings,config)
    output=prepare_router_drafts(tmp_path,settings)
    report=json.loads((output/'router-report.json').read_text())
    assert len(report['programs'])==4
    for program in report['programs']:
        text=(output/program['file']).read_text()
        moves=[line for line in text.splitlines() if re.match(r'N\d+G',line)]
        assert 'X' in moves[0] and 'Y' in moves[0] and 'Z' not in moves[0]
        assert 'Z' in moves[1] and 'X' not in moves[1] and 'Y' not in moves[1]
        assert program['startup']['requires_tool_set_max_height']
        if program['file'].startswith('spoilboard'):
            assert 'X0.000Y0.000' in moves[0]
    review=json.loads((output/'review-data.json').read_text())
    assert all(p['start']==p['startup']['first_work_xy_mm'] for p in review['programs'])
    assert 'before lowering Z' in (output/'router-review.html').read_text(encoding='utf-8') or 'then lower Z' in (output/'router-review.html').read_text(encoding='utf-8')
