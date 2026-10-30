import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from hashlib import sha256
import json
import pytest
from PySide6.QtWidgets import QApplication
from pcb_isolator.desktop import Window
from pcb_isolator.app_backend import read_board,generate,default_router,export_preview
from test_job_outputs import make_job


def test_format_changes_keep_review_but_geometry_changes_invalidate(tmp_path):
    make_job(tmp_path);app=QApplication.instance() or QApplication([])
    window=Window();assert window.laser_format.currentData()=='direct'
    assert not window.laser_format.isEnabled()
    window.loaded(read_board(tmp_path))
    reviewed={'run':tmp_path/'review'};window.preview_results=reviewed;window.laser_ready=reviewed
    window.generate_button.setText('Generate outputs')
    window.helix_fields['power'].setValue(window.helix_fields['power'].value()+1)
    assert window.preview_results is None and window.laser_ready is None
    assert not window.send_laser_button.isEnabled()
    window.close()


def test_origin_follows_selected_pin_and_empty_selection_uses_copper_lower_left(tmp_path):
    make_job(tmp_path);app=QApplication.instance() or QApplication([])
    window=Window();board=read_board(tmp_path);window.loaded(board);window.show();app.processEvents()
    for index in range(window.origin.count()):
        window.origin.setCurrentIndex(index)
        feature=next(f for f in board['features'] if f.id==window.origin.currentData())
        assert window.view.origin_point==(feature.x,feature.y)
        assert not window.view.origin_provisional
    for row in range(window.table.rowCount()):window.table.cellWidget(row,0).setChecked(False)
    assert window.view.origin_point==board['copper'].bounds[:2]
    assert window.view.origin_provisional
    window.toggle_board_hole(board['features'][1].id)
    assert window.view.origin_point==(17,3)
    window.make_router.setChecked(False);assert not window.view.show_router_origin
    window.make_router.setChecked(True);assert window.view.show_router_origin
    app.processEvents();window.close()


def test_change_formats_after_review_without_regenerating_paths(tmp_path,monkeypatch):
    selection=make_job(tmp_path);board=read_board(tmp_path)
    router=default_router();router['alignment_pins'].update(xy_margin_mm=.1,tool_envelope_diameter_mm=.5,start_x_mm=-10)
    result=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,
        {'width':.075,'overlap':33.3333,'lines':1,'format':'dxf'},router,output_folder=tmp_path/'preview')
    assert (result['laser']/'laser-isolation-and-marks.svg').is_file()
    assert (result['laser']/'laser-isolation-and-marks.dxf').is_file()
    originals={p.name:p.read_bytes() for p in result['router'].glob('*.mmg.draft')}
    original_dxf=(result['laser']/'laser-isolation-and-marks.dxf').read_bytes()
    original_svg=(result['laser']/'laser-isolation-and-marks.svg').read_bytes()
    import pcb_isolator.app_backend as backend
    def forbidden(*a,**k):raise AssertionError('Geometry should not regenerate')
    monkeypatch.setattr(backend,'prepare_outputs',forbidden)
    monkeypatch.setattr(backend,'prepare_router_drafts',forbidden)
    for format,extensions in [('svg',{'.svg'}),('both',{'.svg','.dxf'}),('dxf',{'.dxf'})]:
        final=export_preview(result,tmp_path/('final-'+format),laser_format=format)
        assert {p.suffix for p in final['laser'].iterdir() if p.suffix!='.html'}==extensions
        if format!='svg':assert (final['laser']/'laser-isolation-and-marks.dxf').read_bytes()==original_dxf
        if format!='dxf':assert (final['laser']/'laser-isolation-and-marks.svg').read_bytes()==original_svg
        mapping=json.loads((result['record']/'release.json').read_text())['program_names']
        for old,new in mapping.items():assert (final['router']/new).read_bytes()==originals[old]
        assert final['laser_review'].read_bytes()==result['laser_review'].read_bytes()
        assert final['router_review'].read_bytes()==result['router_review'].read_bytes()
        guide=final['guide'].read_text(encoding='utf-8')
        assert ('Open Laser/laser-isolation-and-marks.svg' in guide)==(format!='dxf')
    assert (result['laser']/'laser-isolation-and-marks.svg').read_bytes()==original_svg
    assert (result['laser']/'laser-isolation-and-marks.dxf').read_bytes()==original_dxf
    with pytest.raises(ValueError,match='Choose DXF'):export_preview(result,tmp_path/'invalid',laser_format='dwg')
    (result['laser']/'laser-isolation-and-marks.svg').write_text('tampered')
    with pytest.raises(ValueError,match='Preview files changed'):export_preview(result,tmp_path/'tampered',laser_format='dxf')
