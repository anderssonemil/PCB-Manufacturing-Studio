"""Offline review screen built from the generated draft programs themselves."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import webbrowser

from .kicad_export import load_job, resolve_job_folder
from .outline import load_outline


def copper_svg_path(geometry,origin):
    """A simplified display overlay only; manufacturing geometry is unchanged."""
    ox,oy=origin;commands=[]
    geometry=geometry.simplify(.01,preserve_topology=True)
    polygons=[geometry] if geometry.geom_type=='Polygon' else geometry.geoms
    for polygon in polygons:
        for ring in [polygon.exterior,*polygon.interiors]:
            commands.append('M'+' L'.join(f'{x-ox:.4f},{-(y-oy):.4f}' for x,y in ring.coords)+' Z')
    return ' '.join(commands)


def parse_draft(text,start):
    state={'x':start[0],'y':start[1],'z':None}
    segments=[]
    plunges=[]
    speed_commands=[]
    xy_first='XY FIRST STARTUP - TOOL SETTING MUST LEAVE Z AT MAX HEIGHT' in text
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('(') or line=='%':
            continue
        words={k:float(v) for k,v in re.findall(r'([A-Z])([-+]?\d+(?:\.\d*)?)',line)}
        if 'S' in words:
            speed_commands.append(words['S'])
        if 'G' not in words:
            continue
        if words['G'] not in (0,1):
            raise ValueError('Review currently supports only the generated G00/G1 programs.')
        old=dict(state)
        for axis in ('x','y','z'):
            if axis.upper() in words:
                state[axis]=words[axis.upper()]
        if ('X' in words or 'Y' in words) and not (xy_first and state['z'] is None):
            segments.append({'from':[old['x'],old['y']],'to':[state['x'],state['y']],
                             'rapid':words['G']==0,'z':state['z']})
        if words['G']==1 and 'Z' in words:
            plunges.append({'x':state['x'],'y':state['y'],'z':state['z'],'feed':words.get('F')})
    if speed_commands:
        raise ValueError('Unexpected spindle-speed command in draft output.')
    return segments,plunges


def write_router_review(folder):
    folder=Path(folder).resolve()
    report=json.loads((folder/'router-report.json').read_text(encoding='utf-8'))
    config=report['configuration']
    job=folder.parent.parent
    saved_selection=folder/'alignment-selection.json'
    selection=json.loads((saved_selection if saved_selection.exists() else job/'outputs/pcb-job.json').read_text(encoding='utf-8'))
    if selection['alignment_ids']!=report['alignment_excluded']:
        raise ValueError('Alignment selection changed; regenerate the router draft.')
    copper,_,outline=load_job(job)
    ox,oy=config['machine']['origin_x_mm'],config['machine']['origin_y_mm']
    bounds_paths=[[(x-ox,y-oy) for x,y in ring.coords] for ring in load_outline(outline)]
    features={f['id']:f for f in selection['features']+selection.get('outline_candidates',[])}
    pins=[{'x':features[i]['x']-ox,'y':features[i]['y']-oy,'radius':selection['pin_diameter_mm']/2}
          for i in selection['alignment_ids']]
    programs=[]
    registration_warnings=selection.get('registration_warnings',[])
    # Show actual workflow order: spoilboard before pins are inserted, drills,
    # then the profile after PCB pin registration.
    ordered=sorted(report['programs'],key=lambda p:(0 if p['file'].startswith('spoilboard') else
                                                   2 if p['file'].startswith('pcb-profile') else 1,p['file']))
    for info in ordered:
        path=(folder/info['file']).resolve()
        if path.parent!=folder:
            raise ValueError('Router program paths must stay in their draft folder.')
        digest=sha256(path.read_bytes()).hexdigest()
        if info.get('sha256') is not None and info['sha256']!=digest:
            raise ValueError('Draft program changed after generation; regenerate it before reviewing.')
        start=info.get('startup',{}).get('first_work_xy_mm',info.get('pin_avoidance',{}).get('start_work_xy_mm',info.get('start_work_xy_mm',[0,0])))
        segments,plunges=parse_draft(path.read_text(encoding='ascii'),start)
        from .router_animation import parse_motions
        motions=parse_motions(path.read_text(encoding='ascii'),start)
        if info['file'].startswith('spoilboard'):
            title='Spoilboard pin holes'
        elif info['file'].startswith('pcb-profile'):
            title='Separation cuts, then board profile' if info.get('separation',{}).get('paths') else 'Board profile'
        else:
            title=f"PCB drill · {info['tool_diameter_mm']:g} mm"
        programs.append({**info,'title':title,'start':start,'segments':segments,'plunges':plunges,'motions':motions,
                         'sha256':digest})
    data={'programs':programs,'configuration':config,'pins':pins,'outline':bounds_paths,
          'job':job.parent.name+'/'+job.name,'draft':folder.name,'clearance_diagnostic':report.get('clearance_diagnostic')}
    data['ignored_cutouts']=report.get('ignored_cutouts',[])
    from .importer import load_copper
    data['copper_path']=copper_svg_path(load_copper(copper).geometry,(ox,oy))
    page='''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>PCB Isolator · Router review</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#131a22;color:#e6edf3;font:14px system-ui;height:100vh;height:100dvh;display:flex;flex-direction:column;overflow:hidden}
header{padding:10px 16px;background:#202b37;flex:none}.heading{display:flex;align-items:center;gap:14px;flex-wrap:wrap}h1{font-size:19px;margin:0}h2{font-size:16px;margin:0 0 8px}
p{line-height:1.4;margin:6px 0}.muted{color:#afbdca;font-size:12px}.badge{display:inline-block;background:#694d1e;color:#ffe3a5;padding:3px 8px;border-radius:4px;font-size:12px}header p{margin:4px 0 0}
main{padding:10px 12px;display:grid;grid-template-columns:clamp(230px,20vw,290px) minmax(0,1fr);gap:12px;flex:1;min-height:0}aside{overflow:auto;min-height:0;padding-right:4px}
section,.panel{background:#1c2631;border:1px solid #354351;border-radius:7px;padding:11px;margin:0 0 10px}summary{font-weight:600;cursor:pointer}details[open]>summary{margin-bottom:8px}
select,button,input[type=number]{font:inherit;padding:5px 8px;background:#293a49;color:white;border:1px solid #607387;border-radius:4px}select{width:100%}button{cursor:pointer;white-space:nowrap}button:hover{background:#3c5970}
dl{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin:8px 0 0;font-size:13px}dt{color:#aebfce}dd{margin:0;text-align:right}
.workspace{min-width:0;min-height:0;display:flex;flex-direction:column}.viewport-panel{display:flex;flex-direction:column;flex:1;min-height:0;margin:0;padding:10px}
svg{display:block;background:#111920;width:100%;height:0;flex:1;min-height:180px;touch-action:none;cursor:grab}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0}.viewport-toolbar{display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}.viewport-toolbar h2{margin:0}label{white-space:nowrap}
.animation-box{padding:8px 10px;background:#253b49;border-radius:6px;margin-bottom:8px;flex:none}.animation-box input[type=range]{width:100%;height:14px;margin:7px 0 3px}.readouts{display:flex;justify-content:space-between;align-items:center;gap:4px 16px;flex-wrap:wrap;font-size:12px}.readouts p{margin:0}.readouts .mono{flex:1;min-width:180px}.animation-box select{width:auto}.z-meter{height:3px;background:#101b25;border-radius:3px;margin-top:5px}#z-fill{height:100%;background:#ffb75a;width:0}.legend{margin:6px 0 0;font-size:12px;color:#afbdca;flex:none}
.note{border-left:3px solid #e6ac5a;padding-left:9px}.mono{font-family:monospace;overflow-wrap:anywhere}#anim-setup:empty{display:none}.option-stack{display:grid;gap:9px}
@media(max-width:900px){body{height:auto;overflow:auto}main{display:flex;flex-direction:column}.workspace{order:-1}.viewport-panel{height:calc(100dvh - 105px);min-height:460px;flex:none}aside{overflow:visible}.readouts{font-size:12px}}
@media(min-width:901px) and (max-height:560px){body{height:auto;overflow:auto}main{min-height:490px}}
</style><header><div class="heading"><h1>PCB Isolator · Router job review</h1><span class="badge">DRAFT · Machine setup remains to be checked</span></div>
<p class="muted">__JOB__</p></header><main><aside>
<section><h2>Operation</h2><select id="operation"></select><dl id="operation-details"></dl></section>
<section id="clearance-warning" hidden style="border-color:#ff6666"></section>
<details class="panel" id="anim-setup-panel"><summary>Tool/setup instructions</summary><p id="anim-setup" class="note"></p><p>Stage each program manually at its required work XY. Set spindle speed manually and reset Z for each tool.</p></details>
<details class="panel"><summary>Board and tooling</summary><dl id="board-details"></dl></details>
<details class="panel"><summary>Starting position</summary><p id="start"></p><p class="note">After tool-height setting, leave Z at machine maximum. New XY-first programs move directly to their first hole or cutting start, then lower Z there. Subsequent XY travel follows the pin-avoidance plan.</p>
<p>Initial positioning relies on the tool-setting cycle leaving Z at maximum height. The program cannot verify that height or an unknown starting XY.</p></details>
<details class="panel"><summary>Animation options</summary><div class="option-stack">
<label>Rapid estimate <input id="rapid-estimate" type="number" min="1" max="100000" value="3000" style="width:85px"> mm/min</label></div>
<p class="muted">Rapid timing is estimated; acceleration and manual tool changes are excluded. For XY-first programs, the initial XY positioning and Z descent from unknown machine height are not animated or timed. Animation starts at the first commanded Z height. Green shows completed tool sweeps; amber holes are partially drilled. This is not a 3D stock simulation.</p></details>
<details class="panel"><summary>Program details</summary><p id="filename" class="mono"></p><p id="depths"></p><p id="pecks"></p><p id="pin-status"></p>
<p>Generated files retain the .mmg.draft suffix. This screen does not release machine-ready files.</p></details>
<details class="panel"><summary>Setup assumptions</summary><p>Actual profile cutter diameter and board thickness still need measuring. Feeds are trial settings.</p>
<p>Controller: millimeters and absolute positioning. Spindle speed is set manually; start/stop is automatic.</p>
<p>Locate with pins, press the double-sided tape firmly, then REMOVE ALL PINS before PCB machining. Pin avoidance is disabled for this workflow.</p>
<p>There are no holding tabs. Workholding and holder clearance need a physical check before a machine test.</p></details>
</aside><div class="workspace"><section class="viewport-panel"><div class="viewport-toolbar"><h2 id="view-title"></h2><div class="controls"><button id="fit">Fit view</button>
<label><input id="copper" type="checkbox" checked> Copper</label>
<label><input id="travel" type="checkbox" checked> Travel</label><label><input id="cut" type="checkbox" checked> Cuts / holes</label>
<label><input id="zones" type="checkbox" checked> Registration</label></div></div>
<div class="animation-box">
<div class="controls"><button id="anim-all">Play all tools</button><button id="anim-selected">Play current tool</button><button id="anim-prev">Previous tool</button><button id="anim-next">Next tool</button><button id="anim-play">Pause / Resume</button><button id="anim-restart">Restart</button><button id="anim-static">Static view</button>
<label>Speed <select id="anim-speed"><option value="1">1×</option><option value="5">5×</option><option value="20" selected>20×</option><option value="100">100×</option></select></label></div>
<input id="anim-position" type="range" min="0" max="10000" value="0" aria-label="Animation timeline" style="width:100%">
<div class="readouts"><p id="anim-tool" class="mono">Choose Play all tools or Play current tool.</p><p><b id="anim-z">Z height</b> · <span id="anim-xy"></span></p><p><span id="anim-status">Static operation view</span> · <span id="anim-time"></span></p></div>
<div class="z-meter"><div id="z-fill"></div></div></div>
<svg id="view" xmlns="http://www.w3.org/2000/svg"></svg>
<p class="legend">Gold: copper · Blue dashed: rapid travel · Green: cuts/holes · Red: registration locations (pins removed before PCB machining) · Yellow arrows: XY zero · Scroll to zoom · Drag to pan · Work XY, mm</p></section>
</div></main><script>
const job=__DATA__,svg=document.getElementById('view'),ns='http://www.w3.org/2000/svg';
let selected=0,view=[],initial=[],drag=null;
const el=(tag,attrs,parent=svg)=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);parent.append(n);return n};
const line=(a,b,color,width,parent)=>el('line',{x1:a[0],y1:-a[1],x2:b[0],y2:-b[1],stroke:color,'stroke-width':width},parent);
const details=(id,rows)=>{const n=document.getElementById(id);n.replaceChildren();for(const [a,b] of rows){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=a;dd.textContent=b;n.append(dt,dd)}};
const update=()=>{svg.setAttribute('viewBox',view.join(' '));const marker=document.getElementById('origin-layer');if(marker){const k=Math.max(view[2]/(svg.clientWidth||800),view[3]/(svg.clientHeight||500));marker.setAttribute('transform','scale('+k+')')}};
const point=e=>new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
const cfg=job.configuration;
details('board-details', [['Thickness',cfg.board.thickness_mm+' mm'],['Breakthrough',cfg.board.breakthrough_mm+' mm'],['Profile bit',cfg.profile.tool_diameter_mm+' mm (placeholder)'],['Profile stepdown',cfg.profile.stepdown_mm+' mm'],['Pins',job.pins.length+' × '+(job.pins.length?(job.pins[0].radius*2).toFixed(3):'—')+' mm'],['Pins during machining',cfg.alignment_pins.pins_removed_before_machining?'REMOVED':'Installed']]);
const select=document.getElementById('operation');job.programs.forEach((p,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+'. '+p.title;select.append(o)});
function render(){const p=job.programs[selected],spoil=p.z_zero==='spoilboard_top',pin=p.pin_avoidance;svg.replaceChildren();
document.getElementById('view-title').textContent=p.title;
document.getElementById('filename').textContent=p.file;
document.getElementById('start').textContent=spoil?'Spoilboard operation: pins are not installed yet.':('First work XY: X'+p.start[0].toFixed(3)+' Y'+p.start[1].toFixed(3));
const depths=[...new Set(p.plunges.map(x=>x.z))];
document.getElementById('depths').textContent='Z zero: '+(spoil?'top of spoilboard':'top of PCB')+' · Cutting Z: '+depths.map(x=>x.toFixed(3)).join(', ')+' mm';
const drill=p.drilling;document.getElementById('pecks').textContent=drill?('Peck increment: '+drill.peck_mm+' mm · Between-peck retract: +'+drill.peck_retract_mm+' mm'):(spoil?'Pin-hole depth and drill fit are provisional.':'Profile uses straight plunges and linearized contour moves.');
document.getElementById('pin-status').textContent=pin?.policy==='pins_removed_before_machining'?'REMOVE ALL PINS after tape registration, before PCB machining. Travel uses normal clearance.':pin?('Always route around pins · Travel Z: +'+pin.travel_clearance_mm+' mm · '+pin.detoured_travels+' detoured travels · Tool-center keepout radius: '+pin.keepout_radius_mm.toFixed(3)+' mm'):'Pin avoidance is not applied while making spoilboard pin holes, before inserting the pins.';
const feed=drill?drill.feed_mm_min:spoil?cfg.drilling.feed_mm_min:cfg.profile.feed_mm_min;
const rows=[['Tool diameter',(p.tool_diameter_mm??p.nominal_pin_diameter_mm)+' mm'+(spoil?' nominal pin':'')],['Hole count',p.holes??'Profile'],['Feed',feed+' mm/min'],['Plunge',spoil||drill?feed+' mm/min':cfg.profile.plunge_mm_min+' mm/min'],['Travel Z','+'+(pin?.travel_clearance_mm??cfg.machine.clearance_mm)+' mm'],['Spindle','Auto start/stop']];
if(p.source_hole_sizes){rows.push(['KiCad hole sizes',p.source_hole_sizes.map(s=>s.count+' × '+s.diameter_mm+' mm').join(' / ')]);if(p.source_hole_sizes.some(s=>Math.abs(s.diameter_mm-p.tool_diameter_mm)>1e-6))rows.push(['Size override','Uses chosen drill diameter'])}
if(p.travel_optimization){const o=p.travel_optimization;rows.push(['XY travel',o.optimized_xy_travel_mm.toFixed(1)+' mm'],['Travel saved',o.saved_xy_travel_mm.toFixed(1)+' mm ('+o.saved_percent.toFixed(0)+'%)'])}details('operation-details',rows);
const copper=el('g',{id:'copper-layer'});if(job.copper_path)el('path',{d:job.copper_path,'fill-rule':'evenodd',fill:'#dfb365','fill-opacity':.16,stroke:'#d4af6b','stroke-opacity':.5,'stroke-width':.6,'vector-effect':'non-scaling-stroke'},copper);
let all=[];const outline=el('g',{});job.outline.forEach(points=>{all.push(...points);el('polyline',{points:points.map(a=>a[0]+','+(-a[1])).join(' '),fill:'none',stroke:'#e6edf3','stroke-width':.08},outline)});
const zones=el('g',{id:'zone-layer'});if(!spoil&&!cfg.alignment_pins.pins_removed_before_machining)job.pins.forEach(p0=>{el('circle',{cx:p0.x,cy:-p0.y,r:p0.radius+cfg.alignment_pins.xy_margin_mm,fill:'#e5bb3322',stroke:'#e5bb33','stroke-width':.08},zones);el('circle',{cx:p0.x,cy:-p0.y,r:p0.radius,fill:'#e5525266',stroke:'#ff6666','stroke-width':.08},zones)});
const diagnostic=job.clearance_diagnostic,warning=document.getElementById('clearance-warning');
if(diagnostic){warning.hidden=false;warning.textContent='XY margin reduced from '+diagnostic.requested_margin_mm.toFixed(3)+' to '+diagnostic.applied_margin_mm.toFixed(3)+' mm (maximum that fits). '+(diagnostic.applied_margin_mm<.5?'WARNING: less than 0.5 mm. ':'')+'Red arrow marks the limiting location in '+diagnostic.operation+'.';
const ox=cfg.machine.origin_x_mm,oy=cfg.machine.origin_y_mm,x=diagnostic.closest_xy[0]-ox,y=diagnostic.closest_xy[1]-oy;
const mark=el('g',{'pointer-events':'none'});line([x+7,y+7],[x,y],'#ff5555',.3,mark);line([x,y],[x+1.7,y+.4],'#ff5555',.3,mark);line([x,y],[x+.4,y+1.7],'#ff5555',.3,mark);el('circle',{id:'clearance-tool-marker',cx:x,cy:-y,r:diagnostic.tool_diameter_mm/2,fill:'none',stroke:'#ff5555','stroke-width':.2},mark);}
const travels=el('g',{id:'travel-layer'}),cuts=el('g',{id:'cut-layer'});
p.segments.forEach(s=>{all.push(s.from,s.to);const n=line(s.from,s.to,s.rapid?'#78aaff':'#5fe69a',s.rapid?1.6:1.4,s.rapid?travels:cuts);n.setAttribute('vector-effect','non-scaling-stroke');if(s.rapid)n.setAttribute('stroke-dasharray','5 4')});
if(p.holes){const unique=new Map(p.plunges.map(h=>[h.x+','+h.y,h]));for(const h of unique.values()){all.push([h.x,h.y]);el('circle',{cx:h.x,cy:-h.y,r:(p.tool_diameter_mm??p.nominal_pin_diameter_mm)/2,fill:'#5fe69a55',stroke:'#5fe69a','stroke-width':.07},cuts)}}
if(!spoil){line([p.start[0]-.8,p.start[1]],[p.start[0]+.8,p.start[1]],'#709fff',.15);line([p.start[0],p.start[1]-.8],[p.start[0],p.start[1]+.8],'#709fff',.15);all.push(p.start)}
const origin=el('g',{id:'origin-layer','pointer-events':'none'});
const originShape='M-12 0H34 M0 12V-34 M27 -5L34 0L27 5 M-5 -27L0 -34L5 -27';
el('path',{d:originShape,fill:'none',stroke:'#101820','stroke-width':6},origin);
el('path',{d:originShape,fill:'none',stroke:'#ffe45c','stroke-width':2},origin);
el('circle',{cx:0,cy:0,r:3,fill:'#ffe45c'},origin);
el('text',{x:12,y:21,fill:'#ffe45c','font-size':13,stroke:'#101820','stroke-width':3,'paint-order':'stroke'},origin).textContent=job.pins.length?'XY 0':'XY 0 (copper lower-left, provisional)';
el('text',{x:38,y:4,fill:'#ffe45c','font-size':12},origin).textContent='+X';
el('text',{x:4,y:-38,fill:'#ffe45c','font-size':12},origin).textContent='+Y';
for(const issue of (job.ignored_cutouts||[])){const x=issue.source_center[0]-cfg.machine.origin_x_mm,y=issue.source_center[1]-cfg.machine.origin_y_mm;el('circle',{cx:x,cy:-y,r:.8,fill:'none',stroke:'#ff615a','stroke-width':.1});line([x-.5,y-.5],[x+.5,y+.5],'#ff615a',.1);line([x-.5,y+.5],[x+.5,y-.5],'#ff615a',.1);}
all.push([0,0]);
const xs=all.map(a=>a[0]),ys=all.map(a=>a[1]),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys),pad=Math.max(x1-x0,y1-y0)*.06+1;
initial=[x0-pad,-y1-pad,x1-x0+2*pad,y1-y0+2*pad];view=[...initial];update();toggles();}
function toggles(){for(const [id,layer] of [['copper','copper-layer'],['travel','travel-layer'],['cut','cut-layer'],['zones','zone-layer']]){const n=document.getElementById(layer);if(n)n.style.display=document.getElementById(id).checked?'':'none'}}
for(const id of ['copper','travel','cut','zones'])document.getElementById(id).onchange=()=>{toggles();if(anim.active)drawAnimation()};
select.onchange=()=>{selected=Number(select.value);render()};document.getElementById('fit').onclick=()=>{view=[...initial];update()};
svg.addEventListener('wheel',e=>{e.preventDefault();const p=point(e),f=e.deltaY>0?1.15:1/1.15;if(view[2]*f<.01||view[2]*f>initial[2]*100)return;view=[p.x+(view[0]-p.x)*f,p.y+(view[1]-p.y)*f,view[2]*f,view[3]*f];update()},{passive:false});
svg.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,v:[...view],m:svg.getScreenCTM().inverse()};svg.setPointerCapture(e.pointerId)};
svg.onpointermove=e=>{if(!drag)return;const a=new DOMPoint(drag.x,drag.y).matrixTransform(drag.m),b=new DOMPoint(e.clientX,e.clientY).matrixTransform(drag.m);view=[drag.v[0]+a.x-b.x,drag.v[1]+a.y-b.y,drag.v[2],drag.v[3]];update()};svg.onpointerup=svg.onpointercancel=()=>drag=null;
render();
__ANIMATION__
</script></html>'''
    from .router_animation import animation_assets
    page=page.replace('__ANIMATION__',animation_assets())
    page=page.replace('__JOB__',escape(data['job'])).replace('__DATA__',json.dumps(data).replace('<','\\u003c'))
    if data['ignored_cutouts']:
        page=page.replace('</header>',f'<p style="color:#ffaaa0">{len(data["ignored_cutouts"])} internal cutouts deliberately omitted. Red crosses mark material that will remain uncut.</p></header>',1)
    destination=folder/'router-review.html'
    if registration_warnings:page=page.replace('</header>','<p style="color:#ffb080">'+escape(' '.join(registration_warnings))+'</p></header>',1)
    from .paper_print import paper_data,path_data,attach_paper_print
    from .drills import load_drills
    from dataclasses import replace
    sizes={id:p['tool_diameter_mm'] for p in report['programs'] for id in p.get('hole_order',[])}
    paper_features=[replace(f,diameter_mm=sizes.get(f.id,f.diameter_mm)) for source in load_job(job)[1] for f in load_drills(source)]
    selected_sources={f['id']:f for f in selection['features']+selection.get('outline_candidates',[])}
    alignment_sources=[selected_sources[id] for id in selection['alignment_ids']]
    chosen=[f for f in paper_features if not any(abs(f.x-pin['x'])<.0001 and abs(f.y-pin['y'])<.0001 for pin in alignment_sources)]
    from .drills import DrillFeature
    chosen.extend(DrillFeature(pin['id'],selection['pin_diameter_mm'],pin['x'],pin['y']) for pin in alignment_sources)
    tools=[dict(title=p['title'],d=' '.join(path_data([(seg['from'][0]+ox,seg['from'][1]+oy),(seg['to'][0]+ox,seg['to'][1]+oy)]) for seg in p['segments'] if not seg['rapid'])) for p in programs]
    paper=paper_data(data['job'],'Router',load_copper(copper).geometry,load_outline(outline),chosen,tools)
    paper['padding_mm']=max(2,config['profile']['tool_diameter_mm']/2+.5)
    page=attach_paper_print(page,paper,'<button id="fit">')
    destination.write_text(page,encoding='utf-8')
    (folder/'review-data.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    return destination


def write_job_index(root,destination):
    root=Path(root).resolve()
    rows=[]
    for board in sorted(root.iterdir()):
        if not board.is_dir():
            continue
        try:
            job=resolve_job_folder(board)
        except ValueError:
            continue
        candidates=list((job/'outputs').glob('router-draft-*/router-report.json'))
        if candidates:
            folder=max(candidates,key=lambda p:p.parent.name).parent
            page=write_router_review(folder)
            rows.append('<article><h2>'+escape(board.name)+'</h2><p>Export: '+escape(job.name)+
                        '</p><a href="'+escape(page.as_uri(),quote=True)+'">Open router review</a></article>')
        else:
            rows.append('<article><h2>'+escape(board.name)+'</h2><p>No router draft for latest export '+escape(job.name)+'.</p></article>')
    if not rows:
        raise ValueError(f'No manufacturing jobs found under {root}.')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><title>PCB Isolator · Jobs</title>
<style>body{background:#131a22;color:#e6edf3;font:16px system-ui;max-width:900px;margin:35px auto;padding:20px}article{background:#202b37;border:1px solid #435365;border-radius:8px;padding:20px;margin:20px 0}h1{font-size:26px}h2{font-size:21px}p{color:#b9c8d6}a{display:inline-block;background:#315a75;color:white;padding:10px 18px;border-radius:4px;text-decoration:none}</style>
<h1>PCB Isolator · Router jobs</h1><p>Choose the board to review. Reviews use its latest export. Router files remain drafts.</p>'''+''.join(rows)+'</html>'
    destination=Path(destination).resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(html,encoding='utf-8')
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path,nargs='?')
    parser.add_argument('--jobs-root',type=Path,default=Path('jobs'))
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    try:
        if args.folder is None:
            destination=write_job_index(args.jobs_root,Path('generated/router-jobs.html'))
            print(f'Job list: {destination}')
            if not args.no_open:
                webbrowser.open(destination.as_uri())
            return
        folder=args.folder.resolve()
        print(f'Requested folder: {folder}',flush=True)
        if not (folder/'router-report.json').is_file():
            job=resolve_job_folder(folder)
            candidates=list((job/'outputs').glob('router-draft-*/router-report.json'))
            if not candidates:
                raise ValueError(f'No completed router draft found for job {job}.')
            folder=max(candidates,key=lambda p:p.parent.name).parent
        destination=write_router_review(folder)
    except Exception as error:
        parser.exit(1,f'Could not open router review: {error}\n')
    print(f'Review: {destination}')
    if not args.no_open:
        webbrowser.open(destination.as_uri())


if __name__=='__main__':
    main()
