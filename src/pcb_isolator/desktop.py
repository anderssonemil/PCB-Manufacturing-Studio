"""First Windows desktop interface for the tested PCB manufacturing engines."""
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import sys
import traceback
import uuid

from PySide6.QtCore import Qt,QThread,Signal,QUrl,QTimer,QRectF
from PySide6.QtGui import QColor,QBrush,QPen,QPainterPath,QPainter,QDesktopServices
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QPushButton,QLineEdit,QFileDialog,QGroupBox,QFormLayout,QDoubleSpinBox,
    QSpinBox,QTabWidget,QScrollArea,QCheckBox,QTableWidget,QTableWidgetItem,
    QDialog,QInputDialog,QComboBox,QGraphicsView,QGraphicsScene,QMessageBox,QSplitter,QHeaderView,QProgressBar)

from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem

from . import app_backend as backend


class Worker(QThread):
    succeeded=Signal(object)
    failed=Signal(object)
    transfer=Signal(int,str)
    def __init__(self,action):
        super().__init__();self.action=action
    def run(self):
        try:self.succeeded.emit(self.action())
        except Exception as error:self.failed.emit(error)


class BoardView(QGraphicsView):
    holeClicked=Signal(str)
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor('#111b25'));self.path_items=[];self.hole_items={};self.reference_items={}
        self.round_holes={};self.press_position=None
        self.origin_point=None;self.origin_provisional=True;self.show_router_origin=True
    def mousePressEvent(self,event):
        self.press_position=event.position().toPoint() if event.button()==Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)
    def mouseReleaseEvent(self,event):
        start=self.press_position;self.press_position=None
        super().mouseReleaseEvent(event)
        if event.button()!=Qt.MouseButton.LeftButton or start is None or (event.position().toPoint()-start).manhattanLength()>5:return
        point=event.position().toPoint();candidates=[]
        for id,feature in self.round_holes.items():
            center=self.mapFromScene(feature.x,-feature.y)
            distance=(center-point).manhattanLength()
            radius=max(7,feature.diameter_mm*self.transform().m11()/2+3)
            if distance<=radius:candidates.append((distance,id))
        if candidates:self.holeClicked.emit(min(candidates)[1])
    def wheelEvent(self,event):
        scale=1.15 if event.angleDelta().y()>0 else 1/1.15
        if .1<self.transform().m11()*scale<50000:self.scale(scale,scale)
    def fit(self):
        bounds=QRectF()
        for item in self.scene().items():
            if item.isVisible():bounds=bounds.united(item.sceneBoundingRect())
        self.setSceneRect(bounds.adjusted(-3,-3,3,3));self.fitInView(bounds.adjusted(-3,-3,3,3),Qt.AspectRatioMode.KeepAspectRatio)
    def show_reference(self,name,path,opacity=.7):
        item=self.reference_items.get(name)
        if item is None:
            renderer=QSvgRenderer(str(path))
            if not renderer.isValid():raise ValueError('Invalid SVG reference layer: '+name)
            bounds=renderer.boundsOnElement('reference-art')
            item=QGraphicsSvgItem();renderer.setParent(item);item.setSharedRenderer(renderer);item.setElementId('reference-art')
            item.setPos(bounds.x(),bounds.y());item.setZValue(3);item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setToolTip(name+' · reference only');self.scene().addItem(item);self.reference_items[name]=item
        item.setOpacity(opacity);item.setVisible(True)
        return not item.boundingRect().isEmpty()
    def hide_reference(self,name):
        if name in self.reference_items:self.reference_items[name].hide()

    def draw_board(self,board):
        self.scene().clear();self.path_items=[];self.hole_items={};self.reference_items={}
        self.round_holes={f.id:f for f in board.get('alignment_candidates',board['features']) if f.end is None}
        self.copper_origin=board['copper'].bounds[:2]
        self.origin_point=self.copper_origin;self.origin_provisional=True
        geometry=board['copper'].simplify(.003,preserve_topology=True)
        polygons=[geometry] if geometry.geom_type=='Polygon' else geometry.geoms
        path=QPainterPath();path.setFillRule(Qt.FillRule.OddEvenFill)
        for polygon in polygons:
            for ring in [polygon.exterior,*polygon.interiors]:
                points=list(ring.coords);path.moveTo(points[0][0],-points[0][1])
                for x,y in points[1:]:path.lineTo(x,-y)
                path.closeSubpath()
        self.scene().addPath(path,QPen(Qt.PenStyle.NoPen),QBrush(QColor('#c9a060')))
        for boundary in board['outline']:
            points=list(boundary.coords);path=QPainterPath();path.moveTo(points[0][0],-points[0][1])
            for x,y in points[1:]:path.lineTo(x,-y)
            self.scene().addPath(path,QPen(QColor('#e9f0f6'),.09))
        for feature in board.get('alignment_candidates',board['features']):
            r=feature.diameter_mm/2
            item=self.scene().addEllipse(feature.x-r,-feature.y-r,2*r,2*r,QPen(QColor('#56b9ec'),.07),QBrush(QColor('#3484ae66')))
            item.setToolTip(f'{feature.id}\n{feature.diameter_mm:g} mm · X{feature.x:g} Y{feature.y:g}')
            self.hole_items[feature.id]=item
        for line in board.get('separations',[]):
            points=list(line.coords);path=QPainterPath();path.moveTo(points[0][0],-points[0][1])
            for x,y in points[1:]:path.lineTo(x,-y)
            item=self.scene().addPath(path,QPen(QColor('#ec86d8'),.15))
            item.setToolTip('CNC Separation centerline · cut before outer profile with the profile cutter')
        self.fit()
    def set_router_origin_visible(self,visible):
        self.show_router_origin=visible;self.viewport().update()

    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        if not self.show_router_origin or self.origin_point is None:return
        point=self.mapFromScene(self.origin_point[0],-self.origin_point[1])
        x,y=point.x(),point.y()
        painter.save();painter.resetTransform()
        path=QPainterPath();path.moveTo(x-12,y);path.lineTo(x+38,y)
        path.moveTo(x,y+12);path.lineTo(x,y-38)
        path.moveTo(x+31,y-5);path.lineTo(x+38,y);path.lineTo(x+31,y+5)
        path.moveTo(x-5,y-31);path.lineTo(x,y-38);path.lineTo(x+5,y-31)
        painter.setPen(QPen(QColor('#101820'),7));painter.drawPath(path)
        painter.setPen(QPen(QColor('#ffe45c'),2));painter.drawPath(path)
        painter.setBrush(QBrush(QColor('#ffe45c')));painter.drawEllipse(point,3,3)
        label='XY 0 - copper lower-left (provisional)' if self.origin_provisional else 'XY 0 - selected pin'
        tx=min(max(6,x+16),max(6,self.viewport().width()-260));ty=min(max(25,y-18),self.viewport().height()-8)
        painter.fillRect(tx-3,ty-15,255,20,QColor('#15202b'))
        painter.setPen(QColor('#ffe45c'));painter.drawText(tx,ty,label)
        painter.drawText(x+40,y+5,'+X');painter.drawText(x+5,y-40,'+Y')
        painter.restore()

    def selection(self,ids,origin):
        feature=self.round_holes.get(origin) if origin in ids else None
        self.origin_point=(feature.x,feature.y) if feature else getattr(self,'copper_origin',None)
        self.origin_provisional=feature is None
        self.viewport().update()
        for id,item in self.hole_items.items():
            color='#8bafff' if id==origin else '#56e1a3' if id in ids else '#56b9ec'
            pen=QPen(QColor('#ffffff' if id==origin else '#baff00' if id in ids else color),4 if id in ids else 1)
            pen.setCosmetic(True)
            item.setPen(pen)
            item.setZValue(20 if id in ids else 2)
            item.setBrush(QBrush(QColor('#99baff00' if id in ids else '#3484ae44')))
    def isolation(self,contours):
        for item in self.path_items:self.scene().removeItem(item)
        self.path_items=[]
        for index,contour in enumerate(contours):
            path=QPainterPath()
            for line in (contour.geoms if hasattr(contour,'geoms') else [contour]):
                points=list(line.simplify(.002).coords)
                if not points:continue
                path.moveTo(points[0][0],-points[0][1])
                for x,y in points[1:]:path.lineTo(x,-y)
            fallback=index in getattr(contours,'fallback_indices',set())
            item=self.scene().addPath(path,QPen(QColor('#ff7900' if fallback else '#3bd7ce'),.025))
            if fallback:item.setToolTip('Narrow-gap fallback: nearly overlapping passes; physical burn removes intended copper.')
            self.path_items.append(item)


