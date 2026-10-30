"""Offline Helix preparation and explicit acknowledged queue transfer. Never auto-starts."""
from pathlib import Path
from math import floor,ceil,hypot,isfinite
from html import escape
from hashlib import sha256
import json,socket,subprocess,time,re
from .runtime import asset_root,settings_root
from .adaptive_isolation import line_parts

DEFAULTS=dict(host='192.168.1.4',port=515,speed=10,power=8,frequency=2500,dpi=600,x=0.,y=0.,bed_width=609.6,bed_height=457.2,ignore_tiny_fragments=True,tiny_fragment_mm=.03)

def validate(settings):
    s={**DEFAULTS,**settings}
    for k in ('port','speed','power','frequency','dpi'):
        if isinstance(s[k],bool) or int(s[k])!=float(s[k]):raise ValueError('Helix '+k+' must be an integer.')
        s[k]=int(s[k])
    if not s['host'].strip() or any(c.isspace() for c in s['host']):raise ValueError('Enter a laser IP address or hostname.')
    for k in ('x','y','bed_width','bed_height','tiny_fragment_mm'):
        s[k]=float(s[k])
        if not isfinite(s[k]):raise ValueError('Invalid Helix position or bed size.')
    if not (1<=s['port']<=65535 and 1<=s['speed']<=100 and 1<=s['power']<=100 and 10<=s['frequency']<=5000):raise ValueError('Invalid Helix port, speed, power or frequency.')
    if s['dpi'] not in (75,150,200,300,400,600,1200):raise ValueError('Unsupported Helix DPI.')
    if min(s['x'],s['y'])<0 or min(s['bed_width'],s['bed_height'])<=0:raise ValueError('Use positive bed coordinates; negative offsets are not supported.')
    if not isinstance(s['ignore_tiny_fragments'],bool) or not .001<=s['tiny_fragment_mm']<=.1:raise ValueError('Tiny-fragment threshold must be 0.001–0.100 mm.')
    return s

class LaserGridError(ValueError):
    def __init__(self,message,diagnostic):
        super().__init__(message);self.laser_diagnostic=diagnostic


