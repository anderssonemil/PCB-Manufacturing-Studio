"""Overlay drill files and an optional outline on the copper/isolation preview."""
import argparse
from collections import Counter
from dataclasses import asdict
from html import escape
import json
from pathlib import Path
import webbrowser

from .drills import load_drills
from .isolation import load_settings
from .outline import load_outline
from .preview import write_preview


def write_machining_preview(copper, drill_paths, destination, outline=None, config=Path("config.toml")):
    features = [feature for path in drill_paths for feature in load_drills(path)]
    if len({feature.id for feature in features}) != len(features):
        raise ValueError("Drill input filenames must be unique; do not import the same file twice.")
    boundaries = load_outline(outline) if outline else []
    write_preview(copper, destination, load_settings(config))
    page = destination.read_text(encoding="utf-8")
    overlay = ['<g id="machining">']
    rows = []
    for index, feature in enumerate(features):
        name = escape(feature.id)
        if feature.end is None:
            overlay.append(f'<circle class="hole" id="hole-{index}" cx="{feature.x}" cy="{-feature.y}" r="{feature.diameter_mm/2}"><title>{name} · {feature.diameter_mm:.4f} mm</title></circle>')
        else:
            overlay.append(f'<path class="slot" d="M{feature.x},{-feature.y} L{feature.end[0]},{-feature.end[1]}" stroke-width="{feature.diameter_mm}"/>')
        eligible = feature.end is None and feature.diameter_mm >= 3.175
        checkbox = f'<input type="checkbox" data-hole="{index}" aria-label="Use {name} for alignment">' if eligible else "—"
        rows.append(f'<tr><td>{checkbox}</td><td>{name}</td><td>{feature.diameter_mm:.4f}</td><td>{feature.x:.4f}</td><td>{feature.y:.4f}</td><td>{"Slot" if feature.end else "Hole"}</td></tr>')
    for boundary in boundaries:
        commands = " L".join(f"{x},{-y}" for x, y in boundary.coords)
        overlay.append(f'<path class="outline" d="M{commands}"/>')
    overlay.append('</g>')
    page = page.replace('</g></svg>', "".join(overlay)+'</g></svg>')
    sizes = Counter(round(feature.diameter_mm, 4) for feature in features)
    summary = " · ".join(f"{count} × {diameter:.4f} mm" for diameter, count in sorted(sizes.items()))
    controls = f'''<p><label><input id="show-holes" type="checkbox" checked> Drills / slots</label>
<label><input id="show-outline" type="checkbox" checked> Outline</label>
{len(features)} drill features · {len(boundaries)} outline contours</p>
<p class="hint">Blue = holes/slots · White = outline · Green = selected alignment holes.
Inputs retain original coordinates. Confirm all files are the same revision and origin.</p>'''
    page = page.replace('</header>', controls+'</header>')
    panel = f'''<section id="drill-panel"><h2>Alignment holes · ⅛-inch pins (3.175 mm)</h2>
<p>{escape(summary)}</p><p>Select two or more suitable round mounting holes below. Nothing is selected automatically.
Existing hole diameters are preserved; selection does not change their fit on the pins.</p>
<p id="selection-status">No alignment holes selected.</p><button id="save-selection" disabled>Save alignment selection</button>
<p>This saves a planning JSON file only. Router programs and laser alignment marks are not generated in this version.</p>
<table><thead><tr><th>Alignment</th><th>Source / ID</th><th>Diameter mm</th><th>X mm</th><th>Y mm</th><th>Type</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></section>'''
    page = page.replace('<script>', panel+'<script>', 1)
    page = page.replace('</style>', '''
#machining .hole{fill:#229bff33;stroke:#59bbff;stroke-width:0.045}
#machining .slot{fill:none;stroke:#59bbff;stroke-linecap:round;opacity:.7}
#machining .outline{fill:none;stroke:white;stroke-width:.06}
#machining .selected{fill:#43e78666;stroke:#43e786;stroke-width:.12}
svg{height:65vh}#drill-panel{padding:20px 24px}table{border-collapse:collapse;font-size:13px}
td,th{text-align:left;padding:6px 14px;border-bottom:1px solid #344352}
</style>''')
    manifest = {"version": 1, "copper": str(copper.resolve()),
                "drill_sources": [str(path.resolve()) for path in drill_paths],
                "outline": str(outline.resolve()) if outline else None,
                "pin_diameter_mm": 3.175, "units": "mm",
                "machine": {"profile": "laguna_swift", "z_zero": "board_top",
                            "manual_spindle_speed": True, "automatic_spindle_start_stop": True,
                            "one_file_per_tool": True},
                "features": [asdict(feature) for feature in features]}
    data = json.dumps(manifest).replace("<", "\\u003c")
    script = '''
const job=__JOB__, selected=new Set();
document.getElementById('show-holes').onchange=e=>document.querySelectorAll('.hole,.slot').forEach(g=>g.style.display=e.target.checked?'':'none');
document.getElementById('show-outline').onchange=e=>document.querySelectorAll('.outline').forEach(g=>g.style.display=e.target.checked?'':'none');
document.querySelectorAll('[data-hole]').forEach(input=>input.onchange=()=>{
const i=Number(input.dataset.hole);if(input.checked)selected.add(i);else selected.delete(i);
document.getElementById('hole-'+i).classList.toggle('selected',input.checked);
document.getElementById('selection-status').textContent=selected.size+' alignment holes selected; '+(job.features.length-selected.size)+' remaining drill/slot features. Selection excludes alignment holes from future PCB drilling.';
document.getElementById('save-selection').disabled=selected.size<2;
});
document.getElementById('save-selection').onclick=()=>{
const payload={...job,alignment_ids:[...selected].map(i=>job.features[i].id)};
const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
const a=document.createElement('a');a.href=url;a.download='pcb-job.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
'''.replace('__JOB__', data)
    page = page.replace('</script>', script+'</script>')
    destination.write_text(page, encoding="utf-8")
    return destination.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('copper', type=Path, nargs='?')
    parser.add_argument('--drill', action='append', type=Path)
    parser.add_argument('--job', type=Path)
    parser.add_argument('--outline', type=Path)
    parser.add_argument('--config', type=Path, default=Path('config.toml'))
    parser.add_argument('--output', type=Path, default=Path('generated/machining-preview.html'))
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    try:
        if args.job:
            if args.copper or args.drill or args.outline:
                raise ValueError('Use either a job folder or individual input files.')
            from .kicad_export import load_job, resolve_job_folder
            args.job = resolve_job_folder(args.job)
            print(f'Opening export: {args.job}', flush=True)
            args.copper, args.drill, args.outline = load_job(args.job)
            args.output = args.job/'outputs/machining-preview.html'
        if not args.copper or not args.drill:
            raise ValueError('Provide a job folder, or copper and drill files.')
        destination = write_machining_preview(args.copper, args.drill, args.output, args.outline, args.config)
        if args.job:
            page = destination.read_text(encoding='utf-8')
            page = page.replace('</h1>', '</h1><p class="hint">Export: '+escape(args.job.name)+'</p>', 1)
            destination.write_text(page, encoding='utf-8')
    except Exception as error:
        parser.exit(1, f'Could not create machining preview: {error}\n')
    print(f'Saved: {destination}')
    if not args.no_open:
        webbrowser.open(destination.as_uri())


if __name__ == '__main__':
    main()
