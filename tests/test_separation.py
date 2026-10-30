import json
from hashlib import sha256
import ezdxf
import pytest
from shapely.geometry import LineString,Polygon,box
from shapely.ops import unary_union

from pcb_isolator.separation import separation_paths
from pcb_isolator.router import profile_moves,prepare_router_drafts
from pcb_isolator.app_backend import default_router,write_toml
from pcb_isolator.kicad_export import load_job
from test_job_outputs import make_job


def ring(shape):return LineString(shape.exterior.coords)


def test_clips_edges_and_keeps_short_endpoints():
    lines=[LineString([(-5,5),(15,5)]),LineString([(2,2),(4,2)])]
    paths,report=separation_paths(lines,[ring(box(0,0,10,10))])
    horizontal=next(p for p in paths if p['points'][0][1]==5)
    assert horizontal['points']==[(.002,5),(9.998,5)]
    assert any(p['points']==[(2,2),(4,2)] for p in paths)
    assert report['paths']==2


def test_crossings_overlaps_and_internal_cutouts():
    lines=[LineString([(1,5),(9,5)]),LineString([(3,5),(7,5)]),LineString([(5,1),(5,9)])]
    paths,_=separation_paths(lines,[ring(box(0,0,10,10))])
    geometry=[LineString(p['points']) for p in paths]
    assert sum(p.length for p in geometry)==pytest.approx(16)
    assert sum(p.length for p in geometry)==pytest.approx(unary_union(geometry).length)
    assert sum((5,5) in p['points'] for p in paths)==4
    paths,_=separation_paths(lines,[ring(box(0,0,10,10)),ring(box(4,4,6,6))])
    assert all(not LineString(p['points']).intersects(box(4,4,6,6)) for p in paths)


def test_open_line_runs_backwards_for_next_depth():
    config=default_router();config['profile']['stepdown_mm']=1
    paths=[{'kind':'separation','closed':False,'points':[(0,0),(10,0),(10,10)]}]
    moves=profile_moves(paths,2,config)
    assert [(m['x'],m['y']) for m in moves if m['g']==1 and 'x' in m]==[(10,0),(10,10),(10,0),(0,0)]


def test_program_cuts_separation_before_outside_and_checks_hash(tmp_path):
    make_job(tmp_path)
    doc=ezdxf.new('R2010');doc.units=4
    doc.modelspace().add_line((-5,8),(25,8),dxfattribs={'lineweight':250})
    path=tmp_path/'inputs/separation.dxf';doc.saveas(path)
    manifest_path=tmp_path/'manufacturing-job.json';manifest=json.loads(manifest_path.read_text())
    manifest['files']['separation']='inputs/separation.dxf'
    manifest['sha256']['inputs/separation.dxf']=sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    config=default_router();config['alignment_pins'].update(start_x_mm=-10,xy_margin_mm=.1,tool_envelope_diameter_mm=.5)
    config_path=tmp_path/'machining.toml';write_toml(config_path,config)
    output=prepare_router_drafts(tmp_path,config_path)
    report=json.loads((output/'router-report.json').read_text())
    profile=next(p for p in report['programs'] if p['file']=='pcb-profile.mmg.draft')
    assert profile['separation']['paths']==1
    from pcb_isolator.router_review import parse_draft
    segments,_=parse_draft((output/profile['file']).read_text(),[-10,0])
    feeds=[s for s in segments if not s['rapid']]
    assert feeds[0]['from']==[.002,8] and feeds[0]['to']==[19.998,8]
    assert all(box(0,0,20,10).covers(LineString([s['from'],s['to']])) for s in feeds[:2])
    assert any(not box(0,0,20,10).covers(LineString([s['from'],s['to']])) for s in feeds[2:])
    assert 'Separation cuts, then board profile' in (output/'router-review.html').read_text()
    path.write_text('tampered')
    with pytest.raises(ValueError,match='changed'):load_job(tmp_path)
