"""Plan single-tool drilling/profile operations and reference-style draft MMG."""
import argparse
from hashlib import sha256
from collections import defaultdict
from datetime import datetime, timezone
import json
from math import ceil, isfinite
from pathlib import Path
import tomllib
import uuid

import ezdxf
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from .job_outputs import validate_selection
from .kicad_export import resolve_job_folder
from .outline import load_outline
from .pin_avoidance import avoid_pins, pin_settings,pin_obstacles
from .travel_optimizer import TravelCosts,optimize_points,optimize_cut_paths,join_paths,rapid_distance,travel_report


def load_machining(path):
    with Path(path).open('rb') as stream:
        config=tomllib.load(stream)
    config['machine'].setdefault('approach_mm',0.5)
    config['drilling'].setdefault('peck_resume_gap_mm',0.2)
    positive=[('board','thickness_mm'),('machine','clearance_mm'),('machine','park_z_mm'),
              ('drilling','feed_mm_min'),('profile','tool_diameter_mm'),('profile','feed_mm_min'),
              ('profile','plunge_mm_min'),('profile','stepdown_mm'),('spoilboard','pin_hole_depth_mm'),
              ('machine','approach_mm')]
    for section,key in positive:
        value=config[section][key]
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value) or value<=0:
            raise ValueError(f'{section}.{key} must be positive and finite.')
    for section,key in [('board','breakthrough_mm'),('drilling','peck_mm')]:
        if not isfinite(config[section][key]) or config[section][key]<0:
            raise ValueError(f'{section}.{key} must be nonnegative and finite.')
    for key in ('origin_x_mm','origin_y_mm'):
        if not isfinite(config['machine'][key]):
            raise ValueError('Work origin must be finite.')
    if config['machine']['park_z_mm']<config['machine']['clearance_mm']:
        raise ValueError('Park Z must be at least clearance Z.')
    if config['machine']['approach_mm']>config['machine']['clearance_mm']:
        raise ValueError('Approach height must not exceed travel clearance.')
    drilling_options(config)
    from .drill_grouping import assignments
    assignments(config)
    sizes=[]
    for tool in config['drilling'].get('tools',[]):
        diameter=tool.get('diameter_mm')
        if not isinstance(diameter,(int,float)) or isinstance(diameter,bool) or not isfinite(diameter) or diameter<=0:
            raise ValueError('Drill override diameter must be positive and finite.')
        if any(abs(diameter-old)<=1e-6 for old in sizes):
            raise ValueError('Duplicate drill size override.')
        sizes.append(diameter)
        drilling_options(config,diameter)
    drilling_options(config,override=config['spoilboard'])
    pin_settings(config)
    return config


def drilling_options(config,diameter=None,override=None):
    base=config['drilling']
    settings={key:base.get(key,default) for key,default in
              [('feed_mm_min',127.0),('peck_mm',0.0),('peck_retract_mm',1.0),('peck_resume_gap_mm',0.2)]}
    if diameter is not None:
        matches=[tool for tool in base.get('tools',[]) if abs(tool['diameter_mm']-diameter)<=1e-6]
        if len(matches)>1:
            raise ValueError('Multiple drill overrides match one diameter.')
        if matches:
            settings.update({k:v for k,v in matches[0].items() if k in settings})
    if override is not None:
        settings.update({k:v for k,v in override.items() if k in settings})
    for key,value in settings.items():
        minimum=0 if key=='peck_mm' else 1e-12
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value) or value<minimum:
            raise ValueError(f'Drilling {key} is invalid.')
    if settings['peck_retract_mm']>config['machine']['clearance_mm']:
        raise ValueError('Peck retract height must not exceed travel clearance.')
    if config['machine'].get('approach_mm',0.5)>settings['peck_retract_mm']:
        raise ValueError('Approach height must not exceed peck retract height.')
    return settings


def depth_passes(depth, step):
    # Avoid a duplicate final pass when decimal arithmetic yields 2.0000000004.
    count=max(1,ceil(depth/step-1e-12))
    return [-min(i*step,depth) for i in range(1,count+1)]


