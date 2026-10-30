import json,socket,threading
import pytest
from shapely.geometry import box,LineString
from pcb_isolator.helix import DEFAULTS,validate,quantize,prepare,send

def test_grid_duplicates_bounds_and_collapsed_paths():
 s=validate(DEFAULTS)
 routes,report=quantize([LineString([(0,1),(1,1)]),LineString([(0,1.005),(1,1.005)])],(0,0,1,2),[],s)
 assert len(routes)==2 and report['duplicate_exposures']==1
 assert report['maximum_rounding_mm']<=report['grid_mm']*2**.5/2+1e-10
 with pytest.raises(ValueError,match='negative'):validate(dict(DEFAULTS,x=-1))
 with pytest.raises(ValueError,match='fit'):quantize([LineString([(0,0),(1000,0)])],(0,0,1,1),[],s)
 with pytest.raises(ValueError,match='collapse'):quantize([LineString([(0,0),(.001,0)])],(0,0,1,1),[],s)

def sample(folder,settings=DEFAULTS):
 return prepare(box(0,0,10,10),[LineString([(0,0),(10,0),(10,10)])],[],folder,settings,'sample')

def test_offline_packet_and_tamper_block(tmp_path):
 review=sample(tmp_path);data=(tmp_path/'laser-job.prn').read_bytes()
 assert b'ZS010;' in data and b'YP008;' in data and b'XR2500;' in data and b'WA' not in data
 assert 'exact quantized' in review.read_text(encoding='utf-8')
 assert json.loads((tmp_path/'helix-job.json').read_text())['grid_mm']==pytest.approx(25.4/600)
 (tmp_path/'laser-job.prn').write_bytes(data+b'changed')
 with pytest.raises(ValueError,match='changed'):send(tmp_path,DEFAULTS)

def test_local_acknowledged_transfer_exact(tmp_path,monkeypatch):
 listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(5)
 settings=dict(DEFAULTS,host='127.0.0.1',port=listener.getsockname()[1]);sample(tmp_path,settings)
 received=[];errors=[]
 def server():
  try:
   sock,_=listener.accept();sock.settimeout(5)
   with sock:
    f=sock.makefile('rb');assert f.readline()==b'\2\n';sock.sendall(b'\0')
    header=f.readline();count=int(header[1:].split()[0]);sock.sendall(b'\0');assert len(f.read(count))==count;assert f.read(1)==b'\0';sock.sendall(b'\0')
    header=f.readline();count=int(header[1:].split()[0]);sock.sendall(b'\0');received.append(f.read(count));sock.sendall(b'\0')
  except Exception as error:errors.append(error)
  finally:listener.close()
 thread=threading.Thread(target=server);thread.start();progress=[]
 monkeypatch.setattr('pcb_isolator.helix.settings_root',lambda:tmp_path.parent)
 message=send(tmp_path,settings,lambda n,text:progress.append(n));thread.join(6)
 assert not thread.is_alive() and not errors
 assert received==[(tmp_path/'laser-job.prn').read_bytes()]
 assert progress[0]==0 and progress[-1]==100 and 'acknowledged' in message

def test_direct_backend_bypasses_dxf_and_delivers(tmp_path,monkeypatch):
 from test_job_outputs import make_job
 from pcb_isolator import app_backend as backend
 make_job(tmp_path);board=backend.read_board(tmp_path)
 monkeypatch.setattr(backend,'prepare_outputs',lambda *a,**k:pytest.fail('DXF must not run'))
 laser=dict(width=.075,overlap=33,lines=1,format='direct',helix=DEFAULTS)
 result=backend.generate(board,[],None,3.175,laser,backend.default_router(),make_router=False,output_folder=tmp_path/'preview')
 assert (result['laser']/'laser-job.prn').exists()
 assert not list(result['laser'].glob('*.dxf')) and not list(result['laser'].glob('*.svg'))
 final=backend.export_preview(result,tmp_path/'final',laser_format='direct')
 assert (final['laser']/'laser-job.prn').read_bytes()==(result['laser']/'laser-job.prn').read_bytes()
 assert 'Direct Helix' in final['guide'].read_text(encoding='utf-8')


