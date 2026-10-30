import json
import pytest
from shapely.geometry import box
from shapely.ops import unary_union
from pcb_isolator.isolation import IsolationSettings,generate_isolation,footprint_buffer,isolation_diagnostics
from pcb_isolator.app_backend import read_board,generate,default_router
from test_job_outputs import make_job

def trial(lines=1):return IsolationSettings(.22,33.3333,lines,.33,.020)

def test_offsets_spacing_and_protection():
    copper=box(0,0,10,5);s=trial(3);paths=generate_isolation(copper,s)
    assert paths[0].bounds==pytest.approx((-.110022,-.165022,10.110022,5.165022),abs=.00001)
    assert paths[1].bounds==pytest.approx((-.130022,-.185022,10.130022,5.185022),abs=.00002)
    assert footprint_buffer(unary_union(paths),s).intersection(copper).area<1e-8
    assert s.spacing_mm==.020

def test_narrow_gap_warns_without_cutting_copper():
    copper=box(0,0,5,1).union(box(0,1.02,5,2));s=trial(3)
    paths=generate_isolation(copper,s);d=isolation_diagnostics(copper,paths,s)
    assert d['uncovered_edge_length_mm']>5
    assert d['locations']
    assert footprint_buffer(unary_union(paths),s).intersection(copper).area<1e-8

def test_trial_pipeline_records_and_review(tmp_path):
    selection=make_job(tmp_path);board=read_board(tmp_path)
    result=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,
        {'width':.22,'width_y':.33,'spacing':.020,'directional':True,'overlap':33.3333,'lines':3,'format':'both'},
        default_router(),make_router=False,output_folder=tmp_path/'preview')
    page=result['laser_review'].read_text(encoding='utf-8')
    assert 'TRIAL X 0.22 / Y 0.33' in page
    assert 'fill:#00cec0;stroke:none' in page
    assert 'X / ' in page
    summary=json.loads((result['record']/'run.json').read_text())
    assert summary['laser']['directional'] is True
    assert (result['laser']/'laser-isolation-and-marks.svg').exists()


@pytest.mark.parametrize('width',[.20,.75])
def test_fitted_export_keeps_arbitrary_traces_and_diagonal_geometry(tmp_path,width):
    import ezdxf
    from ezdxf.path import make_path
    from shapely.geometry import LineString,Point
    from pcb_isolator.dxf_export import export_dxf
    copper=LineString([(0,0),(3,3),(7,3)]).buffer(width/2).union(Point(7,3).buffer(.6))
    settings=trial(3);contours=generate_isolation(copper,settings)
    target=tmp_path/'trial.dxf';export_dxf(copper,contours,settings,target,.005)
    recovered=unary_union([LineString([(v.x,v.y) for v in make_path(e).flattening(.000001)]) for e in ezdxf.readfile(target).modelspace()])
    assert footprint_buffer(recovered,settings).intersection(copper).area<1e-7