def drill_moves(features,depth,config,override=None):
    safe=config['machine']['clearance_mm']
    moves=[{'g':0,'z':safe}]
    for feature in features:
        if feature.end is not None:
            raise ValueError('Slots require a milling operation, not a drill plunge.')
        settings=drilling_options(config,feature.diameter_mm if override is None else None,override)
        feed=settings['feed_mm_min']
        peck=settings['peck_mm']
        moves.append({'g':0,'x':feature.x,'y':feature.y})
        passes=depth_passes(depth,peck if peck>0 else depth)
        for index,z in enumerate(passes):
            approach=config['machine'].get('approach_mm',0.5)
            if index:
                approach=min(approach,passes[index-1]+settings['peck_resume_gap_mm'])
            moves.append({'g':0,'z':approach})
            moves.append({'g':1,'z':z,'f':feed})
            retract=settings['peck_retract_mm'] if index<len(passes)-1 else safe
            moves.append({'g':0,'z':retract})
    return moves


class CutoutFitError(ValueError):
    def __init__(self,message,issues):super().__init__(message);self.feature_diagnostic={'issues':issues}


def cutout_info(polygon):
    from shapely import normalize
    return dict(id='cutout-'+sha256(normalize(polygon).wkb).hexdigest()[:16],source_center=[polygon.centroid.x,polygon.centroid.y],bounds=list(polygon.bounds),points=list(polygon.exterior.coords))


def compensated_profiles(rings,diameter,ignored_cutouts=None):
    polygons=[Polygon(ring.coords) for ring in rings]
    if any(not p.is_valid or p.is_empty for p in polygons):
        raise ValueError('Invalid outline polygon.')
    polygons.sort(key=lambda p:p.area,reverse=True)
    outside=polygons[0]
    holes=polygons[1:]
    if any(not outside.contains(hole) for hole in holes):
        raise ValueError('This version supports one board outline with internal cutouts.')
    if any(a.intersects(b) for i,a in enumerate(holes) for b in holes[i+1:]):
        raise ValueError('Nested or overlapping cutouts are not supported.')
    paths=[];issues=[]
    ignored={entry['id'] for entry in (ignored_cutouts or [])}
    # Internal cuts first, final external cut last. Compensation is in geometry,
    # not controller G41/G42 commands. No tab or ramp behavior is implied.
    for polygon in holes+[outside]:
        is_outer=polygon is outside
        info=cutout_info(polygon)
        if not is_outer and info['id'] in ignored:continue
        offset=polygon.buffer((diameter/2)*(1 if is_outer else -1),quad_segs=64)
        if offset.is_empty or offset.geom_type!='Polygon' or offset.interiors:
            x0,y0,x1,y1=polygon.bounds
            if is_outer:raise ValueError('Outer profile compensation is invalid. The outside profile cannot be ignored; revise the outline or tool.')
            info.update(tool_diameter_mm=diameter,reason=f'{diameter:g} mm tool cannot fit {x1-x0:.3f} x {y1-y0:.3f} mm cutout bounds')
            issues.append(info);continue
        # Consistent contour traversal; all output uses G1, as in Profile.mmg.
        offset=orient(offset,sign=-1 if is_outer else 1)
        paths.append({'kind':'outside' if is_outer else 'inside','points':list(offset.exterior.coords)})
    if issues:
        first=issues[0];x0,y0,x1,y1=first['bounds'];x,y=first['source_center']
        raise CutoutFitError(f'Cutter does not fit a cutout or compensation changed topology. Tool diameter {diameter:g} mm; internal cutout bounds {x1-x0:.3f} x {y1-y0:.3f} mm at source X{x:.3f}, Y{y:.3f}. {len(issues)} affected cutouts. Choose a smaller profile tool, omit these internal cutouts, or continue with laser only.',issues)
    return paths


def profile_moves(paths,depth,config):
    safe=config['machine']['clearance_mm']
    settings=config['profile']
    moves=[{'g':0,'z':safe}]
    for path in paths:
        x,y=path['points'][0]
        moves.append({'g':0,'x':x,'y':y})
        moves.append({'g':0,'z':config['machine'].get('approach_mm',0.5)})
        points=path['points']
        for z in depth_passes(depth,settings['stepdown_mm']):
            moves.append({'g':1,'z':z,'f':settings['plunge_mm_min']})
            moves.extend({'g':1,'x':x,'y':y,'f':settings['feed_mm_min']} for x,y in points[1:])
            if not path.get('closed',True):points=points[::-1]
        moves.append({'g':0,'z':safe})
    return moves