def test_collapsed_fragment_only_skipped_when_burn_covers_it():
 s=validate(DEFAULTS)
 routes,report=quantize([LineString([(0,1),(1,1)]),LineString([(.5,1.005),(.501,1.005)])],(0,0,1,2),[],s,coverage_radius_mm=.1)
 assert len(routes)==1 and report['covered_subgrid_fragments']==1
 with pytest.raises(ValueError,match='without a covering'):
  quantize([LineString([(0,1),(1,1)]),LineString([(.5,1.5),(.501,1.5)])],(0,0,1,2),[],s,coverage_radius_mm=.1)


def test_tiny_filter_explicit_limited_and_reported():
 s=validate(DEFAULTS);paths=[LineString([(0,1),(1,1)]),LineString([(.5,1.5),(.51,1.5)])]
 routes,report=quantize(paths,(0,0,1,2),[],s,coverage_radius_mm=.1,ignore_tiny_mm=.03)
 assert len(routes)==1 and len(report['ignored_tiny_fragments'])==1
 assert report['ignored_tiny_fragments'][0]['length_mm']==pytest.approx(.01)
 with pytest.raises(ValueError,match='collapse'):quantize(paths,(0,0,1,2),[],s,coverage_radius_mm=.1,ignore_tiny_mm=.005)

def test_ellipse_and_combined_neighbor_footprints_cover_fragment():
 s=validate(DEFAULTS)
 # Covered by the wider Y footprint, not by the minimum scalar radius.
 routes,report=quantize([LineString([(0,1),(1,1)]),LineString([(.5,1.14),(.501,1.14)])],(0,0,1,2),[],s,coverage_radius_mm=.1,coverage_radius_y_mm=.18)
 assert report['covered_subgrid_fragments']==1 and not report['ignored_tiny_fragments']
 # Each neighboring stroke covers a different part of this collapsed path.
 paths=[LineString([(0,1),(1,1)]),LineString([(0,1.2),(1,1.2)]),LineString([(.5,1.095),(.5,1.105)])]
 routes,report=quantize(paths,(0,0,1,2),[],s,coverage_radius_mm=.12)
 assert report['covered_subgrid_fragments']==1

def test_failure_has_visual_diagnostic_without_printer_file(tmp_path):
 from pcb_isolator.helix import LaserGridError
 with pytest.raises(LaserGridError) as caught:
  prepare(box(0,0,2,2),[LineString([(.5,.5),(.501,.5)])],[],tmp_path,dict(DEFAULTS,ignore_tiny_fragments=False),'tiny')
 assert caught.value.laser_diagnostic['issues']
 assert (tmp_path/'Issues.html').exists() and (tmp_path/'laser-grid-issues.json').exists()
 assert not (tmp_path/'laser-job.prn').exists()
 assert 'Locate 1' in (tmp_path/'Issues.html').read_text(encoding='utf-8')


def test_cutout_fit_error_explains_tool_size_and_location():
 from pcb_isolator.router import compensated_profiles
 outer=box(0,0,10,10).exterior;hole=box(2,2,3.2,3.2).exterior
 with pytest.raises(ValueError,match='Tool diameter 2.54 mm; internal cutout bounds 1.200 x 1.200 mm at source X2.600, Y2.600'):
  compensated_profiles([outer,hole],2.54)
 assert len(compensated_profiles([outer,hole],1))==2


