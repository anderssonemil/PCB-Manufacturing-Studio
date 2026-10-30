"""Build the portable operation guide from a desktop run's actual files."""
import json
from hashlib import sha256
from pathlib import Path

from .kicad_export import load_job
from .outline import load_outline
from .operation_guide import write_html
from .router_review import parse_draft


def build_job_guide(record,folder,names=None,released=False):
    import ezdxf
    from ezdxf.path import make_path
    record=Path(record);folder=Path(folder);names=names or {}
    summary=json.loads((record/'run.json').read_text(encoding='utf-8'))
    config=summary['router'];machine=config['machine'];start=config['alignment_pins']
    ox,oy=summary['source_origin_xy_mm']
    selection=json.loads((record/'settings/alignment-selection.json').read_text(encoding='utf-8'))
    features={f['id']:f for f in selection['features']+selection.get('outline_candidates',[])}
    _,_,outline=load_job(record.parent.parent)
    outlines=[[[x-ox,y-oy] for x,y in ring.coords] for ring in load_outline(outline)]
    pins=[{'x':features[i]['x']-ox,'y':features[i]['y']-oy,'radius':selection['pin_diameter_mm']/2} for i in selection['alignment_ids']]
    fingerprints={};programs={};steps=[];laser_commands=[];marks=[]
    def add(id,title,phase,tool,view,facts,actions,note='',**extra):
        steps.append(dict(id=id,title=title,phase=phase,tool=tool,view=view,facts=facts,actions=actions,note=note,**extra))
    laser=folder/'Laser/laser-isolation-and-marks.dxf'
    svg=folder/'Laser/laser-isolation-and-marks.svg'
    if laser.exists() or svg.exists():
        chosen=svg if svg.exists() else laser
        for deliverable in (laser,svg):
            if deliverable.exists():fingerprints['Laser/'+deliverable.name]=sha256(deliverable.read_bytes()).hexdigest()
        drawing=laser if laser.exists() else record/'laser/laser-isolation-and-marks.dxf'
        for entity in ezdxf.readfile(drawing).modelspace():
            points=list(make_path(entity).flattening(distance=.01))
            if points:
                command='M'+' L'.join(f'{p.x-ox:.4f},{-(p.y-oy):.4f}' for p in points)
                (marks if entity.dxf.layer=='ALIGNMENT_CENTER_MARKS' else laser_commands).append(command)
        settings=summary['laser']
        add('laser','Laser isolation and alignment marks','Laser','Laser · painted copper board','laser',
            [['Scale','1:1 · millimeters'],['Isolation',f'{settings["lines"]} maximum lanes' if settings.get('adaptive',settings.get('directional',False)) else f'{settings["lines"]} lines']]+([['Trial removal X/Y',f'{settings["width"]:g} / {settings["width_y"]:g} mm'],['Lane spacing',f'{settings["spacing"]:g} mm']] if settings.get('directional') else [['Effective width',f'{settings["width"]:g} mm'],['Overlap',f'{settings["overlap"]:g}%']]),
            [f'Open Laser/{chosen.name} in your laser printing application.'+(' Both SVG and DXF are included for comparison; print only one.' if laser.exists() and svg.exists() else ''),
             'Confirm 1:1 scale and board orientation. Use your tuned paint-removal settings.',
             ('Engrave the isolation paths and alignment center marks. Keep the marked hole centers identifiable.' if pins else 'Engrave the isolation paths. No alignment holes or center marks are selected.')],
            'The alignment marks are included in the combined laser file.' if pins else 'Laser-only boards do not require registration holes.',filename='Laser/'+chosen.name)
        add('etch','Etch, clean and inspect','Board preparation','Your established etching process','outline',[],
            ['Etch the exposed copper using your established process, then clean the board.',
             'Inspect for copper bridges, damaged traces and clearly identifiable alignment marks.'],
            'Use your established chemical handling procedure.')
    direct=folder/'Laser/helix-job.json'
    if direct.exists():
        d=json.loads(direct.read_text(encoding='utf-8'));s=d['settings']
        for filename in ('laser-job.prn','helix-job.json','helix-paths.tsv'):
            fingerprints['Laser/'+filename]=sha256((folder/'Laser'/filename).read_bytes()).hexdigest()
        step=25.4/s['dpi']
        source=folder/'Laser/helix-paths.tsv'
        left,top=d['source_left'],d['source_top']
        for row in source.read_text(encoding='ascii').splitlines()[1:]:
            points=[tuple(map(int,point.split(','))) for point in row.split()]
            laser_commands.append('M'+' L'.join(f'{x*step-s["x"]+left-ox:.6f},{y*step-s["y"]-top+oy:.6f}' for x,y in points))
        add('laser','Direct Helix isolation and alignment marks','Laser','Laser · painted copper board','laser',
            [['Ignored tiny fragments',str(len(d.get('ignored_tiny_fragments',[])))],['Connection',f'{s["host"]}:{s["port"]}'],['Speed / power',f'{s["speed"]}% / {s["power"]}%'],['Frequency / DPI',f'{s["frequency"]} Hz / {s["dpi"]} DPI'],['Laser offset',f'X{s["x"]:g} Y{s["y"]:g} mm'],['Estimated time',d['timing']['label']]],
            ['Review Laser/Review.html, including any red omitted-fragment markers. Artwork top-left is placed at laser X0/Y0 plus the configured positive offsets; router XY datum is separate.',
             'Position painted material, set focus manually and confirm air/exhaust manually. Autofocus is disabled.',
             'Use Send to laser in PCB Isolator and confirm the settings. Wait for the complete-job acknowledgement.',
             'Select the indicated PCB job at the Helix panel and start it when ready. Sending does not start the laser.'],
            'SVG/DXF export is disabled in this build. Laser-job.prn is Epilog printer data, not CNC G-code. No air-assist control is included.',filename='Laser/laser-job.prn')
        add('etch','Etch, clean and inspect','Board preparation','Your established etching process','outline',[],
            ['Clean and etch using your established process.','Inspect for bridges, damaged traces and readable alignment marks.'])
    report_path=record/'router/router-report.json'
    if (folder/'Router').exists() and report_path.exists() and not summary.get('module_errors',{}).get('router'):
        report=json.loads(report_path.read_text(encoding='utf-8'))
        largest=max((p.get('pin_avoidance',{}).get('keepout_radius_mm',0) for p in report['programs']),default=0)
        for pin in pins:pin['keepout_radius_mm']=0 if start.get('pins_removed_before_machining') else largest or pin['radius']
        ordered=sorted(report['programs'],key=lambda p:(0 if p['file'].startswith('spoilboard') else 2 if p['file'].startswith('pcb-profile') else 1,p.get('tool_diameter_mm',0)))
        start_label=f'X{start["start_x_mm"]:g}, Y{start["start_y_mm"]:g} mm'
        zero=f'Alignment hole at source X{ox:g}, Y{oy:g} mm'
        for number,info in enumerate(ordered):
            first_xy=info.get('startup',{}).get('first_work_xy_mm',[start['start_x_mm'],start['start_y_mm']])
            start_label=f'X{first_xy[0]:g}, Y{first_xy[1]:g} mm'
            startup_action=(f'After tool-height setting, leave Z at machine maximum. The program first moves XY to {start_label}, then lowers Z. Set spindle speed manually.'
                            if info.get('startup') else f'Stage the raised tool at work {start_label}. Set spindle speed manually.')
            original=info['file'];name=names.get(original,original);path=folder/'Router'/name
            if sha256(path.read_bytes()).hexdigest()!=info['sha256']:
                raise ValueError('Guide program differs from generated toolpath: '+name)
            fingerprints['Router/'+name]=sha256(path.read_bytes()).hexdigest()
            segments,plunges=parse_draft(path.read_text(encoding='ascii'),[start['start_x_mm'],start['start_y_mm']])
            programs[name]={'segments':segments,'plunges':plunges}
            spoil=original.startswith('spoilboard');profile=original.startswith('pcb-profile')
            diameter=info.get('tool_diameter_mm',info.get('nominal_pin_diameter_mm'))
            depths=sorted({p['z'] for p in plunges if p['z']<0},reverse=True)
            facts=[['Tool diameter',f'{diameter:g} mm'],['Z zero','SPOILBOARD TOP' if spoil else 'PCB TOP'],
                   ['First work XY',start_label],['XY zero',zero],['Cut depths',' / '.join(f'{z:g}' for z in depths)+' mm']]
            if 'holes' in info:facts.append(['Hole count',str(info['holes'])])
            if info.get('source_hole_sizes'):
                facts.append(['KiCad hole sizes',' / '.join(f'{r["count"]} × {r["diameter_mm"]:g} mm' for r in info['source_hole_sizes'])])
                if any(abs(r['diameter_mm']-diameter)>1e-6 for r in info['source_hole_sizes']):
                    facts.append(['Size override','These holes use the chosen drill diameter; original KiCad sizes are unchanged.'])
            feed=sorted({p['feed'] for p in plunges if p.get('feed') is not None})
            if feed:facts.append(['Plunge feed',' / '.join(f'{f:g}' for f in feed)+' mm/min'])
            if profile and report.get('ignored_cutouts'):facts.append(['Omitted internal cutouts',str(len(report['ignored_cutouts']))+' — material remains uncut'])
            if profile:facts.append(['Profile XY feed',f'{config["profile"]["feed_mm_min"]:g} mm/min'])
            if spoil:
                title='Drill the spoilboard pin holes';id='spoil'
                actions=['Stop the program and spindle before installing the pin-hole drill.',
                         f'Set XY zero at the intended alignment-hole center ({zero}). Set Z zero on TOP OF THE SPOILBOARD.',
                         startup_action,
                         f'Run Router/{name} before inserting any pins. Verify the resulting pin fit.']
                note='Pins must not be installed during spoilboard drilling.'
            else:
                title='Cut the board profile' if profile else f'Drill {diameter:g} mm PCB holes'
                if profile and info.get('separation',{}).get('paths'):
                    title='Cut separation lines, then the board profile'
                    facts.append(['Separation cutting chains',str(info['separation'].get('machined_paths',info['separation']['paths']))])
                id='profile' if profile else f'drill-{number}'
                actions=[f'Stop the program and spindle, then install the {diameter:g} mm '+('profile cutter.' if profile else 'PCB drill.'),
                         'Reset Z zero on TOP OF THE PCB for this tool. Retain the alignment-hole XY datum.',
                         startup_action,
                         f'Run Router/{name}. '+('Wait for the spindle to stop before removing the board.' if profile else 'Inspect the holes before changing tools.')]
                if profile:actions.insert(2,'Verify actual cutter diameter and hold-down through the final cut. This program has no tabs.')
                if profile and info.get('separation',{}).get('paths'):
                    actions.insert(3,'This program cuts CNC Separation centerlines first, then internal cutouts and the outer profile last. Short line endpoints leave your drawn bridges intact. Check hold-down for every section.')
                note=f'Configured PCB thickness {config["board"]["thickness_mm"]:g} mm + breakthrough {config["board"]["breakthrough_mm"]:g} mm. Pins must be removed after tape registration; normal travel clearance is used.'
            keepout=info.get('pin_avoidance',{}).get('keepout_radius_mm')
            add(id,title,'Router · before pins' if spoil else 'Router · profile' if profile else 'Router · PCB drilling',
                f'Install {diameter:g} mm '+('profile cutter' if profile else 'drill'),'router',facts,actions,note,
                filename='Router/'+name,program=name,hole_radius_mm=diameter/2,keepout_radius_mm=keepout)
            if spoil:
                add('mount','Register and secure the PCB','PCB setup',f'{selection["pin_diameter_mm"]:g} mm pins + double-sided tape','pins',
                    [['Alignment holes',str(len(pins))],['Pins during machining','REMOVE before starting'],['XY zero',zero]],
                    ['Manually drill the PCB alignment holes at the laser center marks to fit your pins.',
                     'Place the PCB on the spoilboard pins and secure it with double-sided tape.',
                     'Confirm board orientation, seating and hold-down. Keep the same XY datum.',
                     'REMOVE ALL PINS after pressing the tape firmly. Verify the board is secure before running PCB operations.'],
                    'The XY datum is at the selected alignment hole. Each new program positions directly over its first hole or cutting start before lowering Z. '+' '.join(selection.get('registration_warnings',[])))
    add('inspect','Inspect the completed board','Finish','Board inspection and component fit','pins',[],
        ['Inspect the profile, hole sizes, trace clearances and component fit.',
         'Record any setting changes with this manufacturing run before making another version.'],
        'Guide completion is your manual record; it does not read or control the machines.')
    return dict(version=1,job_key=sha256(json.dumps(fingerprints,sort_keys=True).encode()).hexdigest()[:16],
                board_name=summary['board'],export_id=summary['export'],files=fingerprints,steps=steps,
                programs=programs,pins=pins,outline=outlines,laser_path=' '.join(laser_commands),mark_path=' '.join(marks),
                setup_note='Released output' if released else 'DRAFT PREVIEW · Generate outputs before using machine files.',
                review_links={key:relative for key,relative in [('Laser review','Laser/Review.html'),('Router review','Router/Review.html')] if (folder/relative).exists()})


def write_job_guide(record,folder,names=None,released=False):
    data=build_job_guide(record,folder,names,released)
    write_html(data,Path(folder)/'Start Here.html')
    return data
