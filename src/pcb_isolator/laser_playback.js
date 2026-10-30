(()=>{
'use strict';
const data=JSON.parse(document.getElementById('laser-playback-data').textContent),svg=document.getElementById('view'),ns='http://www.w3.org/2000/svg',by=id=>document.getElementById(id);
const initial=svg.getAttribute('viewBox');
function element(tag,attrs,parent=svg){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));parent.appendChild(n);return n}
const thin=element('g',{fill:'none',stroke:'#ff72a1','stroke-width':.025,'stroke-linecap':'round','stroke-linejoin':'round'});
const rx=data.widthX/2,ry=data.widthY/2;
const burn=element('g',{fill:'none',stroke:'#66e4b5','stroke-width':2,'stroke-linecap':'round','stroke-linejoin':'round',opacity:.6,transform:`scale(${rx} ${ry})`});
const rapid=element('g',{fill:'none',stroke:'#72b5ff','stroke-width':.06,'stroke-dasharray':'.3 .18',opacity:.7});
const head=element('ellipse',{rx,ry,fill:'#fff6',stroke:'#ffffff','stroke-width':.025,'pointer-events':'none'});
const stages=[],nodes=[],travelNodes=[];let position=[0,0],clock=0;
const routes=data.routes.map(r=>r.map(p=>p.map(v=>v*data.grid)));
const totalLength=data.timing.length_mm,travelLength=data.timing.travel_mm;
const burnSpeed=totalLength/Math.max(.001,data.timing.seconds-1.5-routes.length*.08-travelLength/82.52);
function linePath(points,sx=1,sy=1){return points.map((p,i)=>(i?'L':'M')+(p[0]/sx)+','+(p[1]/sy)).join(' ')}
function stage(kind,a,b,seconds,index){const start=clock;clock+=seconds;stages.push({kind,a,b,start,end:clock,index})}
stage('Setup',position,position,1.5,-1);
routes.forEach((r,index)=>{
 const dist=Math.hypot(r[0][0]-position[0],r[0][1]-position[1]);stage('Travel',position,r[0],dist/82.52,index);
 travelNodes.push(element('path',{d:linePath([position,r[0]])},rapid));
 stage('Path start',r[0],r[0],.08,index);
 const a=element('path',{d:linePath(r),pathLength:1},thin),b=element('path',{d:linePath(r,rx,ry),pathLength:1},burn);nodes.push([a,b]);
 let length=0;const first=clock;
 const normLengths=r.slice(1).map((p,j)=>Math.hypot((p[0]-r[j][0])/rx,(p[1]-r[j][1])/ry)),normTotal=normLengths.reduce((a,b)=>a+b,0);let normBefore=0;
 for(let j=1;j<r.length;j++){const d=Math.hypot(r[j][0]-r[j-1][0],r[j][1]-r[j-1][1]);stage('Engraving',r[j-1],r[j],d/burnSpeed,index);Object.assign(stages[stages.length-1],{normBefore,normLength:normLengths[j-1],normTotal});normBefore+=normLengths[j-1];length+=d}
 nodes[index].start=first;nodes[index].end=clock;position=r[r.length-1];
});
let time=0,playing=false,staticMode=true,lastFrame=null,lastRoute=-2;
function label(t){const n=Math.floor(t);return Math.floor(n/60)+':'+String(n%60).padStart(2,'0')}
function find(t){let lo=0,hi=stages.length-1;while(lo<hi){const mid=(lo+hi)>>1;if(stages[mid].end<t)lo=mid+1;else hi=mid}return stages[lo]}
function showRoute(i,fraction){if(i<0||i>=nodes.length)return;for(const n of nodes[i]){n.style.display=fraction<=0?'none':'';n.setAttribute('stroke-dasharray',fraction>=1?'none':`${fraction} 1`)}}
function draw(force=false){
 const s=find(time),active=s.kind==='Engraving'?s.index:s.index-1;
 if(force){nodes.forEach((n,i)=>showRoute(i,staticMode?1:i<active?1:i===active?Math.max(0,Math.min(1,(time-n.start)/(n.end-n.start))):0));travelNodes.forEach(n=>n.style.display='')}
 else if(active!==lastRoute){const low=Math.max(0,Math.min(active,lastRoute)),high=Math.min(nodes.length-1,Math.max(active,lastRoute));for(let i=low;i<=high;i++)showRoute(i,i<active?1:0)}
 if(!staticMode&&s.kind==='Engraving')showRoute(active,Math.max(0,Math.min(1,(time-nodes[active].start)/(nodes[active].end-nodes[active].start))));
 by('static-paths').style.display='none';thin.style.display=by('laser-mode').value==='thin'?'':'none';burn.style.display=by('laser-mode').value==='burn'?'':'none';rapid.style.display=by('laser-travel').checked?'':'none';
 if(force||active!==lastRoute)travelNodes.forEach((n,i)=>n.style.display=staticMode||i<=s.index?'':'none');
 const f=Math.max(0,Math.min(1,(time-s.start)/(s.end-s.start||1))),p=[s.a[0]+(s.b[0]-s.a[0])*f,s.a[1]+(s.b[1]-s.a[1])*f];head.setAttribute('cx',p[0]);head.setAttribute('cy',p[1]);head.style.display=staticMode?'none':'';
 by('copper').style.opacity=by('laser-opacity').value;by('laser-time').value=time/clock;
 by('laser-status').textContent=staticMode?`Static view · ${routes.length} optimized paths · estimated ${label(clock)}`:`${label(time)} / ${label(clock)} estimated · ${s.kind} · path ${Math.max(0,s.index+1)} / ${routes.length} · X${p[0].toFixed(3)} Y${p[1].toFixed(3)} mm`;
 if(!staticMode&&s.kind==='Engraving'){const fraction=(s.normBefore+s.normLength*f)/s.normTotal;nodes[active][1].setAttribute('stroke-dasharray',fraction>=1?'none':`${fraction} 1`)}
 by('laser-play').textContent=playing?'Pause':time>=clock?'Replay':'Play';lastRoute=active;
}
function frame(now){if(playing){if(lastFrame!==null)time=Math.min(clock,time+(now-lastFrame)/1000*Number(by('laser-speed').value));if(time>=clock)playing=false;draw()}lastFrame=now;requestAnimationFrame(frame)}
by('laser-play').onclick=()=>{if(time>=clock)time=0;staticMode=false;playing=!playing;lastFrame=null;draw(true)};
by('laser-restart').onclick=()=>{playing=false;time=0;staticMode=false;lastFrame=null;draw(true)};
by('laser-static').onclick=()=>{playing=false;staticMode=true;draw(true)};
by('laser-fit').onclick=()=>svg.setAttribute('viewBox',initial);
by('laser-time').oninput=()=>{playing=false;staticMode=false;time=Number(by('laser-time').value)*clock;draw(true)};
['laser-mode','laser-travel','laser-opacity'].forEach(id=>by(id).oninput=()=>draw(true));
window.laserPlayback={data,stages,duration:clock,seek:t=>{time=Math.max(0,Math.min(clock,t));staticMode=false;draw(true)}};
draw(true);requestAnimationFrame(frame);
})();
