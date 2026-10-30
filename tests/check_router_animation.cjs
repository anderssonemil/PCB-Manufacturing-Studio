// Execute the self-contained review in a minimal DOM to test its controls
// and animation clock deterministically, without a browser or CNC attached.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const nodes=new Map();
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.style={};this.value='';this.checked=true;this.textContent='';this.attributes={};}
  setAttribute(k,v){this.attributes[k]=v;if(k==='id'){this.id=v;nodes.set(v,this);}}
  append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
  replaceChildren(...items){this.children=[];this.append(...items);}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
  addEventListener(){}
  getScreenCTM(){return {inverse:()=>({})};}
}
for(const match of html.matchAll(/id="([^"]+)"/g)){const e=new Element('div');e.setAttribute('id',match[1]);}
nodes.get('anim-speed').value='100';nodes.get('rapid-estimate').value='3000';
let now=0,next=0;const frames=new Map();
const context=vm.createContext({console,document:{getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag),createElementNS:(ns,tag)=>new Element(tag)},
  performance:{now:()=>now},requestAnimationFrame:fn=>{const id=++next;frames.set(id,fn);return id;},cancelAnimationFrame:id=>frames.delete(id),
  DOMPoint:class{constructor(x,y){this.x=x;this.y=y;}matrixTransform(){return this;}}});
vm.runInContext(script,context);
const run=code=>vm.runInContext(code,context);
const click=id=>nodes.get(id).onclick();
function advanceUntilPaused(){let count=0;while(run('anim.running')){
  assert(++count<20000,'Animation failed to finish');now+=250;
  const current=[...frames.values()];frames.clear();current.forEach(fn=>fn(now));
  assert(frames.size<=1,'Duplicate animation frame loop');
}}
assert(run('job.programs.every(p=>p.motions.length>0)'));
assert(run('job.copper_path.length>0'));
run('selected=job.programs.findIndex(p=>p.pin_avoidance);render()');
const yellow=nodes.get('zone-layer').children[0];
assert(Math.abs(yellow.attributes.r-run('job.pins[0].radius+cfg.alignment_pins.xy_margin_mm'))<1e-9);
assert(yellow.attributes.r<run('job.programs[selected].pin_avoidance.keepout_radius_mm'));
run('selected=0;render()');
nodes.get('copper').checked=false;nodes.get('copper').onchange();
assert.equal(nodes.get('copper-layer').style.display,'none');
nodes.get('copper').checked=true;nodes.get('copper').onchange();
assert.equal(nodes.get('copper-layer').style.display,'');
click('anim-all');assert(run('anim.running'));advanceUntilPaused();
assert.equal(run('anim.pending'),null);
assert.equal(run('selected'),run('job.programs.length')-1);
assert.equal(run('anim.t'),run('anim.duration'));
assert.equal(nodes.get('anim-status').textContent,'Animation complete');
assert(nodes.get('anim-z').textContent.includes('Z '));
click('anim-restart');assert.equal(run('anim.t'),0);assert.equal(run('selected'),0);
nodes.get('anim-position').value=10000;nodes.get('anim-position').oninput();
assert.equal(run('selected'),run('job.programs.length')-1);
click('anim-selected');assert.equal(run('anim.stages.length'),1);
click('anim-play');assert(!run('anim.running'));
const duration=run('anim.duration');nodes.get('rapid-estimate').value=100;nodes.get('rapid-estimate').onchange();
assert(run('anim.duration')>duration);
click('anim-static');assert(!run('anim.active'));
nodes.get('operation').value='1';nodes.get('operation').onchange();assert.equal(run('selected'),1);
nodes.get('rapid-estimate').value=3000;
click('anim-selected');advanceUntilPaused();assert.equal(run('selected'),1);
click('anim-next');assert.equal(run('selected'),2);assert.equal(run('anim.stages.length'),1);advanceUntilPaused();
click('anim-all');advanceUntilPaused();assert.equal(run('anim.pending'),null);assert.equal(run('anim.t'),run('anim.duration'));
console.log('Animation controls passed: all tools, next tool, resume, restart, seek, selected operation, rapid estimate, continuous playback.');