def quantize(contours,copper_bounds,alignment,s,coverage_radius_mm=0,coverage_radius_y_mm=None,ignore_tiny_mm=0):
    """Preserve every exposure, even when distinct lanes round to identical routes."""
    raw=[list(part.coords) for shape in contours for part in line_parts(shape)]
    for hole in alignment:
        raw.extend([[(hole.x-.25,hole.y),(hole.x+.25,hole.y)],[(hole.x,hole.y-.25),(hole.x,hole.y+.25)]])
    if not raw:raise ValueError('No isolation paths to send.')
    # Include beam-path extent as well as copper so edge isolation never goes negative.
    left=min(copper_bounds[0],min(x for r in raw for x,y in r));top=max(copper_bounds[3],max(y for r in raw for x,y in r))
    step=25.4/s['dpi'];routes=[];collapsed=[];fragment_kinds=[];duplicates=0;seen=set();max_error=0.
    for route in raw:
        points=[]
        for x,y in route:
            bx=x-left+s['x'];by=top-y+s['y'];q=(floor(bx/step+.5),floor(by/step+.5))
            if bx<0 or by<0 or q[0]*step>s['bed_width'] or q[1]*step>s['bed_height']:raise ValueError('Laser artwork does not fit the configured bed at this offset.')
            max_error=max(max_error,hypot(q[0]*step-bx,q[1]*step-by))
            if not points or q!=points[-1]:points.append(q)
        source_length=sum(hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(route,route[1:]))
        if len(points)<2 or (ignore_tiny_mm>0 and source_length<=ignore_tiny_mm):
            fragment_kinds.append('subgrid' if len(points)<2 else 'short_path')
            collapsed.append([(x-left+s["x"],top-y+s["y"]) for x,y in route]);continue
        key=tuple(points);reverse=tuple(reversed(points))
        if key in seen or reverse in seen:duplicates+=1
        seen.add(key);routes.append(points)
    covered=0;covered_indices=set();ignored=[]
    if collapsed and routes and coverage_radius_mm>0:
        from shapely.geometry import LineString,Point
        from shapely.strtree import STRtree
        from shapely.ops import unary_union
        rx=coverage_radius_mm;ry=coverage_radius_y_mm or rx
        # Scale the ellipse to a unit-radius circle. Test the union of nearby
        # stroke footprints, not only the single nearest stroke to one endpoint.
        lines=[LineString([(x*step/rx,y*step/ry) for x,y in r]) for r in routes];tree=STRtree(lines);buffers={}
        def buffered(index):
            if index not in buffers:buffers[index]=lines[index].buffer(.99999,quad_segs=64)
            return buffers[index]
        for index,fragment in enumerate(collapsed):
            path=LineString([(x/rx,y/ry) for x,y in fragment]);nearest_index=int(tree.nearest(path))
            if buffered(nearest_index).covers(path):
                covered+=1;covered_indices.add(index);continue
            candidates=tree.query(path.buffer(1.00001).envelope)
            if len(candidates) and unary_union([buffered(int(i)) for i in candidates]).covers(path):
                covered+=1;covered_indices.add(index)
    unresolved=[]
    for index,fragment in enumerate(collapsed):
        if index in covered_indices:continue
        source=[(x+left-s['x'],top-y+s['y']) for x,y in fragment]
        issue=dict(reason=fragment_kinds[index],source_points=source,source_center=[sum(x for x,y in source)/len(source),sum(y for x,y in source)/len(source)],length_mm=sum(hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(source,source[1:])))
        if ignore_tiny_mm>0 and issue['length_mm']<=ignore_tiny_mm:ignored.append(issue)
        else:unresolved.append(issue)
    if unresolved:
        raise LaserGridError(f'{len(unresolved)} laser paths collapse to points at {s["dpi"]} DPI without a covering burn. No laser job was created. Red markers locate the affected details. Review them, adjust the design/DPI, or explicitly enable the tiny-fragment filter.',dict(dpi=s['dpi'],grid_mm=step,issues=unresolved,covered_subgrid_fragments=covered))
    return routes,dict(source_left=left,source_top=top,grid_mm=step,maximum_rounding_mm=max_error,duplicate_exposures=duplicates,
                       covered_subgrid_fragments=covered,ignored_tiny_fragments=ignored,path_count=len(routes),extent_mm=[max(x for r in routes for x,y in r)*step,max(y for r in routes for x,y in r)*step])

def timing(routes,s):
    step=25.4/s['dpi'];length=sum(hypot(b[0]-a[0],b[1]-a[1])*step for r in routes for a,b in zip(r,r[1:]));travel=(hypot(*routes[0][0])*step if routes else 0)+sum(hypot(b[0][0]-a[-1][0],b[0][1]-a[-1][1])*step for a,b in zip(routes,routes[1:]))
    # Direct full-pattern coupon measured 62 s, 2026-10-26. Fit a 1.5 s job
    # overhead + .08 s/path + travel/82.52, solving remaining speed at 10%.
    # One observation cannot identify acceleration: broad uncertainty is intentional.
    coupon_length=482.82919221293224
    effective=coupon_length/(62-1.5-44*.08-290.1905131311991/82.52)
    seconds=1.5+length/(effective*s['speed']/10)+travel/82.52+len(routes)*.08
    def label(v):v=ceil(v);return f'{v//60}:{v%60:02}'
    return dict(seconds=seconds,label=label(seconds),range=label(seconds*.7)+'–'+label(seconds*1.3),length_mm=length,travel_mm=travel,
                note='Provisional direct-Helix estimate anchored to the 62-second four-pattern coupon at speed 10. Travel/acceleration are approximate; other speeds extrapolated, not calibrated.')

