"""Desktop application orchestration; geometry engines remain independently testable."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import uuid
import hashlib
import time
from datetime import datetime,timezone

from .drills import load_drills
from .importer import load_copper
from .isolation import IsolationSettings,generate_isolation
from .job_outputs import prepare_outputs,validate_selection
from .kicad_export import export_board,load_job,resolve_job_folder
from .outline import load_outline
from .router import load_machining,prepare_router_drafts
from .runtime import asset_root,machining_path

ROOT=asset_root()


def sync_retry(action):
    """Allow a short-lived Windows/cloud-sync sharing lock to clear."""
    for attempt in range(4):
        try:return action()
        except PermissionError:
            if attempt==3:raise
            time.sleep(.2*(attempt+1))


def copy_delivery(source,destination,archive):
    """Copy files in place; synced Windows folders may refuse directory renames."""
    source=Path(source).resolve();destination=Path(destination).resolve();archive=Path(archive).resolve()
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('Staging and delivery folders must be separate.')
    if archive.is_relative_to(destination) or destination.is_relative_to(archive):
        raise ValueError('Archive and delivery folders must be separate.')
    if destination.exists() and not (destination/'Start Here.html').is_file():
        raise ValueError('Choose a new folder or an existing PCB Isolator output folder.')
    if destination.exists() and not archive.exists():
        sync_retry(lambda:shutil.copytree(destination,archive))
    old={p.relative_to(destination) for p in destination.rglob('*') if p.is_file()} if destination.exists() else set()
    files={p.relative_to(source) for p in source.rglob('*') if p.is_file()}
    destination.mkdir(parents=True,exist_ok=True)
    for relative in sorted(files,key=lambda p:(p.name=='Start Here.html',str(p))):
        target=destination/relative
        if not target.resolve().is_relative_to(destination):raise ValueError('Output file escapes its folder.')
        target.parent.mkdir(parents=True,exist_ok=True)
        sync_retry(lambda:shutil.copyfile(source/relative,target))
    for relative in old-files:
        target=destination/relative
        if not target.resolve().is_relative_to(destination):raise ValueError('Old output file escapes its folder.')
        sync_retry(target.unlink)
    for directory in sorted((p for p in destination.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
        if directory.resolve().is_relative_to(destination) and not any(directory.iterdir()):
            sync_retry(directory.rmdir)


def read_board(job):
    job=resolve_job_folder(job)
    copper,drills,outline=load_job(job)
    features=[feature for path in drills for feature in load_drills(path)]
    selection_path=job/'outputs/pcb-job.json'
    selection=json.loads(selection_path.read_text(encoding='utf-8')) if selection_path.exists() else None
    if selection:
        validate_selection(job,selection)
    saved=list((job/'outputs').glob('app-run-*/run.json'))
    ui_settings=json.loads(max(saved,key=lambda p:p.stat().st_mtime).read_text(encoding='utf-8')) if saved else None
    metadata=json.loads((job/'manufacturing-job.json').read_text(encoding='utf-8'))
    source=Path(metadata['source_original']) if metadata.get('source_original') else None
    from .kicad_export import separation_input
    from .separation import load_separation
    separation=separation_input(job)
    from .registration import outline_candidates
    rings=load_outline(outline)
    extra=outline_candidates(rings,features)
    from .reference_layers import list_layers
    reference_error=None
    try:reference_layers=list_layers(job)
    except (OSError,ValueError) as error:reference_layers=[];reference_error=str(error)
    return {'reference_layers':reference_layers,'reference_layer_error':reference_error,'alignment_candidates':features+extra,'outline_alignment':extra,'job':job,'source':source,'output_folder':source.parent/'Manufacturing Output' if source else job/'Manufacturing Output','copper':load_copper(copper).geometry,'features':features,
            'outline':rings,'selection':selection,
            'separations':load_separation(separation) if separation else [],
            'ui_settings':ui_settings,
            'name':json.loads((job/'manufacturing-job.json').read_text(encoding='utf-8')).get('board_name',job.parent.name)}


def import_board(path,output_root):
    path=Path(path)
    if path.suffix.lower()=='.kicad_pro':
        path=path.with_suffix('.kicad_pcb')
    return read_board(export_board(path,output_root))


def write_toml(path,config):
    lines=[]
    for section,values in config.items():
        lines.append(f'[{section}]')
        for key,value in values.items():
            if isinstance(value,list):
                continue
            encoded=json.dumps(value) if isinstance(value,(str,bool)) else str(value)
            lines.append(f'{key} = {encoded}')
        lines.append('')
        for key,value in values.items():
            if isinstance(value,list):
                for entry in value:
                    lines.append(f'[[{section}.{key}]]')
                    for k,v in entry.items():
                        lines.append(f'{k} = {json.dumps(v) if isinstance(v,(str,bool)) else v}')
                    lines.append('')
    Path(path).write_text('\n'.join(lines),encoding='utf-8')


def default_router():
    config=load_machining(machining_path())
    config['alignment_pins']['pins_removed_before_machining']=True
    return config


def make_selection(board,ids,pin_diameter,registration_preview=False,undersized_holes_acknowledged=False):
    job=board['job']
    copper,drills,outline=load_job(job)
    selection={'version':1,'units':'mm','copper':copper.relative_to(job).as_posix(),
               'drill_sources':[p.relative_to(job).as_posix() for p in drills],
               'outline':outline.relative_to(job).as_posix(),'pin_diameter_mm':pin_diameter,
               'features':json.loads(json.dumps([asdict(f) for f in board['features']])),
               'outline_candidates':json.loads(json.dumps([asdict(f) for f in board.get('outline_alignment',[])])),
               'alignment_ids':list(ids),'registration_preview':registration_preview,
               'undersized_holes_acknowledged':undersized_holes_acknowledged,
               'alignment_hole_overrides':[{'id':f.id,'x':f.x,'y':f.y,
                   'source_diameter_mm':f.diameter_mm,'manufacturing_diameter_mm':pin_diameter}
                   for f in board.get('alignment_candidates',board['features']) if f.id in ids and f.diameter_mm<pin_diameter],
               'machine':{'profile':'laguna_swift','z_zero':'board_top','manual_spindle_speed':True,
                          'automatic_spindle_start_stop':True,'one_file_per_tool':True}}
    from .registration import edge_warnings
    selection['registration_warnings']=edge_warnings(board,list(ids),pin_diameter)
    validate_selection(job,selection)
    return selection


def preview_paths(board,laser):
    return generate_isolation(board['copper'],IsolationSettings(laser['width'],laser['overlap'],laser['lines'],laser.get('width_y') if laser.get('directional') else None,laser.get('spacing') if laser.get('directional') else None,laser.get('adaptive',True) if laser.get('directional') else False))


def generate(board,ids,origin_id,pin_diameter,laser,router,make_laser=True,make_router=True,output_folder=None,
             registration_preview=False,undersized_holes_acknowledged=False,prepared_contours=None,on_contours=None,allow_partial=False):
    if not make_laser and not make_router:
        raise ValueError('Choose Laser, Router, or both outputs.')
    laser_format=laser.get('format','dxf')
    if laser_format not in ('dxf','svg','both','direct'):raise ValueError('Choose DXF, SVG or both laser formats.')
    job=board['job']
    router=deepcopy(router)
    router['alignment_pins']['pins_removed_before_machining']=True
    selection=make_selection(board,ids,pin_diameter,registration_preview or not make_router,undersized_holes_acknowledged)
    if origin_id not in ids and not ((registration_preview or not make_router) and not ids):
        raise ValueError('Router XY zero must be one of the selected alignment holes.')
    origin=next((f for f in board.get('alignment_candidates',board['features']) if f.id==origin_id),None)
    ox,oy=(origin.x,origin.y) if origin else board['copper'].bounds[:2]
    router=deepcopy(router)
    router['machine']['origin_x_mm']=ox
    router['machine']['origin_y_mm']=oy
    run=job/'outputs'/('app-run-'+uuid.uuid4().hex[:10]);run.mkdir(parents=True)
    settings=run/'settings';settings.mkdir()
    (settings/'alignment-selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
    (job/'outputs/pcb-job.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
    laser_config={'laser':{'effective_width_mm':laser['width'],'overlap_percent':laser['overlap']},
                  'isolation':{'lines':laser['lines']},'geometry':{'curve_tolerance_mm':min(.005,max(.001,laser['width']*.05))}}
    if laser.get('directional'):
        laser_config['laser'].update(width_y_mm=laser['width_y'],lane_spacing_mm=laser['spacing'],adaptive=laser.get('adaptive',True))
    write_toml(settings/'laser.toml',laser_config)
    write_toml(settings/'machining.toml',router)
    paths={'run':run};module_errors={};contours=prepared_contours;clearance=None
    if make_laser:
        try:
            if laser_format=='direct':
                from .helix import prepare,LaserGridError
                destination=run/'laser';destination.mkdir()
                contours=prepared_contours if prepared_contours is not None else preview_paths(board,laser)
                if on_contours:on_contours(contours)
                # Internal diagnostic cache; never part of public machine output.
                from shapely import to_wkb
                (run/'laser-plan.json').write_text(json.dumps([to_wkb(c,hex=True) for c in contours]),encoding='utf-8')
                selected=[f for f in board.get('alignment_candidates',board['features']) if f.id in ids]
                try:
                    paths['laser_review']=prepare(board['copper'],contours,selected,destination,laser.get('helix',{}),board['name']+'_'+run.name,IsolationSettings(laser['width'],laser['overlap'],laser['lines'],laser.get('width_y') if laser.get('directional') else None,laser.get('spacing') if laser.get('directional') else None,laser.get('adaptive',True) if laser.get('directional') else False),print_features=board['features'],print_outline=board['outline'])
                except LaserGridError as error:
                    error.prepared_contours=contours
                    raise
                paths['laser']=destination
            else:
                output=prepare_outputs(job,settings/'alignment-selection.json',settings/'laser.toml')
                destination=run/'laser';destination.mkdir()
                for path in output.glob('*.dxf'):
                    if path.name.startswith('laser-'):
                        shutil.copyfile(path,destination/path.name)
                from .machining_preview import write_machining_preview
                copper,drills,outline=load_job(job)
                paths['laser_review']=write_machining_preview(copper,drills,run/'laser-review.html',outline,settings/'laser.toml')
                paths['laser']=destination
                from .svg_export import export_svg
                export_svg(destination/'laser-isolation-and-marks.dxf',destination/'laser-isolation-and-marks.svg')
        except Exception as error:
            error.prepared_contours=contours
            if not allow_partial:raise
            module_errors['laser']=error;paths.pop('laser',None)
            from .issue_review import write_issue_review
            diagnostic=getattr(error,'laser_diagnostic',{}).get('review')
            paths['laser_review']=Path(diagnostic) if diagnostic else write_issue_review(board,error,run/'laser-issues.html','Laser')
    if make_router:
        try:
            try:output=prepare_router_drafts(job,settings/'machining.toml',adjust_margin=True)
            except ValueError as error:
                error.router_preview_error=True
                error.prepared_contours=contours if make_laser and laser_format=='direct' else None
                raise
            clearance=json.loads((output/'router-report.json').read_text(encoding='utf-8')).get('clearance_diagnostic')
            if clearance:
                router['alignment_pins']['xy_margin_mm']=clearance['applied_margin_mm']
                write_toml(settings/'machining.toml',router)
            destination=run/'router'
            shutil.copytree(output,destination)
            paths['router']=destination
            paths['router_review']=destination/'router-review.html'
        except Exception as error:
            error.router_preview_error=True;error.prepared_contours=contours
            if not allow_partial:raise
            module_errors['router']=error;paths.pop('router',None)
            from .issue_review import write_issue_review
            paths['router_review']=write_issue_review(board,error,run/'router-issues.html','Router')
    summary={'board':board['name'],'export':job.name,'alignment_ids':ids,'origin_id':origin_id,
             'pin_diameter_mm':pin_diameter,
             'registration_preview':registration_preview and make_router,
             'source_origin_xy_mm':[ox,oy],'laser':laser,'router':router,
             'outputs':{k:Path(v).relative_to(run).as_posix() for k,v in paths.items() if k!='run'},
             'module_errors':{key:str(error) for key,error in module_errors.items()},'router_status':'draft','phone_guide_status':'tested-board prototype not yet generalized'}
    (run/'run.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    result=publish_outputs(job,run,paths,board['name'],output_folder)
    if make_router and clearance:result['clearance_diagnostic']=clearance
    if module_errors:result.update(partial_preview=True,module_errors=module_errors)
    return result


def publish_outputs(job,run,paths,board_name,output_folder=None):
    """Expose deliverables only; retain engine reports and earlier output internally."""
    staging=run/'publish';staging.mkdir()
    public={}
    if 'laser' in paths:
        destination=staging/'Laser';destination.mkdir()
        laser_format=json.loads((run/'run.json').read_text(encoding='utf-8'))['laser'].get('format','dxf')
        for source in paths['laser'].iterdir():
            if source.name!='laser-alignment-marks.dxf' and source.suffix in {'.dxf','.svg','.prn','.json','.tsv','.html'}:
                shutil.copyfile(source,destination/source.name)
        shutil.copyfile(paths['laser_review'],destination/'Review.html')
        public.update(laser=Path('Laser'),laser_review=Path('Laser/Review.html'))
    if 'router' in paths:
        destination=staging/'Router';destination.mkdir()
        for source in paths['router'].glob('*.mmg.draft'):
            shutil.copyfile(source,destination/source.name)
        shutil.copyfile(paths['router_review'],destination/'Review.html')
        public.update(router=Path('Router'),router_review=Path('Router/Review.html'))
    for key,label in [('laser','Laser'),('router','Router')]:
        review_key=key+'_review'
        if review_key in paths and key not in paths:
            destination=staging/label;destination.mkdir(exist_ok=True)
            shutil.copyfile(paths[review_key],destination/'Review.html');public[review_key]=Path(label+'/Review.html')
    from .job_guide import write_job_guide
    write_job_guide(run,staging)
    summary=json.loads((run/'run.json').read_text(encoding='utf-8'))
    if summary.get('registration_preview'):
        notice='<div style="background:#754c15;color:white;padding:8px;font:14px system-ui">PREVIEW ONLY · Alignment incomplete. Select at least two alignment holes and regenerate. XY zero is provisional; do not run these drafts.</div>'
        for html in staging.rglob('*.html'):
            content=html.read_text(encoding='utf-8')
            # Insert inside the body when explicit; HTML also permits an implicit body.
            if '<body>' in content:content=content.replace('<body>','<body>'+notice,1)
            else:content=content.replace('<header>',notice+'<header>',1)
            html.write_text(content,encoding='utf-8')
    destination=Path(output_folder) if output_folder else job/'Manufacturing Output'
    destination=destination.resolve()
    # Keep internal history inside this job; final output can be beside the board.
    if not run.resolve().is_relative_to(job.resolve()):
        raise ValueError('Internal run folder must remain inside the manufacturing job.')
    if destination.exists() and not (destination/'Start Here.html').is_file():
        raise ValueError('Choose a new output folder or an existing PCB Isolator output folder; this folder contains other files.')
    copy_delivery(staging,destination,run/'previous-output')
    manifest={'destination':str(destination),'files':{p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in destination.rglob('*') if p.is_file()},'status':'draft'}
    (run/'published.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return {'run':destination,'record':run,'guide':destination/'Start Here.html',**{key:destination/value for key,value in public.items()}}


def release_outputs(paths):
    """Release the exact reviewed bytes, without rerunning toolpath generation."""
    destination=Path(paths['run']);record=Path(paths['record'])
    if json.loads((record/'run.json').read_text(encoding='utf-8')).get('module_errors'):raise ValueError('Resolve or disable failed modules before final output.')
    if json.loads((record/'run.json').read_text(encoding='utf-8')).get('registration_preview'):
        raise ValueError('Select at least two alignment holes and regenerate the preview before creating final outputs.')
    job=record.parent.parent
    manifest=json.loads((record/'published.json').read_text(encoding='utf-8'))
    if (destination.resolve()!=Path(manifest.get('destination',job/'Manufacturing Output')).resolve()
            or not record.resolve().is_relative_to((job/'outputs').resolve())):
        raise ValueError('Release paths must match the generated output set.')
    if manifest['status']!='draft':raise ValueError('This output set has already been released.')
    actual={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in destination.rglob('*') if p.is_file()}
    if actual!=manifest['files']:
        raise ValueError('Output files have changed since generation. Generate and review a fresh set before release.')
    summary=json.loads((record/'run.json').read_text(encoding='utf-8'))
    if 'router' not in summary['outputs']:raise ValueError('This set has no router programs to release.')
    report=json.loads((record/'router/router-report.json').read_text(encoding='utf-8'))
    programs=report['programs']
    ordered=sorted(programs,key=lambda p:(0 if p['file'].startswith('spoilboard') else 2 if p['file'].startswith('pcb-profile') else 1,p.get('tool_diameter_mm',0)))
    mapping={}
    for number,p in enumerate(ordered,1):
        if p['file'].startswith('spoilboard'):
            diameter=p['nominal_pin_diameter_mm']
            tool='1_8' if abs(diameter-3.175)<.0001 else f'{diameter:g}'.replace('.','p')+'mm'
        elif p['file'].startswith('pcb-profile'):tool=f'{p["tool_diameter_mm"]:g}'.replace('.','p')+'mm'
        else:tool=f'{round(p["tool_diameter_mm"]*1000):04d}'
        mapping[p['file']]=f'{number:02d}-{tool}.mmg'
    staging=record/'release-stage';shutil.copytree(destination,staging)
    for old,new in mapping.items():
        shutil.copyfile(staging/'Router'/old,staging/'Router'/new)
        sync_retry((staging/'Router'/old).unlink)
    review=staging/'Router/Review.html'
    text=review.read_text(encoding='utf-8')
    for old,new in mapping.items():text=text.replace(old,new)
    text=text.replace('DRAFT · Machine setup remains to be checked','RELEASED · Operator approved this generated set')
    text=text.replace('Generated files retain the .mmg.draft suffix. This screen does not release machine-ready files.',
                      'Released files match the reviewed generation. Verify physical setup before running.')
    review.write_text(text,encoding='utf-8')
    when=datetime.now(timezone.utc).isoformat()
    from .job_guide import write_job_guide
    write_job_guide(record,staging,mapping,released=True)
    released={'status':'released','approved_at_utc':when,'files':{p.relative_to(staging).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in staging.rglob('*') if p.is_file()},'program_names':mapping}
    copy_delivery(staging,destination,record/'reviewed-draft-output')
    (record/'release.json').write_text(json.dumps(released,indent=2),encoding='utf-8')
    manifest['status']='released';(record/'published.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return paths


def export_preview(paths,output_folder,laser_format=None):
    """Publish the reviewed preview without regenerating its geometry."""
    if paths.get('partial_preview'):raise ValueError('Resolve or disable the failed module before generating final outputs. Both diagnostic reviews remain available.')
    record=Path(paths['record']);source=Path(paths['run'])
    summary=json.loads((record/'run.json').read_text(encoding='utf-8'))
    laser_format=laser_format or summary['laser'].get('format','both')
    if laser_format not in ('dxf','svg','both','direct'):raise ValueError('Choose DXF, SVG or both laser formats.')
    if json.loads((record/'run.json').read_text(encoding='utf-8')).get('registration_preview'):
        raise ValueError('Select at least two alignment holes and regenerate the preview before creating final outputs.')
    manifest=json.loads((record/'published.json').read_text(encoding='utf-8'))
    actual={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob('*') if p.is_file()}
    expected=manifest['files'] if manifest['status']=='draft' else json.loads((record/'release.json').read_text(encoding='utf-8'))['files']
    if actual!=expected:raise ValueError('Preview files changed. Generate a new preview first.')
    destination=Path(output_folder).resolve()
    if destination==source.resolve() or source.resolve().is_relative_to(destination):
        raise ValueError('Choose an output folder separate from the internal preview.')
    if destination.exists() and not (destination/'Start Here.html').is_file():
        raise ValueError('Choose a new folder or an existing PCB Isolator output folder.')
    if 'router' in paths and manifest['status']=='draft':release_outputs(paths)
    # Format is a delivery choice, not a new geometry generation. Check all
    # reviewed bytes above, then filter a separate delivery copy only.
    delivery=record/('delivery-'+uuid.uuid4().hex[:10])
    shutil.copytree(source,delivery)
    if 'laser' in paths and laser_format!='direct':
        keep={'.dxf','.svg'} if laser_format=='both' else {'.'+laser_format}
        for file in (delivery/'Laser').glob('laser-isolation-and-marks.*'):
            if file.suffix not in keep:file.unlink()
        for suffix in keep:
            if not (delivery/'Laser'/('laser-isolation-and-marks'+suffix)).is_file():
                raise ValueError('Selected format was not prepared in this older preview. Generate one new preview.')
    from .job_guide import write_job_guide
    mapping=json.loads((record/'release.json').read_text(encoding='utf-8'))['program_names'] if 'router' in paths else {}
    write_job_guide(record,delivery,mapping,released=True)
    copy_delivery(delivery,destination,record/'previous-final-output')
    (record/'delivery.json').write_text(json.dumps({'laser_format':laser_format,'destination':str(destination),
        'files':{file.relative_to(destination).as_posix():hashlib.sha256(file.read_bytes()).hexdigest()
                 for file in destination.rglob('*') if file.is_file()}},indent=2),encoding='utf-8')
    return {key:(value if key in ('record','clearance_diagnostic') else destination/Path(value).relative_to(source)) for key,value in paths.items()}


def refresh_laser_filter(board,paths,helix_settings,contours):
    """New reviewed set, preserving router bytes and the imported isolation plan."""
    source=Path(paths['record']);job=board['job']
    manifest=json.loads((source/'published.json').read_text(encoding='utf-8'))
    if manifest['status']!='draft':raise ValueError('Generate a new preview before editing released output.')
    summary=json.loads((source/'run.json').read_text(encoding='utf-8'))
    summary['laser']['helix']=helix_settings
    record=job/'outputs'/('app-run-filter-'+uuid.uuid4().hex[:10]);record.mkdir()
    shutil.copytree(source/'settings',record/'settings')
    if (source/'laser-plan.json').exists():shutil.copyfile(source/'laser-plan.json',record/'laser-plan.json')
    from .helix import prepare,LaserGridError
    laser=summary['laser'];destination=record/'laser'
    alignment=[f for f in board.get('alignment_candidates',board['features']) if f.id in summary['alignment_ids']]
    try:
        review=prepare(board['copper'],contours,alignment,destination,helix_settings,summary['board']+'_'+record.name,
            IsolationSettings(laser['width'],laser['overlap'],laser['lines'],laser.get('width_y') if laser.get('directional') else None,laser.get('spacing') if laser.get('directional') else None,laser.get('adaptive',True) if laser.get('directional') else False),print_features=board['features'],print_outline=board['outline'])
    except LaserGridError as error:error.prepared_contours=contours;raise
    internal={'run':record,'laser':destination,'laser_review':review}
    if 'router' in paths:
        shutil.copytree(source/'router',record/'router');internal.update(router=record/'router',router_review=record/'router/router-review.html')
    elif 'router_review' in paths:
        shutil.copyfile(paths['router_review'],record/'router-issues.html');internal['router_review']=record/'router-issues.html'
    summary['outputs']={key:Path(value).relative_to(record).as_posix() for key,value in internal.items() if key!='run'}
    (record/'run.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    result=publish_outputs(job,record,internal,board['name'],job/'outputs'/('preview-'+uuid.uuid4().hex[:10]))
    if paths.get('clearance_diagnostic'):result['clearance_diagnostic']=paths['clearance_diagnostic']
    if summary.get('module_errors'):result.update(partial_preview=True,module_errors=paths.get('module_errors',{}))
    return result