def xy_first_startup(moves,config):
    """Replace only the virtual staged approach with a direct XY move at current Z.

    The operator's tool-setting cycle leaves Z at machine maximum. No unknown
    initial XY route or initial Z distance can be checked by this program.
    """
    clearance=config['machine']['clearance_mm']
    if not moves or set(moves[0])!={'g','z'} or moves[0]['g']!=0 or moves[0]['z']<clearance:
        raise ValueError('Rapid XY startup requires an initial clearance Z and a cutting destination.')
    target=None;safe=moves[0]['z'];count=0;index=1
    while index<len(moves):
        move=moves[index]
        if move['g']!=0 or ('z' in move and move['z']<clearance):break
        if 'z' in move:
            if set(move)!={'g','z'}:raise ValueError('Startup XY and Z must be separate moves.')
            safe=move['z']
        else:
            if set(move)!={'g','x','y'}:raise ValueError('Startup needs complete XY coordinates.')
            target=dict(move);count+=1
        index+=1
    if target is None or index==len(moves):
        raise ValueError('Rapid XY startup has no first hole or cutting start.')
    work=[target[a]-config['machine']['origin_'+a+'_mm'] for a in ('x','y')]
    return [target,{'g':0,'z':safe},*moves[index:]],{
        'policy':'xy_first_at_tool_set_max_height','first_work_xy_mm':work,
        'initial_xy_unknown':True,'initial_z_unknown':True,
        'requires_tool_set_max_height':True,'discarded_staged_xy_moves':count}


def startup_distance(moves,config):
    planned,info=xy_first_startup(moves,config)
    x,y=info['first_work_xy_mm']
    measured={**config,'alignment_pins':{**config['alignment_pins'],'start_x_mm':x,'start_y_mm':y}}
    return rapid_distance(planned,measured)


def write_draft(path,moves,config,label):
    machine=config['machine']
    moves,startup=xy_first_startup(moves,config)
    lines=['(DRAFT - SETUP AND TOOLING NOT CONFIRMED)',
           '(Requires controller in millimeters and absolute coordinates)',
           '(Spindle speed set manually)',
           '(XY FIRST STARTUP - TOOL SETTING MUST LEAVE Z AT MAX HEIGHT)',
           '(First XY positioning is at current Z; then lower at first hole or cut start)',
           f'({label})','N10M03']
    n=20
    z=None
    for index,move in enumerate([*moves,{'g':0,'z':machine['park_z_mm']}]):
        if ('x' in move or 'y' in move) and move['g']==0 and (z is None or z<machine['clearance_mm']) and index!=0:
            raise ValueError('Rapid XY move before safe Z.')
        line=f'N{n}G'+('00' if move['g']==0 else '1')
        for axis in ('x','y','z'):
            if axis in move:
                value=move[axis]-(machine['origin_'+axis+'_mm'] if axis in ('x','y') else 0)
                line+=axis.upper()+f'{value:.3f}'
        if 'f' in move:
            line+=f'F{move["f"]:.1f}'
        if 'z' in move:
            z=move['z']
        lines.append(line)
        n+=10
    lines.extend([f'N{n}M05',f'N{n+10}M30','%'])
    path.write_bytes(('\r\n'.join(lines)+'\r\n').encode('ascii'))
    return startup


