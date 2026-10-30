from dataclasses import asdict
from hashlib import sha256
import json

import ezdxf
import pytest

from pcb_isolator.drills import load_drills
from pcb_isolator.job_outputs import prepare_outputs, validate_selection


def make_job(tmp_path):
    inputs=tmp_path/'inputs'; inputs.mkdir()
    outputs=tmp_path/'outputs'; outputs.mkdir()
    copper=inputs/'copper.gbr'
    copper.write_text('%FSLAX46Y46*%\n%MOMM*%\n%TF.FileFunction,Copper,L2,Bot*%\n%ADD10C,4*%\n%LPD*%\nD10*\nX10000000Y5000000D03*\nM02*\n')
    drills=inputs/'holes.drl'
    drills.write_text('M48\nMETRIC\nT1C3.2\nT2C0.5\nT3C1.0\n%\nG90\nG05\nT1\nX3.0Y3.0\nX17.0Y3.0\nT2\nX5.0Y5.0\nT3\nX7.0Y5.0\nM30\n')
    outline=inputs/'outline.dxf'
    doc=ezdxf.new('R2010'); doc.units=4
    doc.modelspace().add_lwpolyline([(0,0),(20,0),(20,10),(0,10)],close=True)
    doc.saveas(outline)
    files={'copper':'inputs/copper.gbr','outline':'inputs/outline.dxf','drills':['inputs/holes.drl']}
    manifest={'schema':'pcb-isolator-export','version':1,'units':'mm','origin':'absolute','mirrored':False,
              'files':files,'sha256':{'inputs/'+p.name:sha256(p.read_bytes()).hexdigest() for p in (copper,drills,outline)}}
    (tmp_path/'manufacturing-job.json').write_text(json.dumps(manifest))
    features=load_drills(drills)
    selection={'version':1,'units':'mm','copper':str(copper),'outline':str(outline),'drill_sources':[str(drills)],
               'pin_diameter_mm':3.175,'features':[asdict(f) for f in features],
               'alignment_ids':[f.id for f in features[:2]]}
    (outputs/'pcb-job.json').write_text(json.dumps(selection))
    return selection


def test_geometry_outputs_keep_alignment_and_exclude_pin_holes(tmp_path):
    make_job(tmp_path)
    output=prepare_outputs(tmp_path,include_laser=False)
    report=json.loads((output/'output-report.json').read_text())
    assert report['remaining_holes']==2
    assert report['machine_programs_generated'] is False
    drills=list(output.glob('pcb-drill-*.dxf'))
    assert len(drills)==2
    assert sum(len(ezdxf.readfile(p).modelspace().query('CIRCLE')) for p in drills)==2
    pins=ezdxf.readfile(output/'spoilboard-pin-holes.dxf').modelspace().query('CIRCLE')
    assert [p.dxf.radius*2 for p in pins]==pytest.approx([3.175,3.175])
    assert [(p.dxf.center.x,p.dxf.center.y) for p in pins]==[(3,3),(17,3)]
    marks=ezdxf.readfile(output/'laser-alignment-marks.dxf').modelspace().query('LINE')
    assert len(marks)==4
    centers=[((p.dxf.start.x+p.dxf.end.x)/2,(p.dxf.start.y+p.dxf.end.y)/2) for p in marks]
    assert centers==[(3,3),(3,3),(17,3),(17,3)]


def test_combined_laser_contains_marks_and_isolation(tmp_path):
    make_job(tmp_path)
    output=prepare_outputs(tmp_path,include_laser=True)
    doc=ezdxf.readfile(output/'laser-isolation-and-marks.dxf')
    assert len(doc.modelspace().query('*[layer=="ALIGNMENT_CENTER_MARKS"]'))==4
    assert any(e.dxf.layer.startswith('ISOLATION_') for e in doc.modelspace())


def test_invalid_selection_rejected(tmp_path):
    selection=make_job(tmp_path)
    selection['alignment_ids']=['unknown','unknown']
    with pytest.raises(ValueError,match='distinct'):
        validate_selection(tmp_path,selection)


def test_modified_geometry_rejected(tmp_path):
    selection=make_job(tmp_path)
    selection['features'][0]['x']+=1
    with pytest.raises(ValueError,match='geometry'):
        validate_selection(tmp_path,selection)
