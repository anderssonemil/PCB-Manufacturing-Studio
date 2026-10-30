"""Millimetre-sized paper inspection, independent of review zoom and animation."""
from dataclasses import asdict,is_dataclass
from pathlib import Path
import json


def path_data(points):
    return 'M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y in points)


def paper_data(title,role,geometry,outline=(),features=(),tools=()):
    commands=[]
    display=geometry.simplify(.001,preserve_topology=True)
    for polygon in [display] if display.geom_type=='Polygon' else display.geoms:
        for ring in [polygon.exterior,*polygon.interiors]:commands.append(path_data(ring.coords)+' Z')
    bounds=list(geometry.bounds)
    for ring in outline:
        a,b,c,d=ring.bounds;bounds=[min(bounds[0],a),min(bounds[1],b),max(bounds[2],c),max(bounds[3],d)]
    return dict(title=title,role=role,bounds=[bounds[0],-bounds[3],bounds[2]-bounds[0],bounds[3]-bounds[1]],
        copper=' '.join(commands),outline=' '.join(path_data(r.coords)+' Z' for r in outline),
        holes=[asdict(f) if is_dataclass(f) else dict(f) for f in features],tools=list(tools))


def attach_paper_print(page,data,button_before):
    button='<button id="paper-print" title="Open a full-board paper preview at actual size, independent of zoom or playback. Print at 100% scale.">Print 1:1…</button> '
    assert button_before in page,'Missing print-button insertion point'
    page=page.replace(button_before,button+button_before,1)
    payload=json.dumps(data,separators=(',',':')).replace('<','\\u003c')
    script=Path(__file__).with_name('paper_print.js').read_text(encoding='utf-8')
    return page+'<script id="paper-print-data" type="application/json">'+payload+'</script><script>'+script+'</script>'
