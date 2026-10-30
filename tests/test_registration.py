from pathlib import Path
from math import hypot
import json
from hashlib import sha256
import ezdxf
import pytest
from shapely.geometry import Point,LinearRing
from pcb_isolator.registration import outline_candidates,edge_warnings
from pcb_isolator.drills import DrillFeature
from pcb_isolator.app_backend import read_board,make_selection,generate,default_router
from pcb_isolator.job_outputs import validate_selection
from test_job_outputs import make_job


def test_round_internal_outline_only_and_no_duplicate():
    outside=LinearRing([(0,0),(20,0),(20,10),(0,10)])
    hole=Point(4,4).buffer(.6,quad_segs=64).exterior
    extra=outline_candidates([outside,hole],[])
    assert len(extra)==1 and extra[0].diameter_mm==pytest.approx(1.2)
    assert extra[0].id.startswith('outline:')
    assert outline_candidates([outside,hole],[DrillFeature('drill',1.2,4,4)])==[]
    assert outline_candidates([outside,LinearRing([(2,2),(3,2),(3,3),(2,3)])],[])==[]


def test_outline_registration_selection_and_router_exclusion(tmp_path):
    make_job(tmp_path)
    path=tmp_path/'inputs/outline.dxf';doc=ezdxf.readfile(path)
    doc.modelspace().add_circle((4,7),.6);doc.modelspace().add_circle((16,7),.6);doc.saveas(path)
    manifest_path=tmp_path/'manufacturing-job.json';manifest=json.loads(manifest_path.read_text())
    manifest['sha256']['inputs/outline.dxf']=sha256(path.read_bytes()).hexdigest();manifest_path.write_text(json.dumps(manifest))
    board=read_board(tmp_path);extra=board['outline_alignment'];assert len(extra)==2
    ids=[f.id for f in extra]
    selection=make_selection(board,ids,3.175,undersized_holes_acknowledged=True)
    _,_,alignment,remaining,_=validate_selection(tmp_path,selection)
    assert len(alignment)==2 and len(remaining)==4
    result=generate(board,ids,ids[0],3.175,{'width':.075,'overlap':33.3,'lines':1},default_router(),make_laser=False,undersized_holes_acknowledged=True,output_folder=tmp_path/'review')
    report=json.loads((result['record']/'router/router-report.json').read_text())
    assert len(report['registration_cutouts'])==2
    assert all(p['kind']=='outside' for p in __import__('pcb_isolator.router',fromlist=['compensated_profiles']).compensated_profiles(board['outline'],2.54,report['registration_cutouts']))
    assert 'REMOVE ALL PINS' in (result['run']/'Start Here.html').read_text(encoding='utf-8')
    selection['outline_candidates'][0]['x']+=1
    with pytest.raises(ValueError,match='outline alignment'):validate_selection(tmp_path,selection)


def test_large_pin_near_edge_is_visible_warning():
    rings=[LinearRing([(0,0),(20,0),(20,10),(0,10)])]
    board={'outline':rings,'features':[DrillFeature('pin',1.2,1.27,3)]}
    warnings=edge_warnings(board,['pin'],3.175)
    assert len(warnings)==1 and 'extends 0.31' in warnings[0]
