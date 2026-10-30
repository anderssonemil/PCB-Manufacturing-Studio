import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from pcb_isolator.desktop import Window
from pcb_isolator.app_backend import read_board


def test_desktop_loads_board_and_changes_alignment(monkeypatch):
    job=Path('jobs/Transducer Connectors and ADC board/20261018T192509Z-9e5426')
    if not job.exists():pytest.skip('Personal job absent')
    app=QApplication.instance() or QApplication([])
    window=Window();window.loaded(read_board(job))
    assert window.table.rowCount()==52
    assert len(window.selected_ids())==2
    assert window.origin.count()==2
    window.show();app.processEvents()
    selected_rows=[row for row in range(window.table.rowCount()) if window.table.cellWidget(row,0).isChecked()]
    for row in selected_rows:
        checkbox=window.table.cellWidget(row,0)
        QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton,pos=QPoint(8,checkbox.height()//2))
    assert window.selected_ids()==[]
    assert window.origin.count()==0
    for row in selected_rows:
        checkbox=window.table.cellWidget(row,0)
        QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton,pos=QPoint(8,checkbox.height()//2))
    assert len(window.selected_ids())==2
    assert window.origin.count()==2
    window.lines.setValue(3)
    assert window.laser_values()['lines']==3
    assert window.generate_button.isEnabled()
    from PySide6.QtWidgets import QMessageBox,QPushButton
    assert all(button.toolTip() for button in window.findChildren(QPushButton))
    captured=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(window,'task',lambda *args:captured.append(args))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    from pcb_isolator import app_backend
    monkeypatch.setattr(app_backend,'generate',lambda *args,**kwargs:{'router':Path('router'),'run':kwargs['output_folder']})
    released=[]
    monkeypatch.setattr(app_backend,'export_preview',lambda result,output,**kwargs:released.append(result) or result)
    monkeypatch.setattr(window,'open_result',lambda key:None)
    window.generate();assert len(captured)==1
    result=captured[0][0]()
    assert not released
    captured[0][1](result)
    assert window.generate_button.text()=='Generate outputs'
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Cancel)
    window.generate();assert len(captured)==1
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    window.generate()
    captured[1][0]()
    assert len(released)==1
    window.lines.setValue(4)
    assert window.generate_button.text()=='Generate preview'
    assert window.preview_results is None
    window.close()


def test_board_click_and_selection_invalidate_preview(tmp_path,monkeypatch):
    from test_job_outputs import make_job
    from PySide6.QtWidgets import QMessageBox
    make_job(tmp_path)
    app=QApplication.instance() or QApplication([])
    window=Window();window.loaded(read_board(tmp_path));window.show();app.processEvents()
    assert window.table.rowCount()==4  # Includes undersized holes.
    hole=window.board['features'][2]
    position=window.view.mapFromScene(hole.x,-hole.y)
    window.preview_results={'run':tmp_path};window.generate_button.setText('Generate outputs')
    QTest.mouseClick(window.view.viewport(),Qt.MouseButton.LeftButton,pos=position)
    assert hole.id in window.selected_ids()
    assert window.preview_results is None
    assert window.generate_button.text()=='Generate preview'
    QTest.mouseClick(window.view.viewport(),Qt.MouseButton.LeftButton,pos=position)
    assert hole.id not in window.selected_ids()
    for row in range(window.table.rowCount()):window.table.cellWidget(row,0).setChecked(False)
    tasks=[];questions=[]
    monkeypatch.setattr(window,'task',lambda *args:tasks.append(args))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:questions.append(args[2]) or QMessageBox.StandardButton.Cancel)
    window.generate();assert not tasks and 'Continue without picking holes?' in questions[-1]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(window,'open_result',lambda key:None)
    window.generate();assert len(tasks)==1
    tasks[-1][1]({'run':tmp_path,'registration_preview':True})
    assert window.preview_results is None and window.generate_button.text()=='Generate preview'
    window.toggle_board_hole(window.board['features'][0].id)
    window.toggle_board_hole(window.board['features'][1].id)
    window.generate();assert len(tasks)==2
    window.close()


def test_reference_visibility_preserves_ready_preview(tmp_path,monkeypatch):
    from test_job_outputs import make_job
    make_job(tmp_path);board=read_board(tmp_path)
    board['reference_layers']=[dict(name='F.SilkS',label='Front silk',id=37)]
    svg=tmp_path/'silk.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210"><g id="reference-art"><path d="M3,3 L17,3" stroke="white" stroke-width=".1"/></g></svg>')
    app=QApplication.instance() or QApplication([]);window=Window();window.loaded(board)
    ready={'router_review':tmp_path/'review.html'};window.preview_results=ready;window.results=ready
    cache=object();window.isolation_cache=cache
    monkeypatch.setattr('pcb_isolator.reference_layers.export_layer',lambda job,name:svg)
    monkeypatch.setattr(window,'task',lambda action,done,message:done(action()))
    window.open_reference_layers();window.reference_checks['F.SilkS'].setChecked(True)
    item=window.view.reference_items['F.SilkS'];assert item.isVisible()
    assert item.sceneBoundingRect().x()==pytest.approx(3,abs=.1)
    assert item.sceneBoundingRect().width()==pytest.approx(14.1,abs=.000001)
    assert window.preview_results is ready and window.isolation_cache is cache
    window.reference_checks['F.SilkS'].setChecked(False);assert not item.isVisible()
    assert window.preview_results is ready
    # Existing overlays also survive isolation-path redraws.
    window.view.isolation([]);assert 'F.SilkS' in window.view.reference_items
    window.loaded(board);assert window.reference_dialog is None and not window.view.reference_items
    window.close()
