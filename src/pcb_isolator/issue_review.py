"""Portable diagnostic drawing when a module cannot prepare machine output."""
from html import escape
import json
from pathlib import Path

def write_issue_review(board,error,destination,module):
    geometry=board['copper'];polygons=[geometry] if geometry.geom_type=='Polygon' else geometry.geoms;drawing=[]
    for p in polygons:
        d=['M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y in ring.coords)+' Z' for ring in [p.exterior,*p.interiors]]
        drawing.append('<path fill="#b89356" fill-rule="evenodd" d="'+' '.join(d)+'"/>')
    for ring in board['outline']:drawing.append('<path fill="none" stroke="white" stroke-width=".04" d="M'+' L'.join(f'{x},{-y}' for x,y in ring.coords)+'"/>')
    issues=getattr(error,'feature_diagnostic',{}).get('issues',[])
    if not issues and hasattr(error,'diagnostic'):
        xy=error.diagnostic.get('closest_xy')
        if xy:issues=[dict(source_center=xy,reason=str(error))]
    rows=[]
    for index,issue in enumerate(issues):
        x,y=issue['source_center'];drawing.append(f'<circle cx="{x}" cy="{-y}" r=".7" fill="none" stroke="#ff4444" stroke-width=".08"/><path d="M{x+1.3},{-y-1.3} L{x+.4},{-y-.4}" stroke="#ff4444" stroke-width=".1"/>')
        rows.append(f'<p><button data-index="{index}">Locate {index+1}</button> X{x:.4f} Y{y:.4f} · '+escape(issue.get('reason','Affected feature'))+'</p>')
    x0,y0,x1,y1=geometry.bounds;view=[x0-1,-y1-1,x1-x0+2,y1-y0+2]
    data=json.dumps([i['source_center'] for i in issues]);initial=json.dumps(view)
    page='<!doctype html><meta charset="utf-8"><title>'+module+' diagnostic</title><style>body{font:15px system-ui;background:#17232d;color:#eee;margin:16px}svg{width:100%;height:70vh;background:#101820}button{padding:8px}</style><h2>'+module+' preview needs attention</h2><p>'+escape(str(error))+'</p><p>No machine program for this failed module is included. The other module can still be reviewed. Return to the app to choose a tool, omit eligible internal cutouts, or continue with the other module only.</p><button id="fit">Fit board</button><svg id="v" viewBox="'+' '.join(map(str,view))+'">'+''.join(drawing)+'</svg>'+''.join(rows)+'<script>const svg=document.getElementById("v"),initial='+initial+',points='+data+';document.getElementById("fit").onclick=()=>svg.setAttribute("viewBox",initial.join(" "));document.querySelectorAll("[data-index]").forEach(b=>b.onclick=()=>{const p=points[Number(b.dataset.index)];svg.setAttribute("viewBox",[p[0]-2,-p[1]-2,4,4].join(" "))});svg.onwheel=e=>{e.preventDefault();let b=svg.viewBox.baseVal;const f=e.deltaY>0?1.15:1/1.15,x=b.x+b.width/2,y=b.y+b.height/2;b.width*=f;b.height*=f;b.x=x-b.width/2;b.y=y-b.height/2};</script>'
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(page,encoding='utf-8');return destination