def prepare(geometry,contours,alignment,destination,settings,title='PCB_ISOLATION',isolation_settings=None,print_features=None,print_outline=None):
    s=validate(settings);destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    radius=isolation_settings.width_mm/2 if isolation_settings else 0
    radius_y=(isolation_settings.width_y_mm or isolation_settings.width_mm)/2 if isolation_settings else 0
    try:routes,report=quantize(contours,geometry.bounds,alignment,s,coverage_radius_mm=radius,coverage_radius_y_mm=radius_y,ignore_tiny_mm=s['tiny_fragment_mm'] if s['ignore_tiny_fragments'] else 0)
    except LaserGridError as error:
        diagnostic=write_grid_diagnostic(geometry,contours,destination,error.laser_diagnostic)
        error.laser_diagnostic['review']=str(diagnostic.resolve())
        raise
    from .laser_order import optimize_laser_routes
    routes,optimization=optimize_laser_routes(routes,report['grid_mm'])
    report.update(settings=s,timing=timing(routes,s),optimization=optimization)
    title='PCB_'+re.sub('[^A-Za-z0-9]+','_',title).strip('_')[:28]+'_'+sha256(title.encode()).hexdigest()[:6].upper();report['title']=title
    tsv=destination/'helix-paths.tsv';prn=destination/'laser-job.prn'
    header='\t'.join(map(str,[s['dpi'],s['speed'],s['power'],s['frequency'],s['bed_width'],s['bed_height'],title]))
    tsv.write_text(header+'\n'+'\n'.join(' '.join(f'{x},{y}' for x,y in r) for r in routes)+'\n',encoding='ascii')
    helper=asset_root()/'helix';java=helper/'java/bin/java.exe'
    result=subprocess.run([str(java),'-cp',str(helper/'build'),'PCBHelixJob',str(tsv.resolve()),str(prn.resolve())],capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Helix preparation failed: '+result.stderr[-1500:])
    report['sha256']=sha256(prn.read_bytes()).hexdigest();report['bytes']=prn.stat().st_size
    (destination/'helix-job.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Exact sent coordinate grid over original retained copper. No redraw choices
    # can change the machine geometry from this self-contained review.
    left=report['source_left'];top=report['source_top'];step=report['grid_mm']
    polygons=[geometry] if geometry.geom_type=='Polygon' else geometry.geoms
    copper=[]
    for poly in polygons:
        d=[]
        for ring in [poly.exterior,*poly.interiors]:d.append('M'+' L'.join(f'{x-left+s["x"]:.6f},{top-y+s["y"]:.6f}' for x,y in ring.coords)+' Z')
        copper.append('<path fill="#c89949" fill-rule="evenodd" d="'+' '.join(d)+'"/>')
    paths=['<path d="M'+' L'.join(f'{x*step:.6f},{y*step:.6f}' for x,y in r)+'"/>' for r in routes]
    if isolation_settings is not None:
        from shapely.geometry import LineString
        from .isolation import planned_footprint
        source_routes=[LineString([(x*step-s['x']+left,top-(y*step-s['y'])) for x,y in r]) for r in routes]
        intrusion=planned_footprint(source_routes,isolation_settings).intersection(geometry)
        report['predicted_copper_intrusion_mm2']=intrusion.area
        (destination/'helix-job.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        areas=[intrusion] if intrusion.geom_type=='Polygon' else getattr(intrusion,'geoms',[])
        amber=[]
        for poly in areas:
            if poly.geom_type!='Polygon' or poly.is_empty:continue
            d=[]
            for ring in [poly.exterior,*poly.interiors]:d.append('M'+' L'.join(f'{x-left+s["x"]:.6f},{top-y+s["y"]:.6f}' for x,y in ring.coords)+' Z')
            amber.append('<path fill="#ff7900" fill-opacity=".85" fill-rule="evenodd" d="'+' '.join(d)+'"/>')
        copper.extend(amber)
    ignored_marks=[]
    for index,issue in enumerate(report['ignored_tiny_fragments']):
        x,y=issue['source_center'];x=x-left+s['x'];y=top-y+s['y']
        ignored_marks.append(f'<g data-fragment="{index}" style="cursor:pointer;pointer-events:bounding-box" fill="none" stroke="#ff3333" stroke-width=".035"><circle cx="{x}" cy="{y}" r=".18"/><path d="M{x+.6},{y-.6} L{x+.13},{y-.13}"/></g>')
    w,h=report['extent_mm'];t=report['timing']
    details=f"{s['host']}:{s['port']} · speed {s['speed']}% · power {s['power']}% · {s['frequency']} Hz · {s['dpi']} DPI · offset X{s['x']:g} Y{s['y']:g} mm · manual focus · autofocus OFF"
    page='<!doctype html><meta charset="utf-8"><title>PCB Isolator · Direct Helix review</title><style>body{background:#17232d;color:#eee;font:15px system-ui;margin:16px}svg{width:100%;height:70vh;background:#101820}button{padding:8px}p{margin:8px 0}</style><h2>Direct Helix · '+escape(title)+'</h2><p>'+escape(details)+'</p><p>Estimated time <b>'+t['label']+'</b> (rough range '+t['range']+'). '+escape(t['note'])+'</p><p>Grid '+f'{step:.6f}'+' mm · maximum coordinate shift '+f'{report["maximum_rounding_mm"]:.4f}'+' mm · '+str(report['duplicate_exposures'])+' coincident route exposures retained; '+str(report['covered_subgrid_fragments'])+' small fragments already covered by surviving burns. Close lanes may occupy the same grid coordinates. Width calibration is provisional; rounding can remove additional copper or leave residual paint.</p><button id="toggle">Toggle copper</button><svg id="view" viewBox="-1 -1 '+f'{w+2} {h+2}'+'"><g id="copper">'+''.join(copper)+'</g>'+''.join(ignored_marks)+'<g fill="none" stroke="#ff5685" stroke-width=".018">'+''.join(paths)+'</g></svg><p>Gold: intended retained copper. Orange: predicted copper intrusion from the rounded paths and trial burn width (including approved narrow-gap fallback). Pink: exact quantized beam center paths, including selected alignment crosses. Artwork top-left is laser X0/Y0 plus the configured positive offset; router pin datum is separate. This is not a burn-footprint or etch simulation. Sending queues the job; start it at the Helix panel. No air-assist commands added.</p><script>document.getElementById("toggle").onclick=()=>{let c=document.getElementById("copper");c.style.display=c.style.display==="none"?"":"none"};const v=document.getElementById("view");let box=v.viewBox.baseVal;v.onwheel=e=>{e.preventDefault();const f=e.deltaY>0?1.15:1/1.15;const x=box.x+box.width/2,y=box.y+box.height/2;box.width*=f;box.height*=f;box.x=x-box.width/2;box.y=y-box.height/2};let drag=null;v.onpointerdown=e=>{drag=[e.clientX,e.clientY,box.x,box.y];v.setPointerCapture(e.pointerId)};v.onpointermove=e=>{if(drag){box.x=drag[2]-(e.clientX-drag[0])*box.width/v.clientWidth;box.y=drag[3]-(e.clientY-drag[1])*box.height/v.clientHeight}};v.onpointerup=v.onpointercancel=()=>drag=null;</script>'
    if report['ignored_tiny_fragments']:
        warning=f'<p style="background:#6b291f;padding:10px">Operator-selected filter: {len(report["ignored_tiny_fragments"])} tiny fragments up to {s["tiny_fragment_mm"]:.3f} mm long omitted. Red markers show their locations. These omissions are NOT proven harmless: inspect for possible copper bridges before engraving/etching.</p>'
        page=page.replace('<svg id="view"',warning+'<svg id="view"',1)
    if report['ignored_tiny_fragments']:
        diagnostic=dict(dpi=s['dpi'],grid_mm=step,issues=report['ignored_tiny_fragments'])
        write_grid_diagnostic(geometry,contours,destination,diagnostic,filtered=True)
        rows=''.join(f'<tr><td><button data-fragment="{i}">Locate {i+1}</button></td><td>{issue["length_mm"]:.5f} mm</td></tr>' for i,issue in enumerate(report['ignored_tiny_fragments']))
        panel='<details><summary>Filtered fragments · click a marker or expand for Locate</summary><p><a style="color:#9cf" href="Fragment-details.html">Open source-detail inspection</a></p><div style="max-height:180px;overflow:auto"><table>'+rows+'</table></div></details>'
        page=page.replace('<svg id="view"',panel+'<svg id="view"',1)
        positions=[[issue['source_center'][0]-left+s['x'],top-issue['source_center'][1]+s['y']] for issue in report['ignored_tiny_fragments']]
        script='const omitted='+json.dumps(positions)+';document.querySelectorAll("[data-fragment]").forEach(n=>n.onclick=e=>{e.stopPropagation();const p=omitted[Number(n.dataset.fragment)],b=document.getElementById("view").viewBox.baseVal;b.x=p[0]-.8;b.y=p[1]-.8;b.width=1.6;b.height=1.6;});'
        page=page.replace('</script>',script+'</script>',1)
    from .laser_playback import add_playback
    page=add_playback(page,routes,report,radius*2,radius_y*2)
    from .paper_print import paper_data,path_data,attach_paper_print
    native=[[(x*step-s['x']+left,top-y*step+s['y']) for x,y in route] for route in routes]
    paper=paper_data(title,'Laser',geometry,print_outline or [],print_features or [],[dict(title='Prepared laser paths',d=' '.join(path_data(r) for r in native))])
    page=attach_paper_print(page,paper,'<button id="laser-play">')
    review=destination/'Review.html';review.write_text(page,encoding='utf-8');return review

def check_connection(settings):
    s=validate(settings)
    with socket.create_connection((s['host'],s['port']),timeout=3):pass
    return 'TCP port reachable. No job data sent; this is not a machine-running check.'

def send(folder,settings,progress=lambda percent,message:None):
    """Send the reviewed bytes, not a regenerated job. No automatic retry."""
    folder=Path(folder);report=json.loads((folder/'helix-job.json').read_text(encoding='utf-8'));s=validate(settings)
    if s!=report['settings']:raise ValueError('Laser settings changed. Generate and review a fresh preview first.')
    data=(folder/'laser-job.prn').read_bytes()
    if sha256(data).hexdigest()!=report['sha256']:raise ValueError('Laser command file changed. Generate a fresh preview.')
    title=report['title'];host='PCBHOST';name=title
    control=f'H{host}\nPPCB_ISOLATOR\nJ{title}\nldfA{name}{host}\nUdfA{name}{host}\nN{title}\n'.encode('ascii')
    progress(0,'Connecting to laser queue…')
    try:
        with socket.create_connection((s['host'],s['port']),timeout=5) as sock:
            sock.settimeout(20)
            def ack(stage):
                if sock.recv(1)!=b'\0':raise OSError('Laser queue did not acknowledge '+stage)
            sock.sendall(b'\2\n');ack('queue request')
            sock.sendall(f'\2{len(control)} cfA{name}{host}\n'.encode());ack('control header')
            sock.sendall(control+b'\0');ack('control file')
            sock.sendall(f'\3{len(data)} dfA{name}{host}\n'.encode());ack('job header')
            for offset in range(0,len(data),32768):
                block=data[offset:offset+32768];sock.sendall(block);progress(min(99,int(100*(offset+len(block))/len(data))),'Transmitting laser job…')
            ack('job payload')
    except OSError as error:raise OSError(str(error)+'. Delivery may be partial; check the Helix queue before resending. No automatic retry.') from error
    progress(100,'Laser queue acknowledged the complete job.')
    receipt=dict(title=title,sha256=report['sha256'],bytes=len(data),host=s['host'],submitted_at=time.time(),status='queue_acknowledged_not_started')
    with (settings_root()/'laser-transmissions.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(receipt)+'\n')
    return f'{title}: complete job acknowledged by {s["host"]}. Select and start it at the Helix panel. Running/completion status is unavailable.'


def write_grid_diagnostic(geometry,contours,destination,diagnostic,filtered=False):
    """A failed preparation remains inspectable, but has no runnable printer job."""
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    polygons=[geometry] if geometry.geom_type=='Polygon' else geometry.geoms
    copper=[]
    for polygon in polygons:
        d=[]
        for ring in [polygon.exterior,*polygon.interiors]:d.append('M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y in ring.coords)+' Z')
        copper.append('<path fill="#bd9455" fill-rule="evenodd" d="'+' '.join(d)+'"/>')
    paths=['<path d="M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y in part.coords)+'"/>' for shape in contours for part in line_parts(shape)]
    marks=[];rows=[]
    for number,issue in enumerate(diagnostic['issues'],1):
        x,y=issue['source_center'];issue['number']=number
        marks.append(f'<g stroke="#ff3333" fill="none" stroke-width=".035"><circle cx="{x}" cy="{-y}" r=".2"/><path d="M{x+.65},{-y-.65} L{x+.14},{-y-.14} l.18,-.03 M{x+.14},{-y-.14} l.03,-.18"/></g>')
        rows.append(f'<tr><td><button data-index="{number-1}">Locate {number}</button></td><td>{x:.5f}</td><td>{y:.5f}</td><td>{issue["length_mm"]:.5f}</td></tr>')
    x0,y0,x1,y1=geometry.bounds;view=[x0-.5,-y1-.5,x1-x0+1,y1-y0+1]
    data=json.dumps(diagnostic).replace('<','\u003c')
    page='''<!doctype html><meta charset="utf-8"><title>Laser preparation issues</title><style>body{background:#17232d;color:#eee;font:15px system-ui;margin:16px}svg{width:100%;height:65vh;background:#101820;touch-action:none}button{padding:7px}td,th{padding:5px;text-align:left}h2{color:#ff9b81}</style><h2>Laser preview only — no printer job created</h2><p>__COUNT__ sub-grid paths cannot be represented at __DPI__ DPI (__GRID__ mm grid). Red arrows identify source locations. Pink lines are the planned, unrounded isolation paths. Gold is retained copper. Click Locate to zoom; scroll to zoom and drag to pan.</p><p>These are tiny path fragments, not a count of bad pads or holes. Increasing DPI can change which fragments collapse and is not guaranteed to fix the design. Ignoring them can leave copper bridges; replacing them with a minimum stroke can remove intended copper. No details are silently discarded here.</p><button id="fit">Fit board</button><svg id="board" viewBox="__VIEW__"><g>__COPPER__</g><g fill="none" stroke="#ff8cc2" stroke-width=".008">__PATHS__</g>__MARKS__</svg><table><tr><th>Issue</th><th>Source X mm</th><th>Source Y mm</th><th>Path length mm</th></tr>__ROWS__</table><script>const data=__DATA__,svg=document.getElementById('board'),initial=__INITIAL__;let view=[...initial],drag=null;function draw(){svg.setAttribute('viewBox',view.join(' '))}document.getElementById('fit').onclick=()=>{view=[...initial];draw()};document.querySelectorAll('[data-index]').forEach(b=>b.onclick=()=>{const p=data.issues[Number(b.dataset.index)].source_center;view=[p[0]-.8,-p[1]-.8,1.6,1.6];draw()});svg.onwheel=e=>{e.preventDefault();const f=e.deltaY>0?1.15:1/1.15;const x=view[0]+view[2]/2,y=view[1]+view[3]/2;view=[x-view[2]*f/2,y-view[3]*f/2,view[2]*f,view[3]*f];draw()};svg.onpointerdown=e=>{drag=[e.clientX,e.clientY,...view];svg.setPointerCapture(e.pointerId)};svg.onpointermove=e=>{if(drag){view=[drag[2]-(e.clientX-drag[0])*drag[4]/svg.clientWidth,drag[3]-(e.clientY-drag[1])*drag[5]/svg.clientHeight,drag[4],drag[5]];draw()}};svg.onpointerup=svg.onpointercancel=()=>drag=null;</script>'''
    replacements={'__COUNT__':str(len(diagnostic['issues'])),'__DPI__':str(diagnostic['dpi']),'__GRID__':f'{diagnostic["grid_mm"]:.6f}','__VIEW__':' '.join(map(str,view)),'__INITIAL__':json.dumps(view),'__DATA__':data,'__COPPER__':''.join(copper),'__PATHS__':''.join(paths),'__MARKS__':''.join(marks),'__ROWS__':''.join(rows)}
    for key,value in replacements.items():page=page.replace(key,value)
    (destination/'laser-grid-issues.json').write_text(json.dumps(diagnostic,indent=2),encoding='utf-8')
    if filtered:
        page=page.replace('Laser preview only — no printer job created','Filtered fragments — source-detail inspection').replace('sub-grid paths cannot be represented at','tiny paths were omitted by the selected filter at').replace('No details are silently discarded here.','These details are omitted from the prepared job; inspect them before accepting the output.')
    review=destination/('Fragment-details.html' if filtered else 'Issues.html');review.write_text(page,encoding='utf-8');return review
