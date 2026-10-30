"""Portable, read-only operation guide for a generated manufacturing package."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import tomllib


def build_data(package):
    import ezdxf
    from ezdxf.path import make_path
    from .router_review import parse_draft
    from .kicad_export import load_job
    package=Path(package).resolve()
    manifest=json.loads((package/'test-package.json').read_text(encoding='utf-8'))
    router=package/'router'
    checks=json.loads((router/'file-checksums.json').read_text(encoding='utf-8'))
    fingerprints={}
    programs={}
    for entry in checks:
        name=entry['file']
        path=(router/name).resolve()
        if path.parent!=router or sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Router file differs from its generated checksum: '+name)
        segments,plunges=parse_draft(path.read_text(encoding='ascii'),[-10,0])
        fingerprints[name]=entry['sha256']
        programs[name]={'segments':segments,'plunges':plunges}
    selection=json.loads((package/'reference/alignment-selection.json').read_text(encoding='utf-8'))
    with (package/'reference/machining.toml').open('rb') as stream:
        machine=tomllib.load(stream)['machine']
    ox,oy=machine['origin_x_mm'],machine['origin_y_mm']
    features={f['id']:f for f in selection['features']+selection.get('outline_candidates',[])}
    pins=[{'x':features[i]['x']-ox,'y':features[i]['y']-oy,'radius':selection['pin_diameter_mm']/2}
          for i in selection['alignment_ids']]
    _,_,outline_source=load_job(Path(manifest['source_job']))
    outline_doc=ezdxf.readfile(outline_source)
    outlines=[]
    for entity in outline_doc.modelspace():
        outlines.append([[p.x-ox,p.y-oy] for p in make_path(entity).flattening(distance=0.02)])
    laser_path=package/'laser/laser-isolation-and-marks.dxf'
    laser=ezdxf.readfile(laser_path)
    fingerprints[laser_path.name]=sha256(laser_path.read_bytes()).hexdigest()
    laser_commands=[];mark_commands=[]
    for entity in laser.modelspace():
        points=list(make_path(entity).flattening(distance=0.01))
        if not points:
            continue
        path='M'+' L'.join(f'{p.x-ox:.4f},{-(p.y-oy):.4f}' for p in points)
        (mark_commands if entity.dxf.layer=='ALIGNMENT_CENTER_MARKS' else laser_commands).append(path)
    steps=[
      {'id':'laser','title':'Laser isolation and alignment marks','phase':'Laser',
       'tool':'Laser · painted copper board','filename':'laser-isolation-and-marks.dxf','view':'laser',
       'facts':[['Scale','1:1'],['Alignment centers','120 mm apart'],['Isolation','5 lines · 0.075 mm width'],['Overlap','33.3333%']],
       'actions':['Open the laser DXF in your printing application. Confirm physical scale and the intended board orientation.',
                  'Use your tuned paint-removal settings to expose isolation paths and both center crosses.',
                  'Keep the two alignment marks identifiable for manual drilling.'],
       'note':'Paper printing and scale passed your test. Laser engraving settings still need their own physical test.'},
      {'id':'etch','title':'Etch and clean the board','phase':'Board preparation','tool':'Your established etching process','view':'outline',
       'facts':[['Next reference','Lasered alignment centers']],
       'actions':['Etch the exposed copper using your established process, then clean and inspect the board.',
                  'Check for copper bridges and damaged traces before moving to drilling.'],
       'note':'This guide records the manufacturing sequence; it does not replace your chemical handling procedure.'},
      {'id':'spoil','title':'Drill the spoilboard pin holes','phase':'Router · before inserting pins','tool':'Install ⅛-inch drill · 3.175 mm',
       'filename':'01-1_8.mmg','program':'01-1_8.mmg','view':'router',
       'facts':[['Holes','2 · 120 mm apart'],['XY zero','Left pin-hole center'],['Z zero','SPOILBOARD TOP'],['Start work XY','X−10 · Y0'],['Final Z','−5.000 mm'],['Drill feed','127 mm/min'],['Rapid approach','+0.5 mm'],['Travel Z','+5.08 mm']],
       'actions':['Stop the program and spindle before installing the ⅛-inch drill.',
                  'Set XY zero at the intended left pin-hole center. Set this tool’s Z zero on the spoilboard surface.',
                  'Stage at work X−10, Y0 with the tool clear of the surface. Set spindle speed manually.',
                  'Run 01-1_8.mmg. The second hole is at work X120, Y0.'],
       'note':'Pins are not installed during this operation. Verify their fit before registering the PCB.'},
      {'id':'mount','title':'Register and secure the PCB','phase':'Board setup','tool':'⅛-inch pins + double-sided tape','view':'pins',
       'facts':[['Pin diameter','3.175 mm'],['PCB mounting holes','3.2 mm design diameter'],['XY zero','Left pin center'],['Pin projection','Up to 10 mm above PCB']],
       'actions':['Manually drill the PCB alignment holes at the laser marks to fit your pins.',
                  'Position the board on the spoilboard pins and use double-sided tape to secure it.',
                  'Confirm orientation, seating and hold-down. The left pin remains work X0, Y0.',
                  'Check that the collet/nut clears the pins throughout cutting.'],
       'note':'XY datum and start position are different: PCB programs start at X−10, Y0, away from the left pin.'},
      {'id':'drill0500','title':'Drill the transducer holes','phase':'Router · PCB drilling','tool':'Install 0.5 mm PCB drill',
       'filename':'02-0500.mmg','program':'02-0500.mmg','view':'router',
       'facts':[['Holes','32 · eight groups of four'],['Z zero','PCB TOP'],['Start work XY','X−10 · Y0'],['Peck Z','−0.7 / −1.4 / −1.9 mm'],['Drill feed','127 mm/min'],['Between pecks','Retract to +1 mm'],['Travel Z','+12 mm · around pins']],
       'actions':['Stop the program and spindle, then install the 0.5 mm drill.',
                  'Reset Z zero on TOP OF THE PCB for this tool. Retain the left-pin XY datum.',
                  'Stage at work X−10, Y0 with the tool raised clear. Set spindle speed manually.',
                  'Run 02-0500.mmg. Inspect the transducer holes before changing tools.'],
       'note':'Rapid approach stops at +0.5 mm. Peck reentry stops its rapid 0.2 mm above the previous drilled depth.'},
      {'id':'drill1000','title':'Drill the connector holes','phase':'Router · PCB drilling','tool':'Install 1.0 mm PCB drill',
       'filename':'03-1000.mmg','program':'03-1000.mmg','view':'router',
       'facts':[['Holes','18 · central row + two-pin connector'],['Z zero','PCB TOP'],['Start work XY','X−10 · Y0'],['Peck Z','−0.7 / −1.4 / −1.9 mm'],['Drill feed','127 mm/min'],['Travel Z','+12 mm · around pins']],
       'actions':['Stop the program and spindle, then install the 1.0 mm drill.',
                  'Reset Z zero on TOP OF THE PCB. Retain the left-pin XY datum.',
                  'Stage at work X−10, Y0 with the tool clear. Set spindle speed manually.',
                  'Run 03-1000.mmg. Inspect the connector holes before profiling.'],
       'note':'The two alignment holes are excluded from both PCB drill programs.'},
      {'id':'profile','title':'Cut the board profile','phase':'Router · final cutting operation','tool':'Install profile cutter · configured 2.54 mm',
       'filename':'04-2p54mm.mmg','program':'04-2p54mm.mmg','view':'router',
       'facts':[['Tool diameter','2.540 mm configured'],['Z zero','PCB TOP'],['Start work XY','X−10 · Y0'],['Pass depths','−0.95 / −1.90 mm'],['XY feed','508 mm/min'],['Plunge feed','127 mm/min'],['Travel Z','+12 mm · around pins']],
       'actions':['Stop the program and spindle. Install the profile cutter and verify that its diameter matches 2.54 mm.',
                  'Reset Z zero on TOP OF THE PCB. Check that the tape will hold the board through the final cut; this program has no tabs.',
                  'Stage at work X−10, Y0 with the tool clear. Set spindle speed manually.',
                  'Run 04-2p54mm.mmg. Allow the spindle to stop before removing the board.'],
       'note':'Depths assume a 1.6 mm PCB plus 0.3 mm breakthrough. Verify actual tool diameter and stack before repeating this setup.'},
      {'id':'inspect','title':'Inspect the completed board','phase':'Finish','tool':'Board inspection and component fit','view':'pins',
       'facts':[['Status','Record actual results']],
       'actions':['Inspect the profile, hole sizes, trace clearances and component fit.',
                  'Record any setting changes with this manufacturing run before generating another version.'],
       'note':'Guide progress is your manual record only. It does not read the CNC or verify that an operation has finished.'},
    ]
    key=sha256(json.dumps(fingerprints,sort_keys=True).encode()).hexdigest()[:16]
    return {'version':1,'job_key':key,'board_name':Path(manifest['source_job']).parent.name,
            'export_id':Path(manifest['source_job']).name,'files':fingerprints,'steps':steps,
            'programs':programs,'pins':pins,'outline':outlines,
            'laser_path':' '.join(laser_commands),'mark_path':' '.join(mark_commands),
            'setup_note':'All four router programs were tested by the user with successful component fit. Laser settings remain to be tested.'}


def svg_content(data,step,travel=True):
    parts=['<g fill="none" stroke="#91a6b5" stroke-width="0.08">']
    for points in data['outline']:
        parts.append('<polyline points="'+' '.join(f'{x},{-y}' for x,y in points)+'"/>')
    parts.append('</g>')
    if step['view']=='laser':
        parts.append(f'<path d="{data["laser_path"]}" fill="none" stroke="#20c6be" stroke-width="0.025"/>')
        parts.append(f'<path d="{data["mark_path"]}" fill="none" stroke="#62e59e" stroke-width="0.12"/>')
    if step.get('program'):
        program=data['programs'][step['program']]
        commands={True:[],False:[]}
        for segment in program['segments']:
            a,b=segment['from'],segment['to']
            commands[segment['rapid']].append(f'M{a[0]},{-a[1]} L{b[0]},{-b[1]}')
        for rapid,color in [(True,'#54d3ee'),(False,'#60df98')]:
            if not rapid or travel:
                parts.append(f'<path d="'+ ' '.join(commands[rapid])+f'" fill="none" stroke="{color}" stroke-width="0.1"/>')
        if step['id']!='profile':
            for x,y in sorted({(p['x'],p['y']) for p in program['plunges']}):
                radius=step.get('hole_radius_mm',1.5875 if step['id']=='spoil' else 0.25 if step['id']=='drill0500' else 0.5)
                parts.append(f'<circle cx="{x}" cy="{-y}" r="{radius}" fill="#60df9866" stroke="#60df98" stroke-width="0.09"/>')
    if step['view']=='pins' or step.get('program') and step['id']!='spoil':
        for pin in data['pins']:
            radius=step.get('keepout_radius_mm') if step.get('keepout_radius_mm') is not None else pin.get('keepout_radius_mm',5.177)
            parts.append(f'<circle cx="{pin["x"]}" cy="{-pin["y"]}" r="{radius}" fill="#eac34a16" stroke="#eac34a" stroke-width="0.1"/>')
            parts.append(f'<circle cx="{pin["x"]}" cy="{-pin["y"]}" r="{pin["radius"]}" fill="#ed696977" stroke="#ed6969" stroke-width="0.1"/>')
    return ''.join(parts)


def write_html(data,destination):
    drawings=[svg_content(data,step) for step in data['steps']]
    payload={**data,'drawings':drawings}
    points=[(x,-y) for ring in data['outline'] for x,y in ring]
    points.extend((p['x'],-p['y']) for p in data['pins'])
    for program in data['programs'].values():
        for segment in program['segments']:
            points.extend((p[0],-p[1]) for p in (segment['from'],segment['to']))
    if points:
        xs,ys=zip(*points);margin=max(3,(max(xs)-min(xs))*.04)
        payload['view_box']=[min(xs)-margin,min(ys)-margin,max(xs)-min(xs)+2*margin,max(ys)-min(ys)+2*margin]
    # Keep one embedded laser drawing, not duplicated copies of its geometry.
    payload.pop('laser_path');payload.pop('mark_path')
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PCB operation guide</title><style>
*{box-sizing:border-box}body{margin:0;background:#111a22;color:#e9f0f5;font:17px system-ui;line-height:1.45}header{padding:16px 20px;background:#1d2b38;border-bottom:1px solid #405365}header p{margin:4px 0;font-size:13px;color:#b4c5d3}h1{font-size:20px;margin:0}main{max-width:1100px;margin:auto;padding:18px 18px 115px}select,button{font:inherit;min-height:48px;border-radius:7px;border:1px solid #698093;background:#253b4d;color:#fff;padding:9px 14px}select{width:100%;margin-bottom:16px}button{cursor:pointer}button:disabled{opacity:.4;cursor:default}.phase{color:#55d6c6;font-size:14px;text-transform:uppercase;letter-spacing:.06em}h2{font-size:28px;line-height:1.2;margin:8px 0 12px}.tool{font-size:23px;font-weight:700;padding:15px;background:#294b45;border-left:5px solid #5cdfb4;border-radius:6px}.filename{font:bold 22px ui-monospace,monospace;padding:14px;background:#25394b;overflow-wrap:anywhere;margin:12px 0}.layout{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:16px}.panel{border:1px solid #3a5062;border-radius:8px;padding:15px;background:#182632}dl{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0}dt{color:#b4c5d3}dd{margin:0;text-align:right;font-weight:600}ol{padding-left:26px}li{margin:14px 0}.note{border-left:3px solid #eac34a;padding:10px 14px;background:#302b1e;border-radius:4px}.caption{font-size:13px;color:#b9cbd9}.controls{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}svg{width:100%;height:290px;touch-action:none;background:#101b25;border-radius:6px}.nav{position:fixed;bottom:0;left:0;right:0;background:#1d2b38ee;backdrop-filter:blur(8px);border-top:1px solid #4a6377;padding:12px;display:flex;justify-content:center;gap:12px}.next{background:#236657;min-width:180px}.progress{height:5px;background:#3c5262;margin-top:10px}.progress span{display:block;height:100%;background:#58d9b1;width:0}#storage{font-size:13px;color:#efcf86}#restart{font-size:14px;margin-top:12px}.complete{color:#7ce4b0;font-size:14px}@media(max-width:750px){.layout{grid-template-columns:1fr}h2{font-size:25px}svg{height:230px}main{padding:14px 14px 110px}.nav button{flex:1;max-width:250px}.tool{font-size:21px}}@media print{.nav,.controls,select,#restart{display:none}body{background:white;color:black}.panel,.tool,.filename,.note{background:white;color:black}.layout{grid-template-columns:1fr}svg{height:250px}}
</style><header><h1>PCB manufacturing · Operation guide</h1><p id="job"></p><p id="revision"></p><div class="progress"><span id="bar"></span></div></header>
<main><p id="setup"></p><p id="review-links"></p><select id="steps" aria-label="Choose operation"></select><p id="storage"></p><div class="phase" id="phase"></div><h2 id="title"></h2><div class="tool" id="tool"></div><div class="filename" id="filename"></div><p class="complete" id="done"></p>
<div class="layout"><div><section class="panel"><dl id="facts"></dl></section><ol id="actions"></ol><p class="note" id="note"></p></div>
<div class="panel"><div class="controls"><button id="fit">Fit</button><button id="zoom-in" aria-label="Zoom in">＋</button><button id="zoom-out" aria-label="Zoom out">−</button></div><svg id="view" xmlns="http://www.w3.org/2000/svg"></svg><p class="caption">Touch and drag to pan. Use + / − to zoom. Cyan: travel · Green: cuts/holes · Red: registration locations · Remove pins before PCB machining.</p><p class="caption">Drawing uses the selected alignment-hole XY datum. Laser DXF keeps its original page coordinates. This guide never controls the machines.</p><button id="restart">Restart guide progress</button></div></div></main>
<nav class="nav"><button id="back">Back</button><button class="next" id="next">Mark done &amp; Next</button></nav><script>
const job=__DATA__,key='pcb-guide-'+job.job_key;let index=0,done=new Set(),persist=true;
try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved){index=Math.max(0,Math.min(job.steps.length-1,Number(saved.index)||0));done=new Set((saved.done||[]).filter(x=>Number.isInteger(x)&&x>=0&&x<job.steps.length))}}catch(e){persist=false}
const $=id=>document.getElementById(id),svg=$('view');let view=[],initial=[],drag=null;
$('job').textContent=job.board_name;$('revision').textContent='Export '+job.export_id+' · File set '+job.job_key;
$('setup').textContent=job.setup_note||'';
for(const [label,path] of Object.entries(job.review_links||{})){const a=document.createElement('a');a.href=path;a.textContent=label;a.style.cssText='color:#7ce4b0;margin-right:20px';$('review-links').append(a)}
const save=()=>{try{localStorage.setItem(key,JSON.stringify({index,done:[...done]}))}catch(e){persist=false}status()};
const status=()=>{$('storage').textContent=persist?'Progress is stored only on this device/browser. Completion is your manual record.':'Progress cannot be saved by this browser. You can still step through the guide.'};
const selector=$('steps');job.steps.forEach((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+' / '+job.steps.length+' · '+s.title;selector.append(o)});
const update=()=>svg.setAttribute('viewBox',view.join(' '));
function render(){const s=job.steps[index];selector.value=index;$('phase').textContent='Step '+(index+1)+' of '+job.steps.length+' · '+s.phase;$('title').textContent=s.title;$('tool').textContent=s.tool;$('filename').textContent=s.filename||'';$('filename').style.display=s.filename?'':'none';$('done').textContent=done.has(index)?'Marked done on this device':'';$('note').textContent=s.note;
$('facts').replaceChildren();for(const [a,b]of s.facts){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=a;dd.textContent=b;$('facts').append(dt,dd)}$('actions').replaceChildren();s.actions.forEach(t=>{const li=document.createElement('li');li.textContent=t;$('actions').append(li)});
svg.innerHTML=job.drawings[index];initial=job.view_box||[-14,-26,148,52];view=[...initial];update();$('back').disabled=index===0;$('next').textContent=index===job.steps.length-1?'Mark guide complete':'Mark done & Next';$('bar').style.width=(done.size/job.steps.length*100)+'%';status();}
selector.onchange=()=>{index=Number(selector.value);render();save()};$('back').onclick=()=>{index=Math.max(0,index-1);render();save()};$('next').onclick=()=>{done.add(index);index=Math.min(job.steps.length-1,index+1);render();save();window.scrollTo({top:0,behavior:'smooth'})};
$('restart').onclick=()=>{index=0;done.clear();render();save();window.scrollTo({top:0,behavior:'smooth'})};
$('fit').onclick=()=>{view=[...initial];update()};const zoom=f=>{const cx=view[0]+view[2]/2,cy=view[1]+view[3]/2;if(view[2]*f<.05||view[2]*f>2000)return;view=[cx-view[2]*f/2,cy-view[3]*f/2,view[2]*f,view[3]*f];update()};$('zoom-in').onclick=()=>zoom(.7);$('zoom-out').onclick=()=>zoom(1/.7);
const point=e=>new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());svg.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,v:[...view],m:svg.getScreenCTM().inverse()};svg.setPointerCapture(e.pointerId)};svg.onpointermove=e=>{if(!drag)return;const a=new DOMPoint(drag.x,drag.y).matrixTransform(drag.m),b=new DOMPoint(e.clientX,e.clientY).matrixTransform(drag.m);view=[drag.v[0]+a.x-b.x,drag.v[1]+a.y-b.y,drag.v[2],drag.v[3]];update()};svg.onpointerup=svg.onpointercancel=()=>drag=null;svg.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY>0?1.15:1/1.15)},{passive:false});render();
</script></html>'''
    page=page.replace('__DATA__',json.dumps(payload).replace('<','\\u003c'))
    Path(destination).write_text(page,encoding='utf-8')


def write_pdf(data,destination):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import simpleSplit
    from reportlab.lib.pagesizes import A4
    width,height=A4
    canvas=Canvas(str(destination),pagesize=A4)
    canvas.setTitle('PCB operation guide - '+data['board_name'])
    def text(value,x,y,font='Helvetica',size=11,color='#203345',limit=495):
        value=value.replace('⅛','1/8').replace('−','-').replace('·',' / ')
        canvas.setFont(font,size);canvas.setFillColor(HexColor(color))
        lines=simpleSplit(value,font,size,limit)
        for line in lines:
            canvas.drawString(x,y,line);y-=size*1.35
        return y
    for index,step in enumerate(data['steps']):
        canvas.setFillColor(HexColor('#203345'));canvas.rect(0,height-105,width,105,fill=1,stroke=0)
        text(f'PCB OPERATION GUIDE / {index+1} OF {len(data["steps"])}',42,height-32,'Helvetica-Bold',11,'#7ce4c1')
        text(data['board_name'],42,height-55,'Helvetica-Bold',15,'#ffffff')
        text('Export '+data['export_id']+' / File set '+data['job_key'],42,height-78,size=9,color='#d1dce5')
        y=text(step['title'],42,height-140,'Helvetica-Bold',21)
        y=text(step['tool'],42,y-9,'Helvetica-Bold',14,color='#216856')
        if step.get('filename'):
            y=text(step['filename'],42,y-8,'Courier-Bold',14)
        y-=13
        for label,value in step['facts']:
            y=text(label+': '+value,42,y,size=10.5)
        y-=14
        for n,action in enumerate(step['actions'],1):
            y=text(f'{n}. '+action,42,y,size=11);y-=8
        y-=4
        y=text(step['note'],42,y,size=10,color='#725c22')
        # A consistent bottom overview highlights the current operation.
        box_y=67;box_h=120
        canvas.setFillColor(HexColor('#f0f5f7'));canvas.roundRect(42,box_y,width-84,box_h,6,fill=1,stroke=0)
        scale=min((width-110)/148,(box_h-16)/52)
        def map_point(x,y):return width/2+(x-60)*scale,box_y+box_h/2+y*scale
        canvas.setLineWidth(.5);canvas.setStrokeColor(HexColor('#718898'))
        for points in data['outline']:
            path=canvas.beginPath();path.moveTo(*map_point(*points[0]))
            for p in points[1:]:path.lineTo(*map_point(*p))
            canvas.drawPath(path)
        if step['view']=='laser':
            for commands,color in [(data['laser_path'],'#218b85'),(data['mark_path'],'#21845c')]:
                path=canvas.beginPath()
                for command,x,y0 in re.findall(r'([ML])([-+\d.eE]+),([-+\d.eE]+)',commands):
                    point=map_point(float(x),-float(y0))
                    (path.moveTo if command=='M' else path.lineTo)(*point)
                canvas.setStrokeColor(HexColor(color));canvas.setLineWidth(.12)
                canvas.drawPath(path)
        if step.get('program'):
            program=data['programs'][step['program']]
            for segment in program['segments']:
                canvas.setStrokeColor(HexColor('#6bb6c6' if segment['rapid'] else '#21845c'))
                canvas.line(*map_point(*segment['from']),*map_point(*segment['to']))
            for x,y0 in {(p['x'],p['y']) for p in program['plunges']}:
                canvas.setFillColor(HexColor('#21845c'));canvas.circle(*map_point(x,y0),1.7,fill=1,stroke=0)
        if step['view'] in ('pins','laser'):
            for pin in data['pins']:
                canvas.setStrokeColor(HexColor('#b45050'));canvas.circle(*map_point(pin['x'],pin['y']),pin['radius']*scale,fill=0,stroke=1)
        text('Overview only. Interactive HTML provides detailed laser paths and zoom.',42,51,size=8,color='#526575')
        text(f'Manual reference / No machine connection / Step {index+1}',42,31,size=8,color='#526575')
        if y<box_y+box_h+10:
            raise ValueError('PDF text would overlap the overview on step '+step['id'])
        canvas.showPage()
    canvas.save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    args=parser.parse_args()
    data=build_data(args.package)
    (args.package/'operation-guide-data.json').write_text(json.dumps(data),encoding='utf-8')
    write_html(data,args.package/'operation-guide.html')
    print('Saved operation-guide.html and portable guide data in',args.package)


if __name__=='__main__':
    main()
