import json
from pathlib import Path
import tomllib

import ezdxf
import pytest

from test_job_outputs import make_job
from pcb_isolator.app_backend import read_board,generate,default_router,write_toml,release_outputs,export_preview
from pcb_isolator.job_outputs import validate_selection


def test_toml_settings_roundtrip(tmp_path):
    config=default_router()
    config['drilling']['tools']=[{'diameter_mm':1.0,'peck_mm':0.0}]
    path=tmp_path/'config.toml';write_toml(path,config)
    assert tomllib.loads(path.read_text())==config


def test_preview_without_alignment_and_laser_only_release(tmp_path):
    make_job(tmp_path)
    board=read_board(tmp_path);router=default_router()
    laser={'width':.075,'overlap':33.3333,'lines':1}
    result=generate(board,[],None,3.175,laser,router,registration_preview=True,
                    output_folder=tmp_path/'preview')
    assert result['router_review'].exists()
    assert 'PREVIEW ONLY' in result['router_review'].read_text(encoding='utf-8')
    assert not list(result['router'].glob('spoilboard*'))
    with pytest.raises(ValueError,match='two alignment holes'):release_outputs(result)
    with pytest.raises(ValueError,match='two alignment holes'):export_preview(result,tmp_path/'final')
    result=generate(board,[],None,3.175,laser,router,make_router=False,
                    output_folder=tmp_path/'laser-preview')
    final=export_preview(result,tmp_path/'laser-final')
    assert final['laser_review'].exists() and 'router' not in final


def test_undersized_selection_requires_acknowledgement(tmp_path):
    from pcb_isolator.app_backend import make_selection
    make_job(tmp_path);board=read_board(tmp_path)
    ids=[f.id for f in board['features'][-2:]]
    with pytest.raises(ValueError,match='undersized'):make_selection(board,ids,3.175)
    selection=make_selection(board,ids,3.175,undersized_holes_acknowledged=True)
    _,_,alignment,remaining,_=validate_selection(tmp_path,selection)
    assert [f.diameter_mm for f in alignment]==[.5,1.0]
    assert len(remaining)==2


def test_hole_free_board_laser_output(tmp_path):
    from hashlib import sha256
    make_job(tmp_path)
    drill=tmp_path/'inputs/holes.drl'
    drill.write_text('M48\nMETRIC\n%\nG90\nM30\n')
    manifest_path=tmp_path/'manufacturing-job.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['sha256']['inputs/holes.drl']=sha256(drill.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    (tmp_path/'outputs/pcb-job.json').unlink()
    board=read_board(tmp_path);assert board['features']==[]
    result=generate(board,[],None,3.175,{'width':.075,'overlap':33.3333,'lines':1},
                    default_router(),make_router=False,output_folder=tmp_path/'preview')
    final=export_preview(result,tmp_path/'final')
    doc=ezdxf.readfile(final['laser']/'laser-isolation-and-marks.dxf')
    assert len(doc.modelspace())>0
    assert not list(doc.modelspace().query('*[layer=="ALIGNMENT_CENTER_MARKS"]'))


def test_overlapping_drill_at_pin_location_is_excluded(tmp_path):
    from hashlib import sha256
    from pcb_isolator.app_backend import make_selection
    make_job(tmp_path)
    drill=tmp_path/'inputs/holes.drl'
    drill.write_text(drill.read_text().replace('M30','T2\nX3.0Y3.0\nM30'))
    manifest_path=tmp_path/'manufacturing-job.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['sha256']['inputs/holes.drl']=sha256(drill.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest));(tmp_path/'outputs/pcb-job.json').unlink()
    board=read_board(tmp_path)
    ids=[board['features'][-1].id,board['features'][1].id]
    selection=make_selection(board,ids,3.175,undersized_holes_acknowledged=True)
    _,_,alignment,remaining,_=validate_selection(tmp_path,selection)
    assert len(alignment)==2 and len(remaining)==2
    assert not any(f.x==3 and f.y==3 for f in remaining)
    assert selection['alignment_hole_overrides'][0]['manufacturing_diameter_mm']==3.175


