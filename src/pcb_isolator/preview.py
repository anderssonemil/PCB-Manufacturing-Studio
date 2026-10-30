"""Generate an offline browser preview of imported copper geometry."""
import argparse
from html import escape
import json
from pathlib import Path
import webbrowser

from .importer import load_copper
from .isolation import IsolationSettings, generate_isolation, load_settings,footprint_buffer,isolation_diagnostics,planned_footprint,footprint_layers


def write_preview(source: Path, destination: Path, settings=None) -> Path:
    settings = settings or IsolationSettings()
    layer = load_copper(source)
    geometry = layer.geometry
    display_geometry=geometry.simplify(.0005,preserve_topology=True)
    polygons = [display_geometry] if display_geometry.geom_type == "Polygon" else list(display_geometry.geoms)
    paths = []
    for polygon in polygons:
        rings = [polygon.exterior, *polygon.interiors]
        segments = []
        for ring in rings:
            points = list(ring.coords)
            segments.append("M" + " L".join(f"{x:.8f},{-y:.8f}" for x, y in points) + " Z")
        paths.append('<path fill-rule="evenodd" d="' + " ".join(segments) + '"/>')
    x0, y0, x1, y1 = geometry.bounds
    width, height = x1 - x0, y1 - y0
    padding = max(width, height) * 0.04
    view = [x0-padding, -y1-padding, width+2*padding, height+2*padding]
    metadata = f"{width:.3f} × {height:.3f} mm copper extents · {len(polygons)} copper areas · source: {layer.source_units}"
    isolation = []
    contours=generate_isolation(geometry,settings)
    diagnostics=isolation_diagnostics(geometry,contours,settings)
    for index, contour in enumerate(contours):
        parts = list(contour.geoms) if hasattr(contour, "geoms") else [contour]
        commands = []
        for part in parts:
            if part.is_empty:continue
            commands.append("M" + " L".join(f"{x:.8f},{-y:.8f}" for x, y in part.coords))
        data = " ".join(commands)
        footprint=f'<path class="footprint" d="{data}"/>'
        if settings.directional:
            area=footprint_layers(contours,settings)[index].simplify(.001,preserve_topology=True)
            polygons=[area] if area.geom_type=='Polygon' else area.geoms
            commands=[]
            for polygon in polygons:
                if polygon.is_empty:continue
                for ring in [polygon.exterior,*polygon.interiors]:
                    commands.append('M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y in ring.coords)+' Z')
            footprint='<path class="footprint" style="fill:#00cec0;stroke:none;fill-rule:evenodd;opacity:.25" d="'+' '.join(commands)+'"/>'
        isolation.append(f'<g class="pass" data-pass="{min(index+1,settings.lines)}">{footprint}<path class="centerline" d="{data}"/></g>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<title>PCB Isolator — Isolation preview</title><style>
body{margin:0;background:#131a22;color:#e6edf3;font:15px system-ui}header{padding:18px 24px;background:#202b37}
h1{font-size:20px;margin:0 0 8px}p{margin:6px 0}button{padding:8px 16px;cursor:pointer}
svg{display:block;width:100%;height:calc(100vh - 240px);touch-action:none;cursor:grab}
#copper path{fill:#e6ac5a}#isolation path{fill:none;stroke-linecap:round;stroke-linejoin:round}
.footprint{stroke:#00cec0;stroke-width:__LASERWIDTH__;opacity:0.38}
.centerline{stroke:#ff547c;stroke-width:0.012}
.hide-footprints .footprint,.hide-centers .centerline{display:none}
select{padding:5px}#settings{margin:10px 0}
.hint{color:#b3c2d1}label{margin:0 18px}footer{padding:8px 24px;color:#b3c2d1}
</style><header><h1>PCB Isolator · Isolation preview</h1><p>__NAME__</p><p>__META__</p>
<button id="fit">Fit board</button><label><input id="mirror" type="checkbox"> Mirror horizontally</label>
<span class="hint">Scroll to zoom · Drag to pan</span>
<p id="settings">Isolation lines <select id="lines">__OPTIONS__</select>
<label><input id="centers" type="checkbox" checked> Path centers</label>
<label><input id="footprints" type="checkbox" checked> Laser width</label>
<span>__WIDTH__ mm laser · __OVERLAP__% overlap · <span id="cleared"></span> mm nominal cleared width</span></p></header>
<svg id="board" xmlns="http://www.w3.org/2000/svg" viewBox="__VIEW__"><g id="artwork"><g id="copper">__PATHS__</g><g id="isolation">__ISOLATION__</g></g></svg>
<footer>Gold = retained copper · Pink = path centers · Teal = laser footprint. Scroll in to inspect individual lines.
Narrow-gap fallback uses two nearly overlapping passes and may remove intended copper; displayed width applies where space permits. Run export-dxf.cmd to export configured lines in original orientation.
Original orientation; dimensions describe copper extents. Curves are approximated.</footer>
<script>
const svg=document.getElementById('board'), initial=__INITIAL__;let view=[...initial],drag=null;
const update=()=>svg.setAttribute('viewBox',view.join(' '));
const point=e=>new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
document.getElementById('fit').onclick=()=>{view=[...initial];update()};
document.getElementById('mirror').onchange=e=>document.getElementById('artwork').setAttribute('transform',e.target.checked?'translate(__SUMX__ 0) scale(-1 1)':'');
const lineSelect=document.getElementById('lines');
const setLines=()=>{const n=Number(lineSelect.value);document.querySelectorAll('.pass').forEach(g=>g.style.display=Number(g.dataset.pass)<=n?'':'none');document.getElementById('cleared').textContent=(__LASERWIDTH__+(n-1)*__SPACING__).toFixed(3)};
lineSelect.onchange=setLines;setLines();
document.getElementById('centers').onchange=e=>svg.classList.toggle('hide-centers',!e.target.checked);
document.getElementById('footprints').onchange=e=>svg.classList.toggle('hide-footprints',!e.target.checked);
svg.addEventListener('wheel',e=>{e.preventDefault();const p=point(e),f=e.deltaY>0?1.15:1/1.15;
if(view[2]*f<0.01||view[2]*f>initial[2]*100)return;
view=[p.x+(view[0]-p.x)*f,p.y+(view[1]-p.y)*f,view[2]*f,view[3]*f];update()},{passive:false});
svg.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,v:[...view],m:svg.getScreenCTM().inverse()};svg.setPointerCapture(e.pointerId)};
svg.onpointermove=e=>{if(!drag)return;const a=new DOMPoint(drag.x,drag.y).matrixTransform(drag.m),b=new DOMPoint(e.clientX,e.clientY).matrixTransform(drag.m);view=[drag.v[0]+a.x-b.x,drag.v[1]+a.y-b.y,drag.v[2],drag.v[3]];update()};
svg.onpointerup=svg.onpointercancel=()=>drag=null;
</script></html>'''
    replacements = {"__NAME__": escape(source.name), "__META__": escape(metadata),
                    "__VIEW__": " ".join(map(str, view)), "__INITIAL__": json.dumps(view),
                    "__SUMX__": str(x0+x1), "__PATHS__": "".join(paths),
                    "__ISOLATION__": "".join(isolation), "__LASERWIDTH__": str(settings.width_mm),
                    "__WIDTH__": str(settings.width_mm), "__OVERLAP__": str(settings.overlap_percent),
                    "__SPACING__": str(settings.spacing_mm),
                    "__OPTIONS__": "".join(f'<option value="{n}"'+(' selected' if n == settings.lines else '')+f'>{n}</option>' for n in range(1, settings.lines+1))}
    from .laser_timing import estimate_laser_time
    timing=estimate_laser_time(contours)
    page=page.replace('</header>',f'<p><strong>Estimated laser time: {timing["estimate"]}</strong> (rough range {timing["range"]}, min:sec) &middot; {timing["laser_on_length_mm"]/1000:.2f} m laser-on travel.</p><p class="hint">'+escape(timing['note'])+'</p></header>',1)
    if settings.adaptive:
        page=page.replace('Isolation lines <select','Maximum isolation lines <select')
        page=page.replace('lineSelect.onchange=setLines;setLines();',"lineSelect.disabled=true;lineSelect.title='Change maximum in the app and regenerate the adaptive plan.';setLines();")
        metadata=diagnostics.get('adaptive',{})
        counts=', '.join(str(n) for n in metadata.get('sampled_local_lane_counts',{})) or 'no shared narrow corridors'
        page=page.replace('</header>','<p>Adaptive shared lanes: local sampled counts '+counts+'. Spacing range '+' / '.join(f'{v:.3f}' for v in metadata.get('used_spacing_range_mm',[]))+' mm. Maximum applies to close shared corridors; wide areas retain capped boundary bands. Red marks identify incomplete clearing.</p></header>',1)
    if settings.directional:
        from shapely.ops import unary_union
        overcut=planned_footprint(contours,settings).intersection(geometry).simplify(.0005,preserve_topology=True)
        commands=[]
        for polygon in ([overcut] if overcut.geom_type=='Polygon' else getattr(overcut,'geoms',[])):
            if polygon.geom_type!='Polygon':continue
            for ring in [polygon.exterior,*polygon.interiors]:
                commands.append('M'+' L'.join(f'{x:.6f},{-y:.6f}' for x,y in ring.coords)+' Z')
        page=page.replace('</g></g></svg>','</g><path style="fill:#ff7900;fill-rule:evenodd;opacity:.85;stroke:none" d="'+' '.join(commands)+'"/></g></svg>',1)
        notes='<p style="color:#ffd28a">'+escape(' '.join(diagnostics['warnings']))+'</p>'
        page=page.replace('</header>',notes+'</header>',1)
        markers=''.join(f'<circle cx="{x}" cy="{-y}" r=".4" fill="none" stroke="red" stroke-width=".15"/>' for x,y in diagnostics['locations'])
        page=page.replace('</g></svg>',markers+'</g></svg>',1)
        page=page.replace('__WIDTH__ mm laser · __OVERLAP__% overlap',f'TRIAL X {settings.width_mm:g} / Y {settings.width_y_mm:g} mm · {settings.spacing_mm:g} mm spacing · artwork axes must match laser axes')
        page=page.replace('( __LASERWIDTH__', '(__LASERWIDTH__')
        page=page.replace('(__LASERWIDTH__+(n-1)*__SPACING__).toFixed(3)',"(__LASERWIDTH__+(n-1)*__SPACING__).toFixed(3)+' X / '+("+str(settings.width_y_mm)+"+(n-1)*__SPACING__).toFixed(3)+' Y'")
    for key, value in replacements.items():
        page = page.replace(key, value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding="utf-8")
    return destination.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gerber", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated/copper-preview.html"))
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        destination = write_preview(args.gerber, args.output, settings)
    except Exception as error:
        parser.exit(1, f"Could not import Gerber: {error}\n")
    print(f"Preview saved: {destination}")
    if not args.no_open:
        webbrowser.open(destination.as_uri())


if __name__ == "__main__":
    main()
