// Uses the ordered XYZ motion list embedded in this self-contained review.
const anim={active:false,running:false,t:0,stages:[],duration:0,pending:null,last:0,frame:null};
const $a=id=>document.getElementById(id);
const fmtTime=t=>{const s=Math.max(0,Math.floor(t));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};
function makeStages(indices){
  let clock=0;const rapid=Math.max(1,Number($a('rapid-estimate').value)||3000);
  anim.stages=indices.map(index=>{const p=job.programs[index],begin=clock;const moves=(p.motions||[]).map(m=>{
    const seconds=m.length_mm/(m.rapid?rapid:m.feed)*60;
    const move={...m,begin:clock,end:clock+Math.max(.001,seconds)};clock=move.end;return move;
  });return {index,begin,end:clock,moves}});anim.duration=clock;
}
function stageAt(t){return anim.stages.findIndex((s,i)=>t<s.end||i===anim.stages.length-1)}
function setupMessage(stage){
  const p=job.programs[stage.index],diam=p.tool_diameter_mm??p.nominal_pin_diameter_mm;
  let message='Install '+diam+' mm '+(p.holes?'drill':'cutter')+'. Set Z zero on '+(p.z_zero==='spoilboard_top'?'SPOILBOARD TOP':'PCB TOP')+'. '+(p.startup?'Leave Z at machine maximum after tool setting. Program first positions at X'+p.start[0]+' Y'+p.start[1]+' before lowering Z.':'Stage at work X'+p.start[0]+' Y'+p.start[1]+'.')+' Set spindle speed manually.';
  if(stage.index>0&&job.programs[stage.index-1].z_zero==='spoilboard_top')message='Manually drill the PCB alignment marks, install pins, register and tape the PCB, then REMOVE ALL PINS before machining. '+message;
  return message;
}
function stopAnimation(){anim.running=false;if(anim.frame!==null)cancelAnimationFrame(anim.frame);anim.frame=null;$a('anim-play').textContent='Resume';}
function requestTick(){anim.frame=requestAnimationFrame(tickAnimation);}
function startAnimation(all){
  stopAnimation();anim.active=true;anim.t=0;anim.pending=null;
  makeStages(all?job.programs.map((_,i)=>i):[selected]);
  if(!anim.duration){$a('anim-status').textContent='No motion available in this operation.';return;}
  $a('anim-setup').textContent=setupMessage(anim.stages[0]);
  $a('anim-setup-panel').open=true;
  anim.running=true;anim.last=performance.now();$a('anim-play').textContent='Pause';drawAnimation();requestTick();
}
function drawAnimation(){
  if(!anim.active||!anim.stages.length)return;
  const index=stageAt(anim.t),stage=anim.stages[index],p=job.programs[stage.index];
  if(selected!==stage.index){selected=stage.index;select.value=selected;render();}
  $a('anim-next').disabled=stage.index>=job.programs.length-1;$a('anim-prev').disabled=stage.index<=0;
  $a('anim-setup').textContent=setupMessage(stage);
  const existing=document.getElementById('animation-layer');if(existing)existing.remove();
  const group=el('g',{id:'animation-layer','pointer-events':'none'});
  let current=null,fraction=0;
  for(let i=0;i<=index;i++){
    const s=anim.stages[i],program=job.programs[s.index],diam=program.tool_diameter_mm??program.nominal_pin_diameter_mm;
    const commands=[],rapids=[],dots=new Map();
    for(const move of s.moves){
      if(move.begin>anim.t)break;
      const f=move.end<=anim.t?1:Math.max(0,Math.min(1,(anim.t-move.begin)/(move.end-move.begin)));
      const to=move.from.map((v,j)=>v+(move.to[j]-v)*f);
      if(move.rapid&&(move.from[0]!==move.to[0]||move.from[1]!==move.to[1]))rapids.push('M'+move.from[0]+','+(-move.from[1])+' L'+to[0]+','+(-to[1]));
      if(!move.rapid&&Math.min(move.from[2],to[2])<0){
        if(move.from[0]!==move.to[0]||move.from[1]!==move.to[1])commands.push('M'+move.from[0]+','+(-move.from[1])+' L'+to[0]+','+(-to[1]));
        else if(program.holes){const key=to[0]+','+to[1],old=dots.get(key);if(!old||to[2]<old[2])dots.set(key,to);}
      }
      if(i===index){current=move;fraction=f;}
      if(f<1)break;
    }
    if(commands.length&&$a('cut').checked)el('path',{d:commands.join(' '),fill:'none',stroke:'#58da92','stroke-width':diam,'stroke-linecap':'round','stroke-linejoin':'round',opacity:.5},group);
    if(rapids.length&&$a('travel').checked)el('path',{d:rapids.join(' '),fill:'none',stroke:'#91baff','stroke-width':1.8,'stroke-dasharray':'5 4','vector-effect':'non-scaling-stroke'},group);
    const finalDepth=Math.min(0,...s.moves.filter(m=>!m.rapid).map(m=>m.to[2]));
    if($a('cut').checked)for(const to of dots.values())el('circle',{cx:to[0],cy:-to[1],r:diam/2,fill:to[2]<=finalDepth+.0001?'#58da9299':'#ffb75a88'},group);
  }
  if(current){
    const pos=current.from.map((v,j)=>v+(current.to[j]-v)*fraction),diam=p.tool_diameter_mm??p.nominal_pin_diameter_mm;
    const tool=el('g',{} ,group);
    el('circle',{cx:pos[0],cy:-pos[1],r:diam/2,fill:pos[2]<0?'#ffb75a99':'#8ec5ff55',stroke:'#ffffff','stroke-width':.12},tool);
    const arm=Math.max(1,diam*.7);line([pos[0]-arm,pos[1]],[pos[0]+arm,pos[1]],'#ffffff',.09,tool);line([pos[0],pos[1]-arm],[pos[0],pos[1]+arm],'#ffffff',.09,tool);
    $a('anim-z').textContent='Z '+pos[2].toFixed(3)+' mm · '+(current.rapid?'Rapid travel':pos[2]<0?'Cutting / drilling':'Feed approach');
    $a('anim-xy').textContent='X '+pos[0].toFixed(3)+' · Y '+pos[1].toFixed(3)+' mm';
    const top=Math.max(1,cfg.machine.park_z_mm),bottom=-(cfg.board.thickness_mm+cfg.board.breakthrough_mm+cfg.spoilboard.pin_hole_depth_mm);
    $a('z-fill').style.width=(Math.max(0,Math.min(1,(pos[2]-bottom)/(top-bottom)))*100)+'%';
  }
  $a('anim-tool').textContent=(index+1)+' / '+anim.stages.length+' · '+p.file+' · '+(p.tool_diameter_mm??p.nominal_pin_diameter_mm)+' mm tool';
  $a('anim-time').textContent=fmtTime(anim.t)+' / '+fmtTime(anim.duration)+' estimated motion time';
  $a('anim-position').value=Math.round(anim.t/Math.max(.001,anim.duration)*10000);
  $a('anim-status').textContent=anim.pending!==null?'Paused for setup / tool change':anim.t>=anim.duration?'Animation complete':anim.running?'Playing':'Paused';
  for(const [id,opacity] of [['travel-layer',.6],['cut-layer',.2]]){const n=document.getElementById(id);if(n)n.setAttribute('opacity',opacity);}
}
function tickAnimation(now){
  if(!anim.running)return;
  const before=stageAt(anim.t),delta=Math.max(0,Math.min(.25,(now-anim.last)/1000));anim.last=now;
  let target=Math.min(anim.duration,anim.t+delta*Number($a('anim-speed').value));
  anim.t=target;
  if(anim.t>=anim.duration)stopAnimation();drawAnimation();
  if(anim.running)requestTick();
}
$a('anim-all').onclick=()=>startAnimation(true);
$a('anim-selected').onclick=()=>startAnimation(false);
$a('anim-prev').onclick=()=>{if(selected<=0)return;selected--;select.value=selected;render();startAnimation(false);};
$a('anim-next').onclick=()=>{
  if(selected>=job.programs.length-1)return;
  selected++;select.value=selected;render();startAnimation(false);
};
$a('anim-play').onclick=()=>{
  if(!anim.active)return startAnimation(true);
  if(anim.running){stopAnimation();drawAnimation();return;}
  if(anim.t>=anim.duration)return startAnimation(anim.stages.length>1);
  if(anim.pending!==null){anim.t=anim.stages[anim.pending].begin;anim.pending=null;}
  anim.running=true;anim.last=performance.now();$a('anim-play').textContent='Pause';drawAnimation();requestTick();
};
$a('anim-restart').onclick=()=>{const indices=anim.stages.length?anim.stages.map(s=>s.index):job.programs.map((_,i)=>i);stopAnimation();anim.active=true;anim.pending=null;anim.t=0;makeStages(indices);$a('anim-setup').textContent=setupMessage(anim.stages[0]);drawAnimation();};
$a('anim-position').oninput=()=>{if(!anim.active){anim.active=true;makeStages(job.programs.map((_,i)=>i));}stopAnimation();anim.pending=null;anim.t=anim.duration*Number($a('anim-position').value)/10000;drawAnimation();$a('anim-setup').textContent=setupMessage(anim.stages[stageAt(anim.t)]);};
$a('rapid-estimate').onchange=()=>{if(!anim.active)return;const portion=anim.t/Math.max(.001,anim.duration),indices=anim.stages.map(s=>s.index);stopAnimation();anim.pending=null;makeStages(indices);anim.t=portion*anim.duration;drawAnimation();};
function staticAnimation(){stopAnimation();anim.active=false;anim.pending=null;$a('anim-status').textContent='Static operation view';$a('anim-play').textContent='Pause / Resume';$a('anim-z').textContent='Z height';$a('anim-xy').textContent='';$a('anim-time').textContent='';$a('anim-setup').textContent='';$a('anim-tool').textContent='Choose Play all tools or Play current tool.';$a('anim-position').value=0;$a('z-fill').style.width='0';}
$a('anim-static').onclick=()=>{staticAnimation();render();};
// Existing operation selection returns to the regular static review.
select.onchange=()=>{staticAnimation();selected=Number(select.value);render();$a('anim-prev').disabled=selected<=0;$a('anim-next').disabled=selected>=job.programs.length-1;};
$a('anim-prev').disabled=selected<=0;