def test_desktop_pipeline_relative_job_and_line_count(tmp_path,monkeypatch):
    def blocked_rename(*args,**kwargs):
        raise PermissionError('Simulated synced-folder rename denial')
    monkeypatch.setattr(Path,'rename',blocked_rename)
    selection=make_job(tmp_path)
    board=read_board(tmp_path)
    router=default_router()
    router['alignment_pins'].update(xy_margin_mm=.1,tool_envelope_diameter_mm=.5,start_x_mm=-10.0)
    laser={'width':.075,'overlap':33.3333,'lines':2}
    results=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,laser,router)
    assert results['laser_review'].exists() and results['router_review'].exists()
    doc=ezdxf.readfile(results['laser']/'laser-isolation-and-marks.dxf')
    assert not (results['laser']/'laser-alignment-marks.dxf').exists()
    layers={entity.dxf.layer for entity in doc.modelspace()}
    assert 'ISOLATION_02' in layers and 'ISOLATION_03' not in layers
    saved=json.loads((tmp_path/'outputs/pcb-job.json').read_text())
    assert saved['copper']=='inputs/copper.gbr'
    validate_selection(tmp_path,saved)
    restored=read_board(tmp_path)
    assert restored['ui_settings']['laser']['lines']==2
    assert results['run']==tmp_path/'Manufacturing Output'
    assert {p.name for p in results['run'].iterdir()}=={'Laser','Router','Start Here.html'}
    assert all(p.name.endswith('.mmg.draft') or p.name=='Review.html' for p in results['router'].iterdir())
    internal=next((tmp_path/'outputs').glob('app-run-*'))
    report=json.loads((internal/'router/router-report.json').read_text())
    assert report['configuration']['machine']['origin_x_mm']==3
    assert report['configuration']['machine']['origin_y_mm']==3
    original={p.name:p.read_bytes() for p in results['router'].glob('*.mmg.draft')}
    release_outputs(results)
    receipt=json.loads((internal/'release.json').read_text())
    for old,new in receipt['program_names'].items():
        assert (results['router']/new).read_bytes()==original[old]
    assert not list(results['router'].glob('*.draft'))
    assert 'RELEASED' in results['router_review'].read_text(encoding='utf-8')
    assert 'Released output' in (results['run']/'Start Here.html').read_text()
    from pcb_isolator.job_guide import build_job_guide
    guide=build_job_guide(internal,results['run'],receipt['program_names'],released=True)
    assert [s['id'] for s in guide['steps']][:4]==['laser','etch','spoil','mount']
    assert guide['steps'][-2]['id']=='profile'
    for step in guide['steps']:
        if step.get('program'):
            assert (results['run']/step['filename']).is_file()
            assert 'Reset Z zero on TOP OF THE PCB' in ' '.join(step['actions']) or step['id']=='spoil'
    assert guide['pins'][0]['x']==0 and guide['pins'][0]['y']==0
    assert guide['steps'][0]['facts'][1][1]=='2 lines'
    with pytest.raises(ValueError,match='already been released'):release_outputs(results)
    shallow=tmp_path/'project/Manufacturing Output'
    fresh=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,laser,router,output_folder=shallow)
    assert fresh['run']==shallow
    release_outputs(fresh)
    fresh=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,laser,router,output_folder=shallow)
    changed=next(fresh['router'].glob('*.mmg.draft'));changed.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed since generation'):release_outputs(fresh)
    preview=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,laser,router,output_folder=tmp_path/'outputs/preview-test')
    final=export_preview(preview,tmp_path/'Final Output')
    assert final['run']==tmp_path/'Final Output'
    assert list(final['router'].glob('*.mmg'))
    assert not list(final['router'].glob('*.draft'))
    assert final['router_review'].exists()
    export_preview(preview,tmp_path/'Final Output')
    generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,laser,router,True,False)
    assert not (results['run']/'Router').exists()
    assert list((tmp_path/'outputs').glob('app-run-*/previous-output/Router'))
    laser_record=max((tmp_path/'outputs').glob('app-run-*'),key=lambda p:p.stat().st_mtime)
    laser_guide=build_job_guide(laser_record,results['run'])
    assert [s['id'] for s in laser_guide['steps']]==['laser','etch','inspect']
