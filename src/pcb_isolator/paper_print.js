(()=>{
'use strict';
const data=JSON.parse(document.getElementById('paper-print-data').textContent);
function openPaper(){
 const w=window.open('','_blank');if(!w){alert('Allow this review to open its paper preview window.');return}
 const d=w.document;d.open();d.write(`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PCB paper check · 1:1</title><style>
 *{box-sizing:border-box}body{font:14px system-ui;background:#eee;color:#111;margin:16px}.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px;background:white;border:1px solid #ccc;max-width:1000px}.controls label{white-space:nowrap}button,select{padding:6px}.sheet{background:white;width:max-content;margin-top:12px;padding:0}h1{font-size:13pt;margin:0 0 2mm}p{font-size:9pt;margin:1mm 0}.paper-art{display:block;max-width:none!important;background:white!important;height:auto}.scale{display:block;margin-top:3mm;width:60mm;height:25mm}#paper-title{max-width:180mm;overflow-wrap:anywhere} .notice{max-width:180mm}
 @page{size:auto;margin:10mm}@media print{html,body{background:white!important;color:black!important;margin:0!important;padding:0!important;width:max-content!important;height:auto!important;overflow:visible!important;display:block!important}.controls{display:none!important}.sheet{margin:0!important;break-inside:avoid;page-break-inside:avoid}.paper-art{max-width:none!important;max-height:none!important;flex:none!important}svg{print-color-adjust:exact;-webkit-print-color-adjust:exact}}
 </style></head><body><div class="controls"><button id="print-now">Print / Save PDF</button><label><input id="show-copper" type="checkbox" checked>Copper</label><label><input id="show-holes" type="checkbox" checked>Holes</label><label><input id="show-paths" type="checkbox" checked>Paths</label><label><input id="show-board" type="checkbox" checked>Outline</label><label>Paths <select id="paper-operation"></select></label><label><input id="mirror-paper" type="checkbox">Mirror horizontally</label><span>Use 100% / Actual size. Disable Fit to page and browser headers/footers.</span></div><main class="sheet"><h1 id="paper-title"></h1><p id="paper-dimensions"></p><p class="notice">Paper fit check only. Verify both scale bars before comparing components. Select paper/orientation large enough; oversized artwork is not automatically reduced or tiled.</p><svg id="paper-art" class="paper-art" xmlns="http://www.w3.org/2000/svg"></svg><svg class="scale" width="60mm" height="25mm" viewBox="0 0 60 25" xmlns="http://www.w3.org/2000/svg"><g fill="none" stroke="black" stroke-width=".15"><path d="M5,23 L5,3 M4,3 H6 M4,23 H6 M5,23 H55 M5,22 V24 M55,22 V24"/></g><g fill="black" font-family="sans-serif" font-size="2.5"><text x="22" y="21">50 mm</text><text x="8" y="10">20 mm vertical</text></g></svg><p id="paper-legend"></p></main></body></html>`);d.close();
 const ns='http://www.w3.org/2000/svg',svg=d.getElementById('paper-art');
 const el=(tag,attrs,parent)=>{const n=d.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));parent.appendChild(n);return n};
 const [x,y,width,height]=data.bounds,pad=data.padding_mm||2;
 d.querySelector('.sheet').style.width=Math.max(width+pad*2,60)+'mm';
 svg.setAttribute('width',(width+pad*2)+'mm');svg.setAttribute('height',(height+pad*2)+'mm');svg.style.width=(width+pad*2)+'mm';svg.style.height=(height+pad*2)+'mm';svg.setAttribute('viewBox',[x-pad,y-pad,width+pad*2,height+pad*2].join(' '));
 const artwork=el('g',{},svg),copper=el('path',{d:data.copper,fill:'#e2e2e2',stroke:'#555','stroke-width':.035,'fill-rule':'evenodd'},artwork);
 const outline=el('path',{d:data.outline,fill:'none',stroke:'#111','stroke-width':.12},artwork);
 const paths=el('g',{fill:'none',stroke:data.role==='Laser'?'#b00040':'#006099','stroke-width':.06,'stroke-linecap':'round','stroke-linejoin':'round'},artwork);
 const holes=el('g',{fill:'white',stroke:'#111','stroke-width':.06},artwork);
 for(const f of data.holes){
  if(f.end){el('path',{d:`M${f.x},${-f.y} L${f.end[0]},${-f.end[1]}`,stroke:'#111','stroke-width':f.diameter_mm,'stroke-linecap':'round',fill:'none'},holes);continue}
  el('circle',{cx:f.x,cy:-f.y,r:f.diameter_mm/2},holes);
  el('path',{d:`M${f.x-.15},${-f.y} h.3 M${f.x},${-f.y-.15} v.3`,fill:'none','stroke-width':.035},holes);
 }
 d.getElementById('paper-title').textContent=data.role+' · '+data.title+' · 1:1 paper check';
 d.getElementById('paper-dimensions').textContent=`Board/copper bounds: ${width.toFixed(3)} × ${height.toFixed(3)} mm. No scaling applied. `+(data.role==='Laser'?'Hole outlines use source drill sizes.':'Hole outlines use assigned drill sizes where available.');
 const op=d.getElementById('paper-operation');const option=(text,value)=>{const n=d.createElement('option');n.textContent=text;n.value=value;op.appendChild(n)};option('All paths','all');data.tools.forEach((tool,i)=>option(tool.title,String(i)));
 const selected=document.getElementById('operation');if(data.role==='Router'&&selected)op.value=selected.value;
 const draw=()=>{paths.replaceChildren();const chosen=op.value==='all'?data.tools:[data.tools[Number(op.value)]];for(const tool of chosen)if(tool)el('path',{d:tool.d},paths);d.getElementById('paper-legend').textContent='Gray: retained copper · Black: outline and holes · '+(data.role==='Laser'?'Red: exact prepared beam-center paths.':'Blue: cutting-center paths; rapid travel excluded.')};draw();op.onchange=draw;
 [['show-copper',copper],['show-holes',holes],['show-paths',paths],['show-board',outline]].forEach(([id,node])=>d.getElementById(id).onchange=e=>node.style.display=e.target.checked?'':'none');
 d.getElementById('mirror-paper').onchange=e=>{artwork.setAttribute('transform',e.target.checked?`translate(${2*x+width} 0) scale(-1 1)`:'');d.getElementById('paper-title').textContent=data.role+' · '+data.title+' · 1:1 paper check'+(e.target.checked?' · MIRRORED':'')};
 d.getElementById('print-now').onclick=()=>{w.focus();w.print()};
 w.paperCheck={data,svg};return w;
}
window.openPaperCheck=openPaper;
document.getElementById('paper-print').onclick=openPaper;
})();