def test_filter_retry_reuses_plan_without_isolation_regeneration(tmp_path,monkeypatch):
 from test_job_outputs import make_job
 from pcb_isolator import app_backend as backend
 from pcb_isolator.helix import LaserGridError
 make_job(tmp_path);board=backend.read_board(tmp_path)
 contours=[LineString([(0,0),(1,0)]),LineString([(.5,1),(.501,1)])]
 monkeypatch.setattr(backend,'preview_paths',lambda *a:contours)
 laser=dict(width=.075,overlap=33,lines=1,format='direct',helix=dict(DEFAULTS,ignore_tiny_fragments=False))
 with pytest.raises(LaserGridError) as caught:
  backend.generate(board,[],None,3.175,laser,backend.default_router(),make_router=False,output_folder=tmp_path/'preview')
 assert caught.value.prepared_contours is contours
 monkeypatch.setattr(backend,'preview_paths',lambda *a:pytest.fail('Slow isolation step must not repeat'))
 laser['helix']['ignore_tiny_fragments']=True
 result=backend.generate(board,[],None,3.175,laser,backend.default_router(),make_router=False,output_folder=tmp_path/'preview',prepared_contours=caught.value.prepared_contours)
 report=json.loads((result['laser']/'helix-job.json').read_text())
 assert len(report['ignored_tiny_fragments'])==1


def test_filter_refresh_preserves_router_bytes_and_skips_planning(tmp_path,monkeypatch):
 from test_job_outputs import make_job
 from pcb_isolator import app_backend as backend
 make_job(tmp_path);board=backend.read_board(tmp_path);cache=[]
 laser=dict(width=.075,overlap=33,lines=1,format='direct',helix=DEFAULTS)
 first=backend.generate(board,[],None,3.175,laser,backend.default_router(),registration_preview=True,output_folder=tmp_path/'preview',on_contours=cache.append)
 before={p.name:p.read_bytes() for p in first['router'].iterdir() if p.is_file()}
 monkeypatch.setattr(backend,'preview_paths',lambda *a:pytest.fail('Isolation planning must not repeat'))
 monkeypatch.setattr(backend,'prepare_router_drafts',lambda *a,**k:pytest.fail('Router planning must not repeat'))
 result=backend.refresh_laser_filter(board,first,dict(DEFAULTS,tiny_fragment_mm=.05),cache[0])
 assert before=={p.name:p.read_bytes() for p in result['router'].iterdir() if p.is_file()}
 assert first['run']!=result['run'] and first['laser_review'].exists()
 assert json.loads((result['laser']/'helix-job.json').read_text())['settings']['tiny_fragment_mm']==.05

@pytest.mark.parametrize('broken',['laser','router','both'])
def test_modules_fail_independently_and_keep_other_review(tmp_path,monkeypatch,broken):
 from test_job_outputs import make_job
 from pcb_isolator import app_backend as backend
 make_job(tmp_path);board=backend.read_board(tmp_path)
 def fail(*a,**k):raise ValueError('Deliberate diagnostic failure')
 if broken in ('laser','both'):monkeypatch.setattr('pcb_isolator.helix.prepare',fail)
 if broken in ('router','both'):monkeypatch.setattr(backend,'prepare_router_drafts',fail)
 laser=dict(width=.075,overlap=33,lines=1,format='direct',helix=DEFAULTS)
 result=backend.generate(board,[],None,3.175,laser,backend.default_router(),registration_preview=True,output_folder=tmp_path/'preview',allow_partial=True)
 assert result['partial_preview']
 assert result['laser_review'].exists() and result['router_review'].exists()
 if broken=='laser':assert 'router' in result and 'laser' not in result
 if broken=='router':assert 'laser' in result and 'router' not in result
 if broken=='both':assert 'laser' not in result and 'router' not in result
 with pytest.raises(ValueError,match='failed module'):backend.export_preview(result,tmp_path/'final')

