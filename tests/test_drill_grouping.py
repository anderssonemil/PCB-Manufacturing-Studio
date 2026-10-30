import json
import pytest
from test_job_outputs import make_job
from pcb_isolator.app_backend import read_board,generate,default_router,export_preview
from pcb_isolator.drill_grouping import group_drills,assignments
from pcb_isolator.drills import DrillFeature


def test_grouping_preserves_source_and_positions():
    features=[DrillFeature('a',.4,1,2),DrillFeature('b',.45,3,4),DrillFeature('c',.8,5,6)]
    cfg=default_router();cfg['drilling']['assignments']=[{'source_diameter_mm':.4,'tool_diameter_mm':.5},{'source_diameter_mm':.45,'tool_diameter_mm':.5}]
    groups,sources=group_drills(features,cfg)
    assert len(groups)==2 and len(groups[.5])==2
    assert [f.diameter_mm for f in features]==[.4,.45,.8]
    assert [(f.id,f.x,f.y) for f in groups[.5]]==[('a',1,2),('b',3,4)]
    assert sources[.5]=={.4:1,.45:1}


@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf'),'small'])
def test_invalid_tool_rejected(value):
    cfg=default_router();cfg['drilling']['assignments']=[{'source_diameter_mm':.5,'tool_diameter_mm':value}]
    with pytest.raises(ValueError):assignments(cfg)


def test_combined_tool_pipeline_and_pin_exclusion(tmp_path):
    selection=make_job(tmp_path);board=read_board(tmp_path);cfg=default_router()
    cfg['alignment_pins'].update(tool_envelope_diameter_mm=.5,xy_margin_mm=.1,start_x_mm=-10)
    cfg['drilling']['assignments']=[{'source_diameter_mm':.5,'tool_diameter_mm':.8},{'source_diameter_mm':1,'tool_diameter_mm':.8},
                                    {'source_diameter_mm':3.2,'tool_diameter_mm':4}]
    cfg['drilling']['tools']=[{'diameter_mm':.8,'feed_mm_min':80,'peck_mm':.4}]
    result=generate(board,selection['alignment_ids'],selection['alignment_ids'][0],3.175,
                    {'width':.075,'overlap':33.3333,'lines':1},cfg,make_laser=False,output_folder=tmp_path/'preview')
    report=json.loads((result['record']/'router/router-report.json').read_text())
    drills=[p for p in report['programs'] if p['file'].startswith('pcb-drill')]
    assert len(drills)==1
    drill=drills[0];assert drill['tool_diameter_mm']==.8 and drill['holes']==2
    assert drill['drilling']['feed_mm_min']==80 and drill['drilling']['peck_mm']==.4
    assert drill['source_hole_sizes']==[{'diameter_mm':.5,'count':1},{'diameter_mm':1,'count':1}]
    assert next(p for p in report['programs'] if p['file'].startswith('spoilboard'))['nominal_pin_diameter_mm']==3.175
    assert result['guide'].exists()
    assert 'KiCad hole sizes' in result['guide'].read_text(encoding='utf-8')
    final=export_preview(result,tmp_path/'final')
    assert len(list(final['router'].glob('*.mmg')))==3


def test_table_grouping_highlight_and_preview_reset(tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from pcb_isolator.desktop import Window
    make_job(tmp_path);board=read_board(tmp_path)
    app=QApplication.instance() or QApplication([])
    window=Window();window.loaded(board)
    assert window.drill_table.rowCount()==2
    window.preview_results={'run':tmp_path}
    window.drill_table.cellWidget(0,2).setCurrentText('0.8')
    window.drill_table.cellWidget(1,2).setCurrentText('0.8')
    assert window.preview_results is None
    assert '2 source sizes → 1 PCB drill programs' in window.drill_summary.text()
    window.drill_table.selectRow(0);app.processEvents()
    assert len(window.drill_highlights)==2
    assert all(item.pen().isCosmetic() for item in window.drill_highlights)
    assert window.drill_assignments()[0]['tool_diameter_mm']==.8
    window.toggle_board_hole(board['features'][2].id)
    assert window.drill_table.rowCount()==1
    assert window.drill_assignments()[0]['source_diameter_mm']==1
    assert window.drill_assignments()[0]['tool_diameter_mm']==.8
    window.loaded(board)  # Old highlight objects must not survive a scene reload.
    assert window.drill_table.rowCount()==2
    window.close()
