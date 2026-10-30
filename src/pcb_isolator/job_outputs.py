"""Create aligned laser and drilling DXFs from a verified job selection."""
import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import shutil
import tomllib
import uuid

import ezdxf

from .drills import load_drills
from .dxf_export import export_dxf
from .importer import load_copper
from .isolation import generate_isolation, load_settings,isolation_diagnostics
from .kicad_export import load_job, resolve_job_folder
from .outline import load_outline


def validate_selection(job, selection):
    copper, drills, outline = load_job(job)
    def selected_path(value):
        path=Path(value)
        return (path if path.is_absolute() else Path(job)/path).resolve()
    if selection.get('version') != 1 or selection.get('units') != 'mm':
        raise ValueError('Unsupported alignment selection format or units.')
    if selected_path(selection['copper']) != copper or selected_path(selection['outline']) != outline:
        raise ValueError('Alignment selection belongs to a different job.')
    if [selected_path(p) for p in selection['drill_sources']] != drills:
        raise ValueError('Alignment selection uses different drill sources.')
    features = [feature for path in drills for feature in load_drills(path)]
    serialized = json.loads(json.dumps([asdict(f) for f in features]))
    if serialized != selection.get('features'):
        raise ValueError('Saved hole geometry does not match the current source files.')
    ids = selection.get('alignment_ids', [])
    if (len(ids) < 2 and not selection.get('registration_preview')) or len(ids) != len(set(ids)):
        raise ValueError('Select at least two distinct alignment holes.')
    from .registration import outline_candidates
    extra=outline_candidates(load_outline(outline),features)
    if 'outline_candidates' in selection and json.loads(json.dumps([asdict(f) for f in extra]))!=selection['outline_candidates']:
        raise ValueError('Saved outline alignment geometry does not match the source.')
    lookup = {feature.id: feature for feature in features+extra}
    if any(i not in lookup for i in ids):
        raise ValueError('Unknown alignment hole ID.')
    pins = float(selection['pin_diameter_mm'])
    if not isfinite(pins) or pins <= 0:
        raise ValueError('Invalid alignment pin diameter.')
    alignment = [lookup[i] for i in ids]
    if any(f.end is not None for f in alignment):
        raise ValueError('Alignment holes must be round.')
    if any(f.diameter_mm < pins for f in alignment) and not selection.get('undersized_holes_acknowledged'):
        raise ValueError('Confirm that undersized alignment holes will be prepared manually for the pins.')
    if len({(f.x, f.y) for f in alignment}) != len(alignment):
        raise ValueError('Alignment holes must have distinct positions.')
    # PTH/NPTH or stacked pads can export separate drills at one pin center.
    # Registration consumes the physical location, not just one source ID.
    remaining = [feature for feature in features if not (feature.end is None and
                 any(abs(feature.x-pin.x)<.0001 and abs(feature.y-pin.y)<.0001 for pin in alignment))]
    return copper, outline, alignment, remaining, pins


def new_dxf(layer, color=5):
    doc = ezdxf.new('R2010')
    doc.units = 4
    doc.header['$MEASUREMENT'] = 1
    doc.layers.new(layer, dxfattribs={'color':color})
    return doc


def add_alignment_marks(doc, alignment, size=0.5):
    layer = 'ALIGNMENT_CENTER_MARKS'
    if layer not in doc.layers:
        doc.layers.new(layer, dxfattribs={'color':3})
    for hole in alignment:
        attrs = {'layer':layer}
        doc.modelspace().add_line((hole.x-size/2,hole.y),(hole.x+size/2,hole.y),dxfattribs=attrs)
        doc.modelspace().add_line((hole.x,hole.y-size/2),(hole.x,hole.y+size/2),dxfattribs=attrs)