def test_specific_internal_cutouts_can_be_omitted_but_outer_remains():
 from pcb_isolator.router import compensated_profiles,CutoutFitError,cutout_info
 outer=box(0,0,10,10);hole=box(2,2,3,3)
 with pytest.raises(CutoutFitError) as caught:compensated_profiles([outer.exterior,hole.exterior],2)
 issues=caught.value.feature_diagnostic['issues'];assert len(issues)==1
 paths=compensated_profiles([outer.exterior,hole.exterior],2,[{'id':issues[0]['id']},{'id':cutout_info(outer)['id']}])
 assert len(paths)==1 and paths[0]['kind']=='outside'


def test_live_filter_ui_refreshes_without_generate_click(tmp_path,monkeypatch):
 import os
 os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
 from PySide6.QtWidgets import QApplication
 from pcb_isolator.desktop import Window
 from pcb_isolator import app_backend as backend
 from test_job_outputs import make_job
 app=QApplication.instance() or QApplication([])
 make_job(tmp_path);board=backend.read_board(tmp_path);window=Window();window.loaded(board)
 laser=window.laser_values();contours=[LineString([(8,3),(12,3)])]
 result=backend.generate(board,[],None,3.175,laser,backend.default_router(),make_router=False,output_folder=tmp_path/'preview',prepared_contours=contours)
 window.preview_results=result;window.isolation_cache=(window.plan_key(board,laser),contours)
 calls=[];opened=[]
 def refresh(b,paths,settings,plan):
  calls.append((settings['tiny_fragment_mm'],plan));return result
 monkeypatch.setattr(backend,'refresh_laser_filter',refresh)
 monkeypatch.setattr(window,'task',lambda action,callback,message:callback(action()))
 monkeypatch.setattr(window,'open_result',lambda key:opened.append(key))
 window.tiny_threshold.setValue(.05)
 assert window.filter_timer.isActive()
 window.filter_timer.stop();window.refresh_filter()
 assert calls==[(.05,contours)] and opened==['laser_review']
 assert window.generate_button.text()=='Generate outputs'
 window.close()

def test_default_filter_migrates_old_saved_off_setting(tmp_path,monkeypatch):
 import os
 os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
 from PySide6.QtWidgets import QApplication
 from pcb_isolator.desktop import Window
 monkeypatch.setattr('pcb_isolator.runtime.settings_root',lambda:tmp_path)
 (tmp_path/'helix-settings.json').write_text(json.dumps(dict(DEFAULTS,ignore_tiny_fragments=False)))
 app=QApplication.instance() or QApplication([]);window=Window()
 assert window.ignore_tiny.isChecked()
 window.restore_helix(dict(DEFAULTS,ignore_tiny_fragments=False,tiny_filter_default_version=1))
 assert not window.ignore_tiny.isChecked()
 window.close()


def test_filter_removes_whole_short_fragments_not_edges_of_long_routes():
 s=validate(DEFAULTS)
 paths=[LineString([(0,1),(1,1)]),LineString([(.02,1.5),(.04,1.5)]),LineString([(.1,.1),(.12,.1),(1,.1)])]
 routes,report=quantize(paths,(0,0,1,2),[],s,coverage_radius_mm=.01,ignore_tiny_mm=.03)
 assert len(report['ignored_tiny_fragments'])==1
 assert report['ignored_tiny_fragments'][0]['reason']=='short_path'
 assert len(routes)==2


def test_review_embeds_exact_optimized_device_paths(tmp_path):
 import re
 review=sample(tmp_path)
 text=review.read_text(encoding='utf-8')
 embedded=json.loads(re.search(r'<script id="laser-playback-data" type="application/json">(.*?)</script>',text).group(1))
 emitted=[[[int(v) for v in point.split(',')] for point in line.split()] for line in (tmp_path/'helix-paths.tsv').read_text().splitlines()[1:]]
 assert embedded['routes']==emitted
 assert embedded['optimization']['after_travel_mm']<=embedded['optimization']['before_travel_mm']
 assert 'laser-play' in text and 'laser-time' in text and 'Predicted burn width' in text
 assert 'fetch(' not in text and 'https://' not in text