class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('PCB Isolator · Manufacturing workspace');self.resize(1480,920)
        self.isolation_cache=None;self.filter_source=None;self.filter_timer=QTimer(self);self.filter_timer.setSingleShot(True);self.filter_timer.timeout.connect(self.refresh_filter)
        self.laser_issue_items=[];self.laser_ready=None;self.board=None;self.worker=None;self.results={};self.preview_results=None;self.router=backend.default_router()
        self.router['alignment_pins']['start_x_mm']=-10.0
        self.reference_dialog=None;self.reference_checks={}
        self.fields={};self.busy_widgets=[]
        central=QWidget();self.setCentralWidget(central);outer=QVBoxLayout(central);outer.setContentsMargins(22,18,22,16)
        title=QLabel('PCB Isolator');title.setObjectName('title');outer.addWidget(title)
        self.add_button(outer,'Help / workflow guide',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(backend.ROOT/'Help.html'))))
        outer.addWidget(QLabel('Open a saved board  →  Choose alignment holes  →  Review settings  →  Generate'))
        split=QSplitter();outer.addWidget(split,1)
        left=QWidget();left.setMinimumWidth(290);left.setMaximumWidth(380);l=QVBoxLayout(left);l.setContentsMargins(0,12,12,0)
        project=QGroupBox('1  Project');p=QVBoxLayout(project)
        self.project_name=QLabel('No board loaded');self.project_name.setWordWrap(True);p.addWidget(self.project_name)
        self.project_path=QLineEdit();self.project_path.setReadOnly(True);self.project_path.setPlaceholderText('KiCad board or existing export');p.addWidget(self.project_path)
        self.add_button(p,'Open KiCad board…',self.choose_board)
        self.output_root=QLineEdit();self.output_root.setReadOnly(True);self.output_root.setPlaceholderText('Output location');p.addWidget(self.output_root)
        self.add_button(p,'Choose output folder…',self.choose_output)
        self.more_options=self.add_button(p,'More options ▸',lambda:None)
        self.more_options.setCheckable(True)
        self.extra_project_options=QWidget();extras=QVBoxLayout(self.extra_project_options);extras.setContentsMargins(0,0,0,0)
        self.add_button(extras,'Open existing job…',self.choose_job)
        self.add_button(extras,'Reload latest saved KiCad board',self.import_selected)
        p.addWidget(self.extra_project_options);self.extra_project_options.hide()
        def toggle_project_options(expanded):
            self.extra_project_options.setVisible(expanded)
            self.more_options.setText('More options ▾' if expanded else 'More options ▸')
        self.more_options.toggled.connect(toggle_project_options)
        saved=QLabel('Export uses saved board contents. Save and refill copper zones in KiCad first.');saved.setWordWrap(True);saved.setObjectName('hint');p.addWidget(saved);l.addWidget(project)
        align=QGroupBox('2  Alignment and XY zero');a=QVBoxLayout(align)
        self.pin=QDoubleSpinBox();self.pin.setDecimals(3);self.pin.setRange(.1,20);self.pin.setValue(3.175);self.pin.setSuffix(' mm pins');a.addWidget(self.pin)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Use','Hole Ø','X','Y']);self.table.setMaximumHeight(210)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.table.verticalHeader().hide();a.addWidget(self.table)
        a.addWidget(QLabel('Router XY zero · selected alignment hole'))
        self.origin=QComboBox();a.addWidget(self.origin)
        self.alignment_info=QLabel('Select at least two round mounting holes.');self.alignment_info.setWordWrap(True);a.addWidget(self.alignment_info)
        l.addWidget(align);l.addStretch()
        self.make_laser=QCheckBox('Prepare direct laser job + review');self.make_laser.setChecked(True)
        self.make_router=QCheckBox('Generate router files + review');self.make_router.setChecked(True)
        l.addWidget(self.make_laser);l.addWidget(self.make_router)
        self.generate_button=self.add_button(l,'Generate preview',self.generate);self.generate_button.setObjectName('primary')
        split.addWidget(left)
        middle=QWidget();m=QVBoxLayout(middle);m.setContentsMargins(8,12,8,0)
        self.board_summary=QLabel('Board preview');m.addWidget(self.board_summary)
        toolbar=QHBoxLayout();self.add_button(toolbar,'Fit board',lambda:self.view.fit());self.add_button(toolbar,'Update isolation preview',self.update_preview);self.reference_button=self.add_button(toolbar,'Reference layers…',self.open_reference_layers);self.reference_button.setEnabled(False);self.reference_button.setToolTip('Show optional KiCad layers on this main view only. No effect on manufacturing or generated reviews.');m.addLayout(toolbar)
        self.view=BoardView();m.addWidget(self.view,1)
        self.view.holeClicked.connect(self.toggle_board_hole)
        legend=QLabel('Gold: copper · Teal: isolation · Blue: holes · Lime: selected pins · Yellow arrows: router XY zero · Pink: separation · Orange: narrow-gap fallback');legend.setWordWrap(True);m.addWidget(legend)
        m.addWidget(QLabel('Click a round hole to select alignment. Scroll to zoom. Drag to pan.'))
        self.result_text=QLabel('Generated output links will appear here.');self.result_text.setWordWrap(True);m.addWidget(self.result_text)
        links=QHBoxLayout()
        self.result_buttons={}
        for key,label in [('run','Go to output folder'),('guide','Step-by-step guide'),('laser_review','Laser review'),('router_review','Router review')]:
            button=QPushButton(label);button.setEnabled(False);button.clicked.connect(lambda _,k=key:self.open_result(k));links.addWidget(button);self.result_buttons[key]=button
        zip_button=QPushButton('Save router ZIP…');zip_button.setEnabled(False);zip_button.setToolTip('Save the last generated router review HTML as a ZIP for sharing; no machine files.');zip_button.clicked.connect(self.save_router_zip);links.addWidget(zip_button);self.result_buttons['router_zip']=zip_button
        m.addLayout(links)
        split.addWidget(middle)
        settings=QTabWidget();settings.setMinimumWidth(300);settings.setMaximumWidth(380)
        laser,lf=self.form_tab(settings,'Laser')
        self.laser_format=QComboBox()
        self.laser_format.addItem('Direct Helix','direct');self.laser_format.setEnabled(False)
        lf.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        lf.addRow('Output',self.laser_format)
        self.laser_format.setToolTip('SVG and DXF functions are retained but paused in this development build.')
        from .helix import DEFAULTS
        from .runtime import settings_root
        self.helix_settings_path=settings_root()/'helix-settings.json'
        try:device={**DEFAULTS,**json.loads(self.helix_settings_path.read_text(encoding='utf-8'))}
        except (OSError,ValueError):device=DEFAULTS.copy()
        self.helix_host=QLineEdit(device['host']);lf.addRow('Laser IP / hostname',self.helix_host)
        self.helix_fields={}
        for label,key,low,high,dec in [('Port','port',1,65535,0),('Speed (%)','speed',1,100,0),('Power (%)','power',1,100,0),('Frequency (Hz)','frequency',10,5000,0),('Offset right X (mm)','x',0,1000,3),('Offset down Y (mm)','y',0,1000,3),('Bed width (mm)','bed_width',1,2000,2),('Bed height (mm)','bed_height',1,2000,2)]:
            box=self.spin(device[key],low,high,dec);self.helix_fields[key]=box;lf.addRow(label,box);box.valueChanged.connect(self.invalidate_preview)
            box.setToolTip({'speed':'Epilog percentage, not mm/s. Speed 10 is our measured baseline.','power':'Epilog percentage. Default 8%; tested coupon used 6–9%. Burn widths remain provisional.','frequency':'Explicit pulse-frequency setting in Hz. Tested at 2500 Hz.','x':'Positive distance right from the laser reference to the artwork left edge. Zero adds no offset.','y':'Positive distance down from the laser reference to the artwork top edge. Zero adds no offset.','port':'Laser queue TCP port; Helix default 515.','bed_width':'Usable bed width used for software bounds checking. Verify your machine.','bed_height':'Usable bed height used for software bounds checking. Verify your machine.'}[key])
        self.helix_dpi=QComboBox()
        for dpi in (75,150,200,300,400,600,1200):self.helix_dpi.addItem(str(dpi),dpi)
        self.helix_dpi.setCurrentIndex(self.helix_dpi.findData(device['dpi']));lf.addRow('Resolution (DPI)',self.helix_dpi)
        self.helix_dpi.setToolTip('600 DPI = 0.04233 mm coordinate grid; 1200 = 0.02117 mm. Finer positioning does not shrink the laser spot. Changing DPI requires a fresh preview.')
        self.helix_dpi.currentIndexChanged.connect(self.invalidate_preview);self.helix_host.textChanged.connect(self.invalidate_preview)
        self.ignore_tiny=QCheckBox('Filter tiny fragments');self.ignore_tiny.setChecked(device.get('ignore_tiny_fragments',True) if device.get('tiny_filter_default_version')==1 else True);lf.addRow(self.ignore_tiny)
        self.tiny_threshold=self.spin(device.get('tiny_fragment_mm',.03),.001,.1,3);lf.addRow('Maximum tiny length (mm)',self.tiny_threshold)
        self.ignore_tiny.setToolTip('Omit whole short path fragments no longer than this limit, not the individual segments of long routes. Covered details are removed automatically; other omissions remain red in review. The filter is enabled by default and changes update a ready preview without rescanning.')
        self.ignore_tiny.toggled.connect(self.filter_changed);self.tiny_threshold.valueChanged.connect(self.filter_changed)
        check=QPushButton('Check connection');check.clicked.connect(self.check_laser);lf.addRow(check)
        self.send_laser_button=QPushButton('Send to laser');self.send_laser_button.setEnabled(False);self.send_laser_button.clicked.connect(self.send_laser);lf.addRow(self.send_laser_button)
        check.setToolTip('Open and close the configured TCP port without sending job bytes. Does not report whether the laser is running.')
        self.send_laser_button.setToolTip('After preview, confirm and transmit the reviewed job. Progress ends with the queue acknowledgement. Start engraving separately at the Helix panel.')
        lf.addRow(self.wrap('Queues only; start at the Helix panel. Manual focus; autofocus OFF. No air-assist control. Artwork top-left uses X0/Y0 plus these positive offsets. Router pin datum is separate.'))
        self.lines=QSpinBox();self.lines.setRange(1,50);self.lines.setValue(5);lf.addRow('Maximum isolation lines',self.lines)
        self.calibrated=QCheckBox('Calibrated directional model · trial');self.calibrated.setChecked(True);lf.addRow(self.calibrated)
        self.width=self.spin(.22,.001,5,3);lf.addRow('Burn width X (mm)',self.width)
        self.width_y=self.spin(.33,.001,5,3);lf.addRow('Burn width Y (mm)',self.width_y)
        self.spacing=self.spin(.020,.001,1,3);lf.addRow('Target spacing (mm)',self.spacing)
        self.overlap=self.spin(33.3333,0,99,4);lf.addRow('Overlap (%)',self.overlap)
        self.overlap.setEnabled(False)
        self.calibrated.toggled.connect(self.laser_model_changed)
        self.width_y.valueChanged.connect(self.invalidate_preview);self.spacing.valueChanged.connect(self.invalidate_preview)
        lf.addRow(self.wrap('Trial X=0.22 / Y=0.33 mm, spacing 0.020 mm. Machine axes must match artwork orientation. Keep the calibrated speed, power and focus. Actual etched dimensions remain unverified. Narrow gaps may fit fewer lanes or none.'))
        router,rf=self.form_tab(settings,'Router')
        self.drill_table=QTableWidget(0,4);self.drill_table.setHorizontalHeaderLabels(['Hole Ø','Count','Drill Ø','Change'])
        self.drill_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.drill_table.verticalHeader().hide();self.drill_table.setMinimumHeight(170);self.drill_table.setMaximumHeight(280)
        self.drill_table.setToolTip('Assign the same drill diameter to multiple source sizes to combine them into one program. Select a row to highlight its holes.')
        self.restore_cutouts_button=QPushButton('Restore omitted internal cutouts');self.restore_cutouts_button.clicked.connect(self.restore_cutouts);rf.addRow(self.restore_cutouts_button)
        rf.addRow(self.wrap('PCB drill groups · millimeters'));rf.addRow(self.drill_table)
        self.drill_summary=self.wrap('Open a board to assign drill sizes.');rf.addRow(self.drill_summary)
        self.drill_table.itemSelectionChanged.connect(self.highlight_drill_group)
        self.drill_highlights=[]
        for label,section,key,low,high,decimals in [
          ('PCB thickness (mm)','board','thickness_mm',.1,20,3),('Breakthrough (mm)','board','breakthrough_mm',0,5,3),
          ('Profile tool Ø (mm)','profile','tool_diameter_mm',.1,20,3),('Profile feed (mm/min)','profile','feed_mm_min',1,10000,1),
          ('Profile plunge (mm/min)','profile','plunge_mm_min',1,5000,1),('Stepdown (mm)','profile','stepdown_mm',.01,10,3),
          ('Drill feed (mm/min)','drilling','feed_mm_min',1,5000,1),('Peck depth · 0 = off','drilling','peck_mm',0,10,3),
          ('Peck retract (mm)','drilling','peck_retract_mm',.01,20,3),('Peck resume gap (mm)','drilling','peck_resume_gap_mm',.01,5,3),
          ('Rapid approach (mm)','machine','approach_mm',.01,10,3),('Travel clearance (mm)','machine','clearance_mm',.1,100,2),
          ('Final park Z (mm)','machine','park_z_mm',.1,100,2),('Spoilboard pin depth (mm)','spoilboard','pin_hole_depth_mm',.1,50,2)]:
            widget=self.spin(self.router[section][key],low,high,decimals);self.fields[(section,key)]=widget;rf.addRow(label,widget)
        rf.addRow(self.wrap('PCB Z0 = board top. Spoilboard Z0 = spoilboard top. Spindle speed is manual; M03/M05 remains automatic.'))
        pins,pf=self.form_tab(settings,'Pins / start')
        for label,key,low,high in [('Ordering reference X (mm)','start_x_mm',-1000,1000),('Ordering reference Y (mm)','start_y_mm',-1000,1000)]:
            widget=self.spin(self.router['alignment_pins'][key],low,high,3);self.fields[('alignment_pins',key)]=widget;pf.addRow(label,widget)
        pf.addRow(self.wrap('Locate the PCB with pins, press the double-sided tape firmly, then REMOVE ALL PINS before machining. There are no pin keepouts or pin-related travel detours.'))
        pf.addRow(self.wrap('After tool-height setting, leave Z at machine maximum. First move is directly to the first hole or cutting start; Z then lowers there. Ordering reference influences route selection.'))
        split.addWidget(settings);split.setStretchFactor(1,1);split.setSizes([320,800,330])
        status=QHBoxLayout();self.status=QLabel('Ready · Open a KiCad board or an existing export.');self.status.setWordWrap(True);status.addWidget(self.status,1)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setMaximumWidth(160);self.progress.hide();status.addWidget(self.progress);outer.addLayout(status)
        self.busy_widgets=[left,settings,self.view,self.reference_button,zip_button]
        self.table.itemChanged.connect(self.selection_changed);self.origin.currentIndexChanged.connect(self.origin_changed);self.pin.valueChanged.connect(self.populate_holes)
        self.generate_button.setEnabled(False)
        for widget in (self.lines,self.width,self.overlap):widget.valueChanged.connect(lambda:self.status.setText('Laser settings changed · Update isolation preview or Generate to apply.'))
        tips={'Open KiCad board…':'Select a saved .kicad_pcb or .kicad_pro and create a fresh manufacturing snapshot.',
              'Open existing job…':'Reopen an earlier manufacturing snapshot. This does not read later KiCad edits.',
              'Reload latest saved KiCad board':'Export a new snapshot from the original KiCad file, including its latest saved changes. Save and refill zones in KiCad first.',
              'Choose output folder…':'Choose the final folder containing Laser, Router and Start Here.html.',
              'Generate outputs':'Show a setup summary. Confirm once to generate released DXFs, numbered .mmg programs and reviews.',
              'Fit board':'Zoom so the whole board is visible.',
              'Update isolation preview':'Redraw isolation paths using the current laser settings; no output files are generated.',
              'Output folder':'Open the final Manufacturing Output folder.',
              'Laser review':'Open the offline laser preview in your browser.',
              'Router review':'Open router operations, setup details and animated playback with speed and tool-change controls.',
              'Step-by-step guide':'Open Start Here.html: laser, etching, alignment, router tools and completion steps.',
              'Help / workflow guide':'Explain the workflow, buttons, file locations and machine setup.'}
        for button in self.findChildren(QPushButton):button.setToolTip(tips.get(button.text(),button.text()))
        self.lines.setToolTip('Maximum shared lane count in close gaps. The calibrated model adapts count and spacing locally; broad areas keep capped bands near each boundary.')
        self.width.setToolTip('Measured width of paint removed by one laser pass, in millimeters.')
        self.overlap.setToolTip('Overlap between neighboring laser passes; higher values place them closer together.')
        self.table.setToolTip('Select round holes here or click them on the board. Smaller holes are flagged and require manual preparation for the pins.')
        self.origin.setToolTip('The selected hole at which you set router X=0 and Y=0.')
        for (section,key),widget in self.fields.items():widget.setToolTip(f'{section.title()}: {key.replace("_"," ")}. See Help for setup and units.')
        for widget in (self.lines,self.width,self.overlap,self.pin,*self.fields.values()):widget.valueChanged.connect(self.invalidate_preview)
        self.origin.currentIndexChanged.connect(self.invalidate_preview)
        self.table.itemChanged.connect(self.invalidate_preview)
        self.make_laser.toggled.connect(self.invalidate_preview);self.make_router.toggled.connect(self.invalidate_preview)
        self.make_router.toggled.connect(self.view.set_router_origin_visible)
        self.output_root.textChanged.connect(self.invalidate_preview)
        self.invalidate_preview()
        self.more_options.setToolTip('Show less-used options for reopening an export or reloading the saved KiCad board.')

    def output_format_changed(self,*_):
        if self.preview_results:
            self.status.setText('Output format changed · Reviewed paths kept. Generate outputs is ready.')

    def invalidate_preview(self,*_):
        if hasattr(self,'filter_timer'):self.filter_timer.stop()
        self.filter_source=None
        for item in getattr(self,'laser_issue_items',[]):
            try:self.view.scene().removeItem(item)
            except RuntimeError:pass
        self.laser_issue_items=[]
        self.preview_results=None
        self.laser_ready=None
        if hasattr(self,'send_laser_button'):self.send_laser_button.setEnabled(False)
        self.generate_button.setText('Generate preview')
        self.generate_button.setStyleSheet('background:#326b99;color:white;font-weight:bold;padding:12px')
        self.generate_button.setToolTip('Generate draft laser and router previews. Final output is created in the next stage.')

    def wrap(self,text):
        label=QLabel(text);label.setWordWrap(True);label.setObjectName('hint');return label
    def add_button(self,layout,label,callback):
        button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button);return button
    def spin(self,value,low,high,decimals):
        box=QDoubleSpinBox();box.setDecimals(decimals);box.setRange(low,high);box.setValue(value);box.setKeyboardTracking(False);return box
    def form_tab(self,tabs,title):
        widget=QWidget();form=QFormLayout(widget);form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);tabs.addTab(scroll,title);return widget,form
    def task(self,action,callback,message):
        if self.worker and self.worker.isRunning():return
        self.status.setText(message);self.progress.setRange(0,0);self.progress.show()
        for widget in self.busy_widgets:widget.setEnabled(False)
        self.worker=Worker(action);self.worker.succeeded.connect(callback);self.worker.failed.connect(self.failed);self.worker.transfer.connect(self.transfer_progress)
        self.worker.finished.connect(self.finished);self.worker.start()
    def finished(self):
        self.progress.hide()
        for widget in self.busy_widgets:widget.setEnabled(True)
        self.generate_button.setEnabled(self.board is not None)
        self.reference_button.setEnabled(bool(self.board and self.board.get('reference_layers')))
        self.result_buttons['router_zip'].setEnabled('router_review' in self.results)
        self.send_laser_button.setEnabled(self.laser_ready is not None)
    def failed(self,message):
        if getattr(message,'reference_layer',None):
            name=message.reference_layer;check=self.reference_checks.get(name)
            if check:check.blockSignals(True);check.setChecked(False);check.blockSignals(False)
            self.status.setText('Reference layer unavailable · '+str(message));QMessageBox.warning(self,'Reference layer',str(message));return
        for item in self.laser_issue_items:
            try:self.view.scene().removeItem(item)
            except RuntimeError:pass
        self.laser_issue_items=[]
        if hasattr(message,'resume_router'):
            issues=getattr(message,'feature_diagnostic',{}).get('issues',[])
            locations=issues
            if not locations and hasattr(message,'diagnostic') and message.diagnostic.get('closest_xy'):locations=[dict(source_center=message.diagnostic['closest_xy'])]
            for issue in locations:
                x,y=issue['source_center'];path=QPainterPath();path.addEllipse(x-.7,-y-.7,1.4,1.4);path.moveTo(x+1.3,-y-1.3);path.lineTo(x+.4,-y-.4)
                pen=QPen(QColor('#ff3333'),2);pen.setCosmetic(True);item=self.view.scene().addPath(path,pen);item.setZValue(1000);self.laser_issue_items.append(item)
            box=QMessageBox(self);box.setWindowTitle('Router feature needs a decision');box.setIcon(QMessageBox.Icon.Warning);box.setText(str(message))
            box.setInformativeText('Marked internal cutouts can be omitted: their material will remain uncut. Continuing reuses the calculated isolation plan.' if issues else 'The other review remains available. Change the reported setup or continue with laser only. Physical pin collisions and invalid outer profiles cannot be bypassed.')
            omit=box.addButton(f'Omit these {len(issues)} cutouts and continue',QMessageBox.ButtonRole.AcceptRole) if issues else None
            tool=box.addButton('Change profile tool…',QMessageBox.ButtonRole.ActionRole) if issues else None
            laser=box.addButton('Continue laser preview only',QMessageBox.ButtonRole.ActionRole) if self.make_laser.isChecked() else None
            cancel=box.addButton(QMessageBox.StandardButton.Cancel);box.setDefaultButton(cancel);box.exec();chosen=box.clickedButton();resume=message.resume_router
            if omit and chosen==omit:QTimer.singleShot(0,lambda:resume('omit'))
            elif tool and chosen==tool:
                diameter,ok=QInputDialog.getDouble(self,'Profile tool','Actual available cutter diameter (mm)',self.fields[('profile','tool_diameter_mm')].value(),.1,20,3)
                if ok:QTimer.singleShot(0,lambda:resume('tool',diameter))
            elif laser and chosen==laser:QTimer.singleShot(0,lambda:resume('laser'))
            else:self.status.setText('Preview paused · no router features were omitted.')
            return
        if hasattr(message,'laser_diagnostic'):
            d=message.laser_diagnostic
            for issue in d['issues']:
                x,y=issue['source_center'];path=QPainterPath();path.addEllipse(x-.22,-y-.22,.44,.44);path.moveTo(x+.8,-y-.8);path.lineTo(x+.15,-y-.15);path.lineTo(x+.35,-y-.2)
                pen=QPen(QColor('#ff3333'),2);pen.setCosmetic(True);item=self.view.scene().addPath(path,pen);item.setZValue(1000);self.laser_issue_items.append(item)
            if d.get('review'):QDesktopServices.openUrl(QUrl.fromLocalFile(d['review']))
            if hasattr(message,'continue_preview'):
                self.status.setText('Preview paused · choose whether to omit the marked details.')
                box=QMessageBox(self);box.setWindowTitle('Small laser details');box.setIcon(QMessageBox.Icon.Warning)
                box.setText(f"{len(d['issues'])} marked fragments cannot be printed at this DPI.")
                box.setInformativeText('Skip these fragments and continue the preview using the isolation paths already calculated? Their locations stay marked in review. Omissions may leave copper bridges.')
                skip=box.addButton(f"Skip {len(d['issues'])} fragments and continue preview",QMessageBox.ButtonRole.AcceptRole)
                cancel=box.addButton(QMessageBox.StandardButton.Cancel);box.setDefaultButton(cancel);box.exec()
                if box.clickedButton()==skip:
                    continuation=message.continue_preview;QTimer.singleShot(0,continuation)
                else:self.status.setText('Preview paused · marked details were not omitted.')
                return
        if hasattr(message,'diagnostic'):
            d=message.diagnostic;x,y=d['closest_xy'];path=QPainterPath();path.moveTo(x+7,-y-7);path.lineTo(x,-y);path.lineTo(x+1.7,-y-.4);path.moveTo(x,-y);path.lineTo(x+.4,-y-1.7)
            self.view.scene().addPath(path,QPen(QColor('#ff5555'),.3))
        message=str(message)
        self.status.setText('Could not complete operation: '+message);QMessageBox.warning(self,'PCB Isolator',message)
    def choose_board(self):
        path,_=QFileDialog.getOpenFileName(self,'Open saved KiCad board','','KiCad (*.kicad_pcb *.kicad_pro)')
        if path:
            self.project_path.setText(path);self.output_root.setText(str(Path(path).parent/'Manufacturing Output'));self.import_selected()
    def choose_output(self):
        path=QFileDialog.getExistingDirectory(self,'Choose manufacturing output location',self.output_root.text())
        if path:self.output_root.setText(path)
    def import_selected(self):
        path=Path(self.project_path.text())
        if path.suffix.lower() not in ('.kicad_pcb','.kicad_pro'):
            path=self.board.get('source') if self.board else None
            if not path or not path.exists():
                self.choose_board();return
        output=path.parent/'.pcb-isolator/jobs'
        self.task(lambda:backend.import_board(path,output),self.loaded,'Exporting the saved KiCad board and importing geometry…')
    def choose_job(self):
        path=QFileDialog.getExistingDirectory(self,'Open manufacturing job folder',str(backend.ROOT/'jobs'))
        if path:self.load_job(Path(path))
    def load_job(self,path):
        self.task(lambda:backend.read_board(path),self.loaded,'Loading copper, drills and outline…')
    def loaded(self,board):
        if self.reference_dialog is not None:
            self.busy_widgets.remove(self.reference_dialog);self.reference_dialog.close();self.reference_dialog.deleteLater();self.reference_dialog=None
        self.reference_checks={}
        self.board=board;self.results={};self.isolation_cache=None
        self.reference_button.setEnabled(bool(board.get('reference_layers')))
        if not board.get('reference_layers'):self.reference_button.setToolTip(board.get('reference_layer_error') or 'This export has no saved KiCad layer inventory. Open a saved KiCad board to see extra layers.')
        else:self.reference_button.setToolTip('Show optional KiCad layers on this main view only. No manufacturing changes.')
        self.router['profile'].pop('ignored_cutouts',None)
        self.invalidate_preview()
        self.table.blockSignals(True);self.table.setRowCount(0);self.table.blockSignals(False)
        saved=board.get('ui_settings')
        if saved:
            self.router=deepcopy(saved['router'])
            for (section,key),widget in self.fields.items():widget.setValue(self.router[section][key])
            self.calibrated.blockSignals(True);self.calibrated.setChecked(saved['laser'].get('directional',False));self.calibrated.blockSignals(False)
            self.width_y.setEnabled(self.calibrated.isChecked());self.spacing.setEnabled(self.calibrated.isChecked());self.overlap.setEnabled(not self.calibrated.isChecked())
            self.width_y.setValue(saved['laser'].get('width_y',.33));self.spacing.setValue(saved['laser'].get('spacing',.020))
            self.lines.setValue(saved['laser']['lines']);self.width.setValue(saved['laser']['width']);self.overlap.setValue(saved['laser']['overlap'])
            self.laser_format.setCurrentIndex(0)
            if saved['laser'].get('helix'):self.restore_helix(saved['laser']['helix'])
            self.pin.blockSignals(True);self.pin.setValue(saved.get('pin_diameter_mm',3.175));self.pin.blockSignals(False)
        for button in self.result_buttons.values():button.setEnabled(False)
        self.project_name.setText(board['name']);self.project_path.setText(str(board.get('source') or board['job']));self.output_root.setText(str(board['output_folder']))
        self.output_root.setToolTip(str(board['output_folder']))
        x0,y0,x1,y1=board['copper'].bounds
        self.board_summary.setText(f'{board["name"]}   ·   {x1-x0:.2f} × {y1-y0:.2f} mm copper   ·   {len(board["features"])} holes / slots')
        self.drill_highlights=[]
        self.view.draw_board(board);self.populate_holes()
        self.populate_drill_groups(reset=True)
        QTimer.singleShot(0,self.view.fit)
        if saved:
            index=self.origin.findData(saved['origin_id'])
            if index>=0:self.origin.setCurrentIndex(index)
        self.status.setText('Board loaded · Select alignment holes and review settings.');self.generate_button.setEnabled(True)
    def selected_ids(self):
        return [self.table.item(row,0).data(Qt.ItemDataRole.UserRole) for row in range(self.table.rowCount()) if self.table.cellWidget(row,0).isChecked()]
    def populate_holes(self):
        if not self.board:return
        old=set(self.selected_ids()) if self.table.rowCount() else set((self.board.get('selection') or {}).get('alignment_ids',[]))
        self.table.blockSignals(True);self.table.setRowCount(0)
        for feature in self.board.get('alignment_candidates',self.board['features']):
            if feature.end is not None:continue
            row=self.table.rowCount();self.table.insertRow(row)
            item=QTableWidgetItem();item.setData(Qt.ItemDataRole.UserRole,feature.id);self.table.setItem(row,0,item)
            check=QCheckBox('Use');check.setChecked(feature.id in old)
            check.setToolTip('Smaller than the pin: prepare this PCB hole manually to fit.' if feature.diameter_mm<self.pin.value() else 'Use this hole for alignment.')
            if feature.id.startswith('outline:'):check.setToolTip(check.toolTip()+' Circular internal Edge.Cuts; selected locations are prepared manually and excluded from profile routing.')
            self.table.setCellWidget(row,0,check)
            check.toggled.connect(self.selection_changed)
            for col,value in enumerate((feature.diameter_mm,feature.x,feature.y),1):
                item=QTableWidgetItem(f'{value:.3f}');item.setFlags(Qt.ItemFlag.ItemIsEnabled);self.table.setItem(row,col,item)
                if feature.diameter_mm<self.pin.value():
                    item.setForeground(QBrush(QColor('#ffcf80')));item.setToolTip('Hole is smaller than the configured pin. Selection preserves its source diameter.')
        self.table.blockSignals(False);self.selection_changed()
    def toggle_board_hole(self,id):
        if self.worker and self.worker.isRunning():return
        for row in range(self.table.rowCount()):
            if self.table.item(row,0).data(Qt.ItemDataRole.UserRole)==id:
                check=self.table.cellWidget(row,0);check.setChecked(not check.isChecked())
                self.table.scrollToItem(self.table.item(row,0));return
    def selection_changed(self,*_):
        if not self.board:return
        sender=self.sender()
        if isinstance(sender,QCheckBox) and sender.isChecked():
            row=next((r for r in range(self.table.rowCount()) if self.table.cellWidget(r,0) is sender),None)
            if row is not None:
                id=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
                chosen=next(f for f in self.board.get('alignment_candidates',self.board['features']) if f.id==id)
                for r in range(self.table.rowCount()):
                    check=self.table.cellWidget(r,0)
                    other=next(f for f in self.board.get('alignment_candidates',self.board['features']) if f.id==self.table.item(r,0).data(Qt.ItemDataRole.UserRole))
                    if check is not sender and abs(other.x-chosen.x)<.0001 and abs(other.y-chosen.y)<.0001:
                        check.blockSignals(True);check.setChecked(False);check.blockSignals(False)
        self.invalidate_preview()
        ids=self.selected_ids();previous=self.origin.currentData();self.origin.blockSignals(True);self.origin.clear()
        selected=sorted((f for f in self.board.get('alignment_candidates',self.board['features']) if f.id in ids),key=lambda f:(f.x,f.y))
        for feature in selected:self.origin.addItem(f'X{feature.x:.3f}  Y{feature.y:.3f}',feature.id)
        index=self.origin.findData(previous)
        if index>=0:self.origin.setCurrentIndex(index)
        self.origin.blockSignals(False)
        self.alignment_info.setText(f'{len(ids)} alignment holes selected · {len(self.remaining_drills())} remaining features')
        small=sum(f.diameter_mm<self.pin.value() for f in selected)
        if small:self.alignment_info.setText(self.alignment_info.text()+f' · {small} undersized: prepare manually for pins')
        from .registration import edge_warnings
        warnings=edge_warnings(self.board,ids,self.pin.value())
        if warnings:self.alignment_info.setText(self.alignment_info.text()+' · WARNING: pin hole breaks out of board edge')
        self.alignment_info.setToolTip('\n'.join(warnings))
        self.origin_changed()
        self.populate_drill_groups()
    def drill_assignments(self):
        rows=[]
        for row in range(self.drill_table.rowCount()):
            source=self.drill_table.item(row,0).data(Qt.ItemDataRole.UserRole)
            try:tool=float(self.drill_table.cellWidget(row,2).currentText())
            except ValueError:raise ValueError('Enter a numeric drill diameter in millimeters.')
            if not .001<=tool<=100:raise ValueError('Use a drill diameter between 0.001 and 100 mm.')
            rows.append({'source_diameter_mm':source,'tool_diameter_mm':round(tool,6)})
        return rows
    def remaining_drills(self):
        if not self.board:return []
        pins=[f for f in self.board.get('alignment_candidates',self.board['features']) if f.id in self.selected_ids()]
        return [f for f in self.board['features'] if f.end is None and not any(abs(f.x-p.x)<.0001 and abs(f.y-p.y)<.0001 for p in pins)]
    def populate_drill_groups(self,reset=False):
        if not self.board:return
        if reset:
            mapping={r['source_diameter_mm']:r['tool_diameter_mm'] for r in self.router['drilling'].get('assignments',[])} if self.board.get('ui_settings') else {}
        else:
            mapping=dict(getattr(self,'drill_mapping',{}))
            try:mapping.update({r['source_diameter_mm']:r['tool_diameter_mm'] for r in self.drill_assignments()})
            except ValueError:return
        self.drill_mapping=mapping
        counts=Counter(f.diameter_mm for f in self.remaining_drills())
        self.drill_table.blockSignals(True);self.drill_table.setRowCount(0)
        choices=sorted(set(counts)|set(mapping.values()))
        for source,count in sorted(counts.items()):
            row=self.drill_table.rowCount();self.drill_table.insertRow(row)
            for col,text in [(0,f'{source:g}'),(1,str(count)),(3,'')]:
                item=QTableWidgetItem(text);item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                if col==0:item.setData(Qt.ItemDataRole.UserRole,source)
                self.drill_table.setItem(row,col,item)
            combo=QComboBox();combo.setEditable(True);combo.addItems([f'{v:g}' for v in choices]);combo.setCurrentText(f'{mapping.get(source,source):g}')
            self.drill_table.setCellWidget(row,2,combo);combo.currentTextChanged.connect(self.drill_groups_changed)
        self.drill_table.blockSignals(False);self.drill_groups_changed();self.highlight_drill_group()
    def drill_groups_changed(self,*_):
        self.invalidate_preview()
        try:rows=self.drill_assignments()
        except ValueError as error:self.drill_summary.setText(str(error));return
        for index,row in enumerate(rows):
            delta=row['tool_diameter_mm']-row['source_diameter_mm']
            self.drill_table.item(index,3).setText('Same' if abs(delta)<1e-6 else f'{delta:+.3f}')
            self.drill_table.item(index,3).setForeground(QBrush(QColor('#ffcf80' if abs(delta)>=1e-6 else '#a7bacb')))
        tools=len({r['tool_diameter_mm'] for r in rows})
        changed=sum(abs(r['tool_diameter_mm']-r['source_diameter_mm'])>=1e-6 for r in rows)
        self.drill_summary.setText(f'{len(rows)} source sizes → {tools} PCB drill programs'+(f' · {changed} size overrides. + larger / − smaller holes.' if changed else '')+' Alignment pin drilling stays separate.')
    def highlight_drill_group(self):
        for item in self.drill_highlights:
            if item.scene() is self.view.scene():self.view.scene().removeItem(item)
        self.drill_highlights=[]
        selected={self.drill_table.item(index.row(),0).data(Qt.ItemDataRole.UserRole) for index in self.drill_table.selectionModel().selectedRows()}
        # A selected cell also identifies its source-size row.
        selected.update(self.drill_table.item(i.row(),0).data(Qt.ItemDataRole.UserRole) for i in self.drill_table.selectedIndexes())
        for f in self.remaining_drills():
            if f.diameter_mm in selected:
                r=max(f.diameter_mm/2+.35,9/max(self.view.transform().m11(),.001))
                # High-contrast halo and cosmetic strokes remain visible on
                # both copper and dark gaps, including small component holes.
                for color,width,fill,z in [('#101018',8,None,1000),('#ff25db',4,'#ff25db77',1001)]:
                    pen=QPen(QColor(color),width);pen.setCosmetic(True)
                    item=self.view.scene().addEllipse(f.x-r,-f.y-r,2*r,2*r,pen,
                        QBrush(QColor(fill)) if fill else QBrush(Qt.BrushStyle.NoBrush))
                    item.setZValue(z);self.drill_highlights.append(item)
    def origin_changed(self,*_):
        if self.board:self.view.selection(set(self.selected_ids()),self.origin.currentData())
    def laser_model_changed(self,enabled):
        self.width_y.setEnabled(enabled);self.spacing.setEnabled(enabled);self.overlap.setEnabled(not enabled)
        if enabled:
            self.width.setValue(.22);self.width_y.setValue(.33);self.spacing.setValue(.020)
            if self.lines.value()>6:self.lines.setValue(6)
        self.invalidate_preview()
    def laser_values(self):return {'lines':self.lines.value(),'width':self.width.value(),'overlap':self.overlap.value(),'format':'direct','helix':self.helix_values(),'directional':self.calibrated.isChecked(),'width_y':self.width_y.value(),'spacing':self.spacing.value(),'adaptive':self.calibrated.isChecked()}
    def update_preview(self):
        if not self.board:return
        laser=self.laser_values();board=self.board
        def done(contours):self.view.isolation(contours);self.status.setText(f'Isolation preview updated · maximum {laser["lines"]} lines.')
        self.task(lambda:backend.preview_paths(board,laser),done,'Generating isolation preview…')
    def generate(self):
        if not self.board:return
        if self.preview_results and not self.preview_results.get('partial_preview'):
            if self.preview_results.get('registration_preview'):
                QMessageBox.information(self,'Complete alignment setup','Select at least two alignment holes on the board or in the table, then Generate preview again before creating final outputs.');return
            d=self.preview_results.get('clearance_diagnostic')
            extra=f'\n\nXY margin was reduced to {d["applied_margin_mm"]:.3f} mm to fit. Confirm this reduced clearance.' if d else ''
            if 'laser' in self.preview_results:
                report=Path(self.preview_results['laser'])/'helix-job.json'
                if report.exists():
                    omitted=json.loads(report.read_text(encoding='utf-8')).get('ignored_tiny_fragments',[])
                    if omitted:extra+=f'\n\n{len(omitted)} uncovered tiny fragments were omitted at your request. Confirm you inspected their red markers in Laser review; omissions may leave copper bridges.'
            answer=QMessageBox.question(self,'Generate outputs','Create final output files from these previews? Existing output will be archived internally. Reset Z for each tool and check the physical machine setup before running.'+extra,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Yes:return
            preview=self.preview_results;output=Path(self.output_root.text())
            def published(results):
                self.results=results;self.invalidate_preview();self.laser_ready=results if 'laser' in results else None
                for key,button in self.result_buttons.items():button.setEnabled(('router_review' if key=='router_zip' else key) in results)
                self.result_text.setText(str(results['run']));self.status.setText('Outputs ready · Released files are in the output folder.')
            format=self.laser_format.currentData()
            self.task(lambda:backend.export_preview(preview,output,laser_format=format),published,'Creating final outputs from the preview…')
            return
        router=deepcopy(self.router)
        for (section,key),widget in self.fields.items():router[section][key]=widget.value()
        try:router['drilling']['assignments']=self.drill_assignments()
        except ValueError as error:QMessageBox.warning(self,'Drill sizes',str(error));return
        board=self.board;ids=self.selected_ids();origin=self.origin.currentData();pin=self.pin.value()
        try:laser=self.laser_values()
        except ValueError as error:self.failed(error);return
        if laser['directional'] and laser['lines']>6:
            QMessageBox.warning(self,'Trial lane limit','Use at most 6 lanes for the calibrated trial preset.');return
        flags=[self.make_laser.isChecked(),self.make_router.isChecked()]
        registration_preview=len(ids)<2 and flags[1]
        if len(ids)<2:
            answer=QMessageBox.question(self,'Incomplete alignment setup',
                ('Continue without picking holes?' if not ids else 'Continue with only one alignment hole?')+
                ('\n\nRouter previews will use an incomplete registration setup. Select holes and regenerate before final router output.' if flags[1] else '\n\nLaser-only output does not require alignment holes.'),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Yes:return
        undersized=any(f.id in ids and f.diameter_mm<pin for f in board.get('alignment_candidates',board['features']))
        if undersized:
            answer=QMessageBox.question(self,'Undersized alignment holes',
                f'Selected undersized locations will use {pin:g} mm pin holes for manufacturing. Manually drill the PCB at these marks to fit the pins; all overlapping round drill entries at these centers are excluded from normal PCB drilling. The original KiCad board stays unchanged. Continue?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Yes:return
        if not any(flags):
            QMessageBox.warning(self,'Choose output','Select Laser, Router, or both.');return
        output=Path(self.output_root.text())
        def done(results):
            self.results=results
            self.preview_results=results
            self.laser_ready=results if 'laser' in results else None
            self.generate_button.setText('Generate outputs')
            self.generate_button.setStyleSheet('background:#26745e;color:white;font-weight:bold;padding:12px')
            self.generate_button.setToolTip('Create final files from the generated previews after confirmation.')
            for key,button in self.result_buttons.items():button.setEnabled(('router_review' if key=='router_zip' else key) in results)
            self.result_buttons['run'].setEnabled(False)
            self.result_text.setText('Draft previews ready. Review them, then press Generate outputs.');self.status.setText('Preview ready · Generate outputs is now available.');self.router=router
            if registration_preview:
                self.generate_button.setText('Generate preview')
                self.generate_button.setStyleSheet('background:#326b99;color:white;font-weight:bold;padding:12px')
                self.preview_results=None
                self.result_text.setText('Preview only · Alignment incomplete. Pick at least two holes and generate a new preview. With no holes selected, XY zero is provisionally at the copper lower-left.')
                self.status.setText('Preview ready · You can change alignment holes and generate again.')
            for key in ('laser_review','router_review'):
                if key in results:self.open_result(key)
            if results.get('partial_preview'):
                self.generate_button.setText('Generate preview');self.generate_button.setStyleSheet('background:#326b99;color:white;font-weight:bold;padding:12px')
                self.result_text.setText('Partial preview · both reviews are available. Resolve the marked issue or continue with the working module only.')
                errors=list(results.get('module_errors',{}).values())
                if errors:QTimer.singleShot(0,lambda error=errors[0]:self.failed(error))

            d=results.get('clearance_diagnostic')
            if d:
                QMessageBox.warning(self,'XY clearance adjusted',f'Requested XY margin: {d["requested_margin_mm"]:.3f} mm.\nMaximum margin that fits: {d["maximum_margin_mm"]:.3f} mm.\nPreview calculated using {d["applied_margin_mm"]:.3f} mm.\n'+('Warning: this is less than 0.5 mm.\n' if d['applied_margin_mm']<.5 else '')+'A red arrow marks the limiting location in Router review. Review this reduced clearance before generating outputs.')
        key=self.plan_key(board,laser)
        prepared=[self.isolation_cache[1] if self.isolation_cache and self.isolation_cache[0]==key else None]
        def keep_plan(contours):
            prepared[0]=contours;self.isolation_cache=(key,contours)
        def resume(error):
            if self.worker and self.worker.isRunning():
                QTimer.singleShot(25,lambda:resume(error));return
            from math import ceil
            limit=min(.1,max(laser['helix']['tiny_fragment_mm'],ceil(max(i['length_mm'] for i in error.laser_diagnostic['issues'])*1000)/1000))
            self.ignore_tiny.setChecked(True);self.tiny_threshold.setValue(limit)
            laser['helix'].update(ignore_tiny_fragments=True,tiny_fragment_mm=limit,tiny_filter_default_version=1)
            self.task(action,done,'Continuing preview · reusing calculated isolation paths…')
        def decorate(error):
            from .helix import LaserGridError
            if getattr(error,'prepared_contours',None) is not None:keep_plan(error.prepared_contours)
            if getattr(error,'router_preview_error',False):
                def resume_router(choice,diameter=None,failure=error):
                    if self.worker and self.worker.isRunning():QTimer.singleShot(25,lambda:resume_router(choice,diameter,failure));return
                    if choice=='laser':flags[1]=False;self.make_router.setChecked(False)
                    elif choice=='tool':
                        router['profile']['tool_diameter_mm']=diameter;self.fields[('profile','tool_diameter_mm')].setValue(diameter)
                    elif choice=='omit':
                        entries=router['profile'].setdefault('ignored_cutouts',[]);known={e['id'] for e in entries}
                        entries.extend({'id':i['id']} for i in failure.feature_diagnostic['issues'] if i['id'] not in known)
                        self.router['profile']['ignored_cutouts']=deepcopy(entries)
                    self.task(action,done,'Continuing preview · reusing imported board and isolation paths…')
                error.resume_router=resume_router
            if not isinstance(error,LaserGridError):return
            if all(i['length_mm']<=.1 for i in error.laser_diagnostic['issues']):
                error.continue_preview=lambda failure=error:resume(failure)
        def action():
            preview_folder=board['job']/'outputs'/('preview-'+uuid.uuid4().hex[:10])
            try:
                result=backend.generate(board,ids,origin,pin,laser,router,*flags,output_folder=preview_folder,
                    registration_preview=registration_preview,undersized_holes_acknowledged=undersized,
                    prepared_contours=prepared[0],on_contours=keep_plan,allow_partial=True)
                for error in result.get('module_errors',{}).values():decorate(error)
                return result
            except ValueError as error:decorate(error);raise
        self.task(action,done,'Generating laser and router previews…')
    def plan_key(self,board,laser):
        return (id(board['copper']),tuple(laser.get(k) for k in ('lines','width','width_y','overlap','spacing','directional','adaptive')))
    def filter_changed(self,*_):
        source=self.preview_results or self.filter_source
        if source and 'laser' not in source:source=None
        self.invalidate_preview();self.filter_source=source
        if source and self.isolation_cache:self.filter_timer.start(350)
    def refresh_filter(self):
        source=self.filter_source
        if not source or not self.board:return
        if self.worker and self.worker.isRunning():self.filter_timer.start(100);return
        try:laser=self.laser_values();settings=laser['helix']
        except ValueError as error:self.failed(error);return
        key=self.plan_key(self.board,laser)
        if not self.isolation_cache or self.isolation_cache[0]!=key:return
        board=self.board;contours=self.isolation_cache[1];self.filter_source=None
        def done(results):
            self.results=results;self.preview_results=results;self.laser_ready=results if 'laser' in results else None
            summary=json.loads((Path(results['record'])/'run.json').read_text(encoding='utf-8'))
            incomplete=summary.get('registration_preview') or results.get('partial_preview')
            if incomplete:self.filter_source=results
            if summary.get('registration_preview') and not results.get('partial_preview'):self.preview_results=None
            self.generate_button.setText('Generate preview' if incomplete else 'Generate outputs')
            self.generate_button.setStyleSheet('background:#326b99;color:white;font-weight:bold;padding:12px' if incomplete else 'background:#26745e;color:white;font-weight:bold;padding:12px')
            for key,button in self.result_buttons.items():button.setEnabled(('router_review' if key=='router_zip' else key) in results)
            self.result_buttons['run'].setEnabled(False)
            self.result_text.setText('Filter updated · same isolation plan and router result retained.');self.status.setText('Filter preview updated without rescanning or rerouting.')
            self.open_result('laser_review')
        def action():
            from .helix import LaserGridError
            try:return backend.refresh_laser_filter(board,source,settings,contours)
            except LaserGridError as error:
                def resume(failure=error):
                    from math import ceil
                    self.filter_source=source
                    limit=min(.1,max(settings['tiny_fragment_mm'],ceil(max(i['length_mm'] for i in failure.laser_diagnostic['issues'])*1000)/1000))
                    self.ignore_tiny.setChecked(True);self.tiny_threshold.setValue(limit)
                    if not self.filter_timer.isActive():self.filter_timer.start(0)
                if all(i['length_mm']<=.1 for i in error.laser_diagnostic['issues']):error.continue_preview=resume
                raise
        self.task(action,done,'Updating filter only · reusing plan and router programs…')
    def restore_cutouts(self):
        self.router['profile'].pop('ignored_cutouts',None);self.invalidate_preview();self.status.setText('Omitted cutouts restored. Generate preview; cached isolation plan will be reused.')
    def helix_values(self):
        from .helix import validate
        values={key:box.value() for key,box in self.helix_fields.items()}
        return validate(dict(values,host=self.helix_host.text().strip(),dpi=self.helix_dpi.currentData(),ignore_tiny_fragments=self.ignore_tiny.isChecked(),tiny_fragment_mm=self.tiny_threshold.value(),tiny_filter_default_version=1))
    def restore_helix(self,settings):
        self.helix_host.setText(settings['host'])
        self.ignore_tiny.setChecked(settings.get('ignore_tiny_fragments',True) if settings.get('tiny_filter_default_version')==1 else True);self.tiny_threshold.setValue(settings.get('tiny_fragment_mm',.03))
        for key,box in self.helix_fields.items():
            if key in settings:box.setValue(settings[key])
        self.helix_dpi.setCurrentIndex(max(0,self.helix_dpi.findData(settings.get('dpi',600))))
    def check_laser(self):
        from .helix import check_connection
        try:settings=self.helix_values()
        except ValueError as error:self.failed(error);return
        self.helix_settings_path.write_text(json.dumps(settings,indent=2),encoding='utf-8')
        self.task(lambda:check_connection(settings),lambda message:QMessageBox.information(self,'Laser connection',message),'Checking laser TCP port; no job data…')
    def transfer_progress(self,percent,message):
        self.progress.setRange(0,100);self.progress.setValue(percent);self.status.setText(f'{percent}% · {message}')
    def send_laser(self):
        from .helix import send
        if not self.laser_ready:return
        folder=Path(self.laser_ready['laser'])
        try:
            settings=self.helix_values();report=json.loads((folder/'helix-job.json').read_text(encoding='utf-8'))
        except (OSError,ValueError) as error:self.failed(error);return
        message=(f"Send {report['title']} to {settings['host']}:{settings['port']}?\nSpeed {settings['speed']}% · Power {settings['power']}% · {settings['frequency']} Hz · {settings['dpi']} DPI\nOffset X{settings['x']:g} Y{settings['y']:g} mm · approximate time {report['timing']['label']}\n\nReview the exact grid paths in Laser review. Close lanes may round onto the same coordinates. Confirm material placement, manual focus, air and exhaust. Sending queues the job; it does not start the machine. No automatic retry on a transfer error.")
        if report.get('ignored_tiny_fragments'):message+=f'\n\nWARNING: {len(report["ignored_tiny_fragments"])} uncovered tiny fragments were omitted at your request. Check the red locations in review; omissions may leave bridges.'
        if QMessageBox.question(self,'Send reviewed laser job',message,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        self.helix_settings_path.write_text(json.dumps(settings,indent=2),encoding='utf-8')
        def done(message):
            self.status.setText(message);QMessageBox.information(self,'Laser queue acknowledged',message)
        self.task(lambda:send(folder,settings,lambda percent,text:self.worker.transfer.emit(percent,text)),done,'Submitting reviewed laser job…')
    def open_reference_layers(self):
        if not self.board:return
        if self.reference_dialog is not None:self.reference_dialog.show();self.reference_dialog.raise_();return
        dialog=QDialog(self);dialog.setWindowTitle('Reference layers · display only');dialog.resize(420,590)
        layout=QVBoxLayout(dialog);layout.addWidget(self.wrap('Layers from the saved board snapshot. All start hidden. Visibility never changes manufacturing settings or previews. Empty layers may have no artwork.'))
        row=QHBoxLayout();row.addWidget(QLabel('Overlay opacity'));opacity=self.spin(.7,.05,1,2);row.addWidget(opacity)
        hide=QPushButton('Hide all');row.addWidget(hide);layout.addLayout(row)
        scroll=QScrollArea();scroll.setWidgetResizable(True);contents=QWidget();items=QVBoxLayout(contents)
        self.reference_opacity=opacity
        for layer in self.board.get('reference_layers',[]):
            check=QCheckBox(layer['label']);check.setToolTip('Reference only: '+layer['name']);items.addWidget(check);self.reference_checks[layer['name']]=check
            check.toggled.connect(lambda checked,name=layer['name']:self.toggle_reference(name,checked))
        items.addStretch();scroll.setWidget(contents);layout.addWidget(scroll)
        close=QPushButton('Close');close.clicked.connect(dialog.hide);layout.addWidget(close)
        hide.clicked.connect(lambda:[check.setChecked(False) for check in self.reference_checks.values()])
        opacity.valueChanged.connect(lambda value:[item.setOpacity(value) for item in self.view.reference_items.values()])
        self.reference_dialog=dialog;self.busy_widgets.append(dialog);dialog.show()
    def toggle_reference(self,name,checked):
        if not checked:self.view.hide_reference(name);return
        if name in self.view.reference_items:self.view.show_reference(name,None,self.reference_opacity.value());return
        if self.worker and self.worker.isRunning():
            check=self.reference_checks[name];check.blockSignals(True);check.setChecked(False);check.blockSignals(False);return
        from .reference_layers import export_layer
        board=self.board
        def done(path):
            if self.board is not board:return
            visible=self.view.show_reference(name,path,self.reference_opacity.value())
            self.status.setText(name+(' · reference layer visible; manufacturing unchanged.' if visible else ' · no visible artwork on this layer.'))
        def action():
            try:return export_layer(board['job'],name)
            except Exception as error:
                error.reference_layer=name;raise
        self.task(action,done,'Loading reference layer '+name+'…')
    def save_router_zip(self):
        if self.worker and self.worker.isRunning():return
        review=self.results.get('router_review')
        if not review:return
        name=(self.board['name'] if self.board else 'PCB')+' - Router review.zip'
        destination,_=QFileDialog.getSaveFileName(self,'Save router review ZIP',str(Path(self.output_root.text())/name),'ZIP archive (*.zip)')
        if not destination:return
        from .review_zip import save_router_review_zip
        self.task(lambda:save_router_review_zip(review,destination),lambda path:self.status.setText('Router review ZIP saved: '+str(path)),'Saving router review ZIP…')
    def open_result(self,key):
        if key in self.results:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.results[key])))
    def closeEvent(self,event):
        self.filter_timer.stop()
        if self.worker and self.worker.isRunning():
            self.status.setText('Please wait for the current generation to finish before closing.');event.ignore()
        else:event.accept()


STYLE='''QWidget{background:#18232f;color:#e5edf5;font-family:Segoe UI;font-size:10pt}QLabel#title{font-size:23pt;font-weight:650;color:#f1f5f9}QLabel#hint{color:#a7bacb;font-size:9pt}QGroupBox{border:1px solid #405365;border-radius:7px;margin-top:13px;padding:12px 9px 8px}QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 5px;color:#79cdbc}QPushButton{background:#2a4052;border:1px solid #506a7d;border-radius:5px;padding:8px 11px;min-height:18px}QPushButton:hover{background:#38566c}QPushButton#primary{background:#26745e;color:white;font-weight:bold;padding:12px}QPushButton:disabled{color:#6f8292;border-color:#334655}QLineEdit,QDoubleSpinBox,QSpinBox,QComboBox{background:#111c27;border:1px solid #486174;border-radius:4px;padding:5px;selection-background-color:#32735f}QTableWidget{background:#111c27;gridline-color:#314759}QHeaderView::section{background:#253b4e;padding:5px;border:0}QTabBar::tab{background:#253b4e;padding:10px 12px}QTabBar::tab:selected{background:#34605d}QScrollArea{border:0}QGraphicsView{border:1px solid #405365;border-radius:6px}QSplitter::handle{background:#263b4c;width:2px}QProgressBar{height:8px;border:0;background:#304658}QProgressBar::chunk{background:#4dd3ae}'''


def main():
    app=QApplication(sys.argv);app.setApplicationName('PCB Isolator');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    window=Window();window.show()
    if len(sys.argv)>1:
        path=Path(sys.argv[1])
        if path.is_dir():QTimer.singleShot(0,lambda:window.load_job(path))
    sys.exit(app.exec())


if __name__=='__main__':main()