def prepare_outputs(job, selection_path=None, config=Path('config.toml'), include_laser=True):
    job = resolve_job_folder(job)
    selection_path = Path(selection_path) if selection_path else job/'outputs/pcb-job.json'
    selection = json.loads(selection_path.read_text(encoding='utf-8'))
    copper, outline, alignment, remaining, pins = validate_selection(job, selection)
    # Confirm topology before producing profile geometry for downstream CAM.
    load_outline(outline)
    settings = load_settings(config)
    with Path(config).open('rb') as stream:
        config_data = tomllib.load(stream)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = job/'outputs'/('geometry-'+stamp+'-'+uuid.uuid4().hex[:6])
    output.mkdir(parents=True)
    records = []
    groups = defaultdict(list)
    for feature in remaining:
        if feature.end is not None:
            raise ValueError('Slot DXF output is not implemented yet; no machine output will be created.')
        groups[feature.diameter_mm].append(feature)
    for diameter, features in sorted(groups.items()):
        name = f'pcb-drill-{diameter:.6f}mm.dxf'
        doc = new_dxf('PCB_DRILL')
        for feature in features:
            doc.modelspace().add_circle((feature.x,feature.y),diameter/2,dxfattribs={'layer':'PCB_DRILL'})
        doc.saveas(output/name)
        records.append({'file':name,'role':'pcb_drilling','diameter_mm':diameter,'count':len(features)})
    doc = new_dxf('SPOILBOARD_PIN_HOLES')
    for feature in alignment:
        doc.modelspace().add_circle((feature.x,feature.y),pins/2,dxfattribs={'layer':'SPOILBOARD_PIN_HOLES'})
    doc.saveas(output/'spoilboard-pin-holes.dxf')
    records.append({'file':'spoilboard-pin-holes.dxf','role':'spoilboard_pin_centers',
                    'nominal_pin_diameter_mm':pins,'count':len(alignment)})
    marks = new_dxf('ALIGNMENT_CENTER_MARKS',3)
    add_alignment_marks(marks,alignment)
    marks.saveas(output/'laser-alignment-marks.dxf')
    records.append({'file':'laser-alignment-marks.dxf','role':'laser_center_marks','count':len(alignment)})
    shutil.copyfile(outline,output/'board-profile.dxf')
    records.append({'file':'board-profile.dxf','role':'finished_board_outline_no_cutter_offset'})
    if include_laser:
        geometry = load_copper(copper).geometry
        contours=generate_isolation(geometry,settings)
        diagnostics=isolation_diagnostics(geometry,contours,settings)
        report = export_dxf(geometry,contours,settings,
                            output/'laser-isolation-and-marks.dxf',
                            config_data.get('geometry',{}).get('curve_tolerance_mm',0.001))
        laser = ezdxf.readfile(output/'laser-isolation-and-marks.dxf')
        add_alignment_marks(laser,alignment)
        laser.saveas(output/'laser-isolation-and-marks.dxf')
        records.append({'file':'laser-isolation-and-marks.dxf','role':'laser_isolation_and_center_marks',
                        'isolation_report':report,'diagnostics':diagnostics})
    for record in records:
        doc = ezdxf.readfile(output/record['file'])
        if doc.units != 4 or doc.audit().has_errors:
            raise ValueError(f'Generated DXF failed readback: {record["file"]}')
        record['sha256'] = sha256((output/record['file']).read_bytes()).hexdigest()
    report = {'schema':'pcb-isolator-geometry-output','version':1,'units':'mm',
              'origin':'absolute','mirrored':False,'machine_programs_generated':False,
              'alignment_ids':selection['alignment_ids'],'pin_diameter_mm':pins,
              'pcb_alignment_hole_diameters_mm':[f.diameter_mm for f in alignment],
              'remaining_holes':len(remaining),'files':records}
    (output/'output-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'alignment-selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
    (output/'laser-settings.toml').write_bytes(Path(config).read_bytes())
    (output/'README.txt').write_text(
        'Geometry only: no router machine programs are included.\n'
        'All drawings share original unmirrored KiCad coordinates in millimeters.\n'
        'Laser marks are 0.5 mm center crosses, not hole outlines.\n'
        'Selected alignment holes are omitted from normal PCB drill drawings.\n'
        'Spoilboard circles show nominal pin diameter, not a tuned drilling fit.\n'
        'Profile drawing is finished geometry without cutter compensation.\n',encoding='utf-8')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job',type=Path)
    parser.add_argument('--selection',type=Path)
    parser.add_argument('--config',type=Path,default=Path('config.toml'))
    args=parser.parse_args()
    try:
        output=prepare_outputs(args.job,args.selection,args.config)
    except Exception as error:
        parser.exit(1,f'Could not prepare job outputs: {error}\n')
    print(f'Prepared geometry outputs:\n{output}')
    print('DXF geometry only; router programs are not generated yet.')


if __name__=='__main__':
    main()
