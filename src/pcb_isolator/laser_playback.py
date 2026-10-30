"""Standalone playback of the exact optimized integer-grid printer routes."""
import json
import re
from pathlib import Path


def add_playback(page,routes,report,width_x,width_y):
    data=dict(routes=routes,grid=report['grid_mm'],widthX=width_x or .075,widthY=width_y or width_x or .075,
              timing=report['timing'],optimization=report['optimization'])
    panel='''<section class="playback"><button id="laser-play">Play</button> <button id="laser-restart">Restart</button> <button id="laser-static">Static view</button> <button id="laser-fit">Fit board</button>
<label>Speed <select id="laser-speed"><option>1</option><option>5</option><option selected>20</option><option>50</option><option>100</option></select>×</label>
<label><input type="checkbox" id="laser-travel" checked>Travel</label>
<label>View <select id="laser-mode"><option value="thin">Beam paths</option><option value="burn">Predicted burn width</option></select></label>
<label>Copper <input id="laser-opacity" type="range" min="0" max="1" step=".05" value=".4"></label>
<input id="laser-time" type="range" min="0" max="1" step=".0001" value="0"><output id="laser-status"></output></section>'''
    optimization=report['optimization']
    stats=f"<p>{len(routes):,} paths · {report['timing']['length_mm']:.1f} mm engraving · rapid travel {optimization['before_travel_mm']:.1f} → {optimization['after_travel_mm']:.1f} mm · saved {optimization['saved_percent']:.1f}% travel. Engraving geometry and repeated exposures preserved.</p>"
    page=page.replace('<svg id="view"',panel+stats+'<svg id="view"',1)
    page=page.replace('<g fill="none" stroke="#ff5685" stroke-width=".018">','<g id="static-paths" fill="none" stroke="#ff5685" stroke-width=".018">',1)
    # Keep the board in the viewport; detailed model/calibration notes remain available.
    notes=[]
    def timing_note(match):
        text=match.group(0);head,sep,note=text.partition('). ')
        if sep:notes.append('<p>'+note[:-4]+'</p>');return head+').</p>'
        return text
    page=re.sub(r'<p>Estimated time .*?</p>',timing_note,page,count=1)
    def grid_note(match):notes.append(match.group(0));return ''
    page=re.sub(r'<p>Grid .*?</p>',grid_note,page,count=1)
    page=page.replace('<button id="toggle">Toggle copper</button>','<button id="toggle">Toggle copper</button><details class="model-notes"><summary>Grid, calibration and timing notes</summary>'+''.join(notes)+'</details>',1)
    page=page.replace('<style>body','<meta name="viewport" content="width=device-width,initial-scale=1"><style>body',1)
    first=page.index('</style>')+len('</style>');svgi=page.index('<svg id="view"')
    page=page[:first]+'<div id="review-header">'+page[first:svgi]+'</div>'+page[svgi:]
    page+='''<style>.playback{padding:8px;background:#294353;border-radius:5px;display:flex;gap:7px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:2}.playback label{white-space:nowrap}.playback #laser-time{width:100%;margin:0}.playback output{font-size:13px}body{height:calc(100dvh - 24px);margin:12px;display:flex;flex-direction:column;overflow:hidden}#review-header{flex-shrink:0}#review-header p{font-size:13px;margin:5px 0}#view{height:auto;min-height:180px;flex:1;touch-action:none}body>p{font-size:12px;line-height:1.35;flex-shrink:0}.model-notes{display:inline-block;margin-left:8px}.model-notes[open]{display:block;max-height:22vh;overflow:auto}h2{font-size:20px;margin:8px 0}details+p{font-size:13px}@media(max-width:700px){body{height:auto;overflow:auto;display:block}#view{height:58dvh;min-height:260px}.playback{position:static}.playback label{font-size:12px}} </style>'''
    page+='<script id="laser-playback-data" type="application/json">'+json.dumps(data,separators=(',',':'))+'</script><script>'+Path(__file__).with_name('laser_playback.js').read_text(encoding='utf-8')+'</script>'
    page=page.replace('Artwork top-left is laser', 'Green: predicted burn footprint. Blue dashed: laser-off travel. Artwork top-left is laser')
    page=page.replace('This is not a burn-footprint or etch simulation.','Burn width is the provisional calibrated ellipse, not a measurement or an etch simulation. Playback starts at assumed laser X0/Y0 and models travel approximately; it does not report machine status.')
    return page
