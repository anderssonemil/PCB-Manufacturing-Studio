"""Frozen GUI entry point; diagnostic mode verifies the distributed binary."""
import json
import os
from pathlib import Path
import shutil
import sys
import traceback


def self_test(source,destination):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    os.environ['PCB_ISOLATOR_HOME']=str(destination/'settings')
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase,QFont
    from pcb_isolator import app_backend as backend
    from pcb_isolator.desktop import Window,STYLE
    from pcb_isolator.demo import create_demo_job
    job=destination/'job'
    if source:
        job.mkdir();shutil.copyfile(Path(source)/'manufacturing-job.json',job/'manufacturing-job.json')
        shutil.copytree(Path(source)/'inputs',job/'inputs')
        if (Path(source)/'source').is_dir():shutil.copytree(Path(source)/'source',job/'source')
    else:create_demo_job(job)
    board=backend.read_board(job)
    eligible=[f.id for f in board['features'] if f.end is None and f.diameter_mm>=3.175]
    if len(eligible)<2:raise ValueError('Self-test sample needs two suitable alignment holes.')
    ids=eligible[:2];router=backend.default_router();router['alignment_pins']['start_x_mm']=-10
    laser=dict(width=.075,overlap=33.3333,lines=2,format='direct',helix={'host':'127.0.0.1'})
    preview=backend.generate(board,ids,ids[0],3.175,laser,router,output_folder=job/'outputs/preview')
    final=backend.export_preview(preview,destination/'Manufacturing Output')
    assert list(final['router'].glob('*.mmg'))
    assert (final['laser']/'laser-job.prn').is_file()
    assert 'paper-print-data' in final['laser_review'].read_text(encoding='utf-8')
    assert 'paper-print-data' in final['router_review'].read_text(encoding='utf-8')
    assert 'Mark done &amp; Next' in final['guide'].read_text(encoding='utf-8')
    from pcb_isolator.review_zip import save_router_review_zip
    save_router_review_zip(final['router_review'],destination/'router-review.zip')
    app=QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'
    if font.exists():QFontDatabase.addApplicationFont(str(font));app.setFont(QFont('Segoe UI',10))
    window=Window();window.loaded(board);window.show();app.processEvents()
    svg=destination/'reference-test.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><g id="reference-art"><path d="M3,3 L17,3" stroke="white"/></g></svg>',encoding='utf-8')
    assert window.view.show_reference('offline SVG check',svg)
    assert window.table.rowCount()>=2 and (backend.ROOT/'Help.html').exists()
    window.grab().save(str(destination/'window.png'));window.close()
    (destination/'result.json').write_text(json.dumps({'success':True,'frozen':getattr(sys,'frozen',False),
        'executable':sys.executable,'programs':[p.name for p in final['router'].glob('*.mmg')],
        'python_version':sys.version,'assets':str(backend.ROOT),'direct_encoder':True,'paper_reviews':True,'router_zip':True,'qt_svg':True,'network_contacted':False},indent=2),encoding='utf-8')


if __name__=='__main__':
    try:
        if len(sys.argv) in (3,4) and sys.argv[1]=='--self-test':
            self_test(sys.argv[2] if len(sys.argv)==4 else None,sys.argv[-1])
        else:
            from pcb_isolator.desktop import main
            main()
    except Exception:
        detail=traceback.format_exc()
        if len(sys.argv) in (3,4) and sys.argv[1]=='--self-test':
            folder=Path(sys.argv[-1]);folder.mkdir(parents=True,exist_ok=True)
            (folder/'error.txt').write_text(detail,encoding='utf-8')
        else:
            from PySide6.QtWidgets import QApplication,QMessageBox
            app=QApplication.instance() or QApplication([])
            QMessageBox.critical(None,'PCB Isolator could not start',detail)
        sys.exit(1)