def prepare_router_drafts(folder,config_path=Path('machining.toml'),adjust_margin=False):
    job=resolve_job_folder(folder)
    selection=json.loads((job/'outputs/pcb-job.json').read_text(encoding='utf-8'))
    _,outline,alignment,remaining,pins=validate_selection(job,selection)
    config=load_machining(config_path)
    if any(f.end is not None for f in remaining):
        raise ValueError('Slot toolpaths are not implemented yet.')
    depth=config['board']['thickness_mm']+config['board']['breakthrough_mm']
    rings=load_outline(outline)
    registration_cutouts=[{'id':f.id.removeprefix('outline:')} for f in alignment if f.id.startswith('outline:')]
    paths=compensated_profiles(rings,config['profile']['tool_diameter_mm'],config['profile'].get('ignored_cutouts',[])+registration_cutouts)
    from .kicad_export import separation_input
    from .separation import load_separation,separation_paths
    separation=separation_input(job)
    separations,separation_report=separation_paths(load_separation(separation) if separation else [],rings,
        (config['machine']['origin_x_mm'],config['machine']['origin_y_mm']))
    profiles=paths
    paths=separations+profiles
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output=job/'outputs'/('router-draft-'+stamp+'-'+uuid.uuid4().hex[:6])
    output.mkdir(parents=True)
    from .drill_grouping import group_drills
    groups,source_sizes=group_drills(remaining,config)
    from .clearance import measure_clearance,ClearanceError
    operations=[(f'Drill {diameter:g} mm',drill_moves(features,depth,config),diameter) for diameter,features in sorted(groups.items())]
    operations.append(('Separation / profile',profile_moves(paths,depth,config),config['profile']['tool_diameter_mm']))
    diagnostic=measure_clearance(operations,alignment,pins,config)
    if diagnostic and diagnostic['maximum_margin_mm']<config['alignment_pins']['xy_margin_mm']:
        maximum=diagnostic['maximum_margin_mm']
        if not adjust_margin or maximum<.01:
            raise ClearanceError(f'Pin clearance conflict in {diagnostic["operation"]}. Maximum XY margin: {maximum:.3f} mm. '+
                                 ('Physical clearance is insufficient; change pins, tooling or setup.' if maximum<.01 else 'Reduce XY margin or change the setup.'),diagnostic)
        config['alignment_pins']['xy_margin_mm']=maximum
        diagnostic['applied_margin_mm']=maximum
    report={'status':'DRAFT','units':'mm','machine_modes_assumed':['millimeters','absolute'],
            'configuration':config,'programs':[],'alignment_excluded':selection['alignment_ids'],
            'registration_cutouts':registration_cutouts,'profile_cutting_depth_mm':depth,'tabs':False,'profile_arcs_linearized':True,
            'clearance_diagnostic':diagnostic if diagnostic and 'applied_margin_mm' in diagnostic else None,
            'ignored_cutouts':[cutout_info(Polygon(r.coords)) for r in rings if cutout_info(Polygon(r.coords))['id'] in {entry['id'] for entry in config['profile'].get('ignored_cutouts',[])}]}
    planned_operations=[]
    start=config['alignment_pins']
    start_xy=(start['start_x_mm']+config['machine']['origin_x_mm'],start['start_y_mm']+config['machine']['origin_y_mm'])
    start_label='XY FIRST AT TOOL-SET MAX HEIGHT'
    for diameter,features in sorted(groups.items()):
        name=f'pcb-drill-{diameter:.6f}mm.mmg.draft'
        planned,avoidance=avoid_pins(drill_moves(features,depth,config),alignment,pins,diameter,config,start_at_first=True)
        before=startup_distance(planned,config)
        ordered=optimize_points(features,start_xy,TravelCosts(pin_obstacles(alignment,pins,diameter,config)))
        candidate,candidate_avoidance=avoid_pins(drill_moves(ordered,depth,config),alignment,pins,diameter,config,start_at_first=True)
        after=startup_distance(candidate,config)
        if after<before-1e-6:planned,avoidance,features=candidate,candidate_avoidance,ordered
        else:after=before
        optimization=travel_report(before,after,'nearest-neighbor, row/column sweeps and 2-opt; pin-aware')
        optimization['comparison']='Rounded inter-feature XY travel and pin detours; unknown initial positioning excluded'
        startup=write_draft(output/name,planned,config,'PCB drilling - '+start_label)
        planned_operations.append((name,xy_first_startup(planned,config)[0],avoidance))
        report['programs'].append({'file':name,'startup':startup,'tool_diameter_mm':diameter,'holes':len(features),'z_zero':'board_top',
                                   'source_hole_sizes':[{'diameter_mm':size,'count':count} for size,count in sorted(source_sizes[diameter].items())],
                                   'drilling':drilling_options(config,diameter),'pin_avoidance':avoidance,
                                   'travel_optimization':optimization,'hole_order':[f.id for f in features]})
    name='spoilboard-pins.mmg.draft'
    if alignment:
        pin_order=sorted(alignment,key=lambda f:(f.x-config['machine']['origin_x_mm'])**2+(f.y-config['machine']['origin_y_mm'])**2)
        startup=write_draft(output/name,drill_moves(pin_order,config['spoilboard']['pin_hole_depth_mm'],config,
                                      override=config['spoilboard']),config,'Spoilboard pin holes - '+start_label)
        report['programs'].append({'file':name,'startup':startup,'nominal_pin_diameter_mm':pins,'holes':len(alignment),'z_zero':'spoilboard_top',
                               'tool_and_fit_not_confirmed':True,
                               'start_work_xy_mm':startup['first_work_xy_mm']})
    name='pcb-profile.mmg.draft'
    planned,avoidance=avoid_pins(profile_moves(paths,depth,config),alignment,pins,config['profile']['tool_diameter_mm'],config,start_at_first=True)
    before=startup_distance(planned,config)
    if separations:
        costs=TravelCosts(pin_obstacles(alignment,pins,config['profile']['tool_diameter_mm'],config))
        candidate_paths=optimize_cut_paths(join_paths(separations),start_xy,profiles[0]['points'][0],
            len(depth_passes(depth,config['profile']['stepdown_mm'])),costs)+profiles
        candidate,candidate_avoidance=avoid_pins(profile_moves(candidate_paths,depth,config),alignment,pins,config['profile']['tool_diameter_mm'],config,start_at_first=True)
        after=startup_distance(candidate,config)
        if after<=before+1e-8:
            planned,avoidance,paths=candidate,candidate_avoidance,candidate_paths
        else:after=before
    else:after=before
    separation_report['machined_paths']=sum(p['kind']=='separation' for p in paths)
    optimization=travel_report(before,after,'joined centerlines, nearest-neighbor, 2-opt and entry-direction optimization; profile last')
    optimization['comparison']='Rounded inter-feature XY travel and pin detours; unknown initial positioning excluded'
    startup=write_draft(output/name,planned,config,'PCB separation then profile - '+start_label if separations else 'PCB profile - '+start_label)
    planned_operations.append((name,xy_first_startup(planned,config)[0],avoidance))
    report['programs'].append({'file':name,'startup':startup,'tool_diameter_mm':config['profile']['tool_diameter_mm'],'z_zero':'board_top',
                               'pin_avoidance':avoidance,'separation':separation_report,'travel_optimization':optimization})
    drawing=ezdxf.new('R2010'); drawing.units=4
    for index,path in enumerate(paths):
        layer=f'CUTTER_CENTER_{path["kind"].upper()}_{index+1}'
        drawing.layers.new(layer)
        closed=path.get('closed',True)
        drawing.modelspace().add_lwpolyline(path['points'][:-1] if closed else path['points'],close=closed,dxfattribs={'layer':layer})
    drawing.saveas(output/'profile-cutter-centers.dxf')
    review=ezdxf.new('R2010');review.units=4
    review.layers.new('ALIGNMENT_PINS',dxfattribs={'color':1})
    review.layers.new('PIN_KEEPOUT',dxfattribs={'color':2})
    largest=max(info['keepout_radius_mm'] for _,_,info in planned_operations)
    for feature in alignment:
        review.modelspace().add_circle((feature.x,feature.y),pins/2,dxfattribs={'layer':'ALIGNMENT_PINS'})
        if largest>0:review.modelspace().add_circle((feature.x,feature.y),largest,dxfattribs={'layer':'PIN_KEEPOUT'})
    for index,(name,planned,info) in enumerate(planned_operations):
        rapid=f'TRAVEL_TOOL_{index+1}';cut=f'CUT_TOOL_{index+1}'
        review.layers.new(rapid,dxfattribs={'color':4})
        review.layers.new(cut,dxfattribs={'color':3})
        xy=(planned[0]['x'],planned[0]['y'])
        for move in planned:
            if 'x' in move or 'y' in move:
                target=(move.get('x',xy[0]),move.get('y',xy[1]))
                if target!=xy:
                    review.modelspace().add_line(xy,target,dxfattribs={'layer':rapid if move['g']==0 else cut})
                xy=target
    review.saveas(output/'pin-avoidance-review.dxf')
    for program in report['programs']:
        program['sha256']=sha256((output/program['file']).read_bytes()).hexdigest()
    (output/'router-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'alignment-selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
    from .app_backend import write_toml
    write_toml(output/'machining.toml',config)
    from .router_review import write_router_review
    write_router_review(output)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job',type=Path)
    parser.add_argument('--config',type=Path,default=Path('machining.toml'))
    args=parser.parse_args()
    try:
        output=prepare_router_drafts(args.job,args.config)
    except Exception as error:
        parser.exit(1,f'Could not prepare router drafts: {error}\n')
    print(f'Router drafts prepared:\n{output}')
    print('Drafts only. Tool sizes, feeds, work origin, board thickness and workholding must be checked.')


if __name__=='__main__':
    main()
