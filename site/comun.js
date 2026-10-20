const $=s=>document.querySelector(s),f=(n,d=2)=>n==null?'–':Number(n).toLocaleString('es-AR',{minimumFractionDigits:d,maximumFractionDigits:d});
const pm=x=>x==null?'–':(x>0?'+':'')+f(x)+'%',sg=x=>x>=0?'up':'dn';
const R_=document.documentElement;if(localStorage.tema==='claro'||(!localStorage.tema&&matchMedia('(prefers-color-scheme: light)').matches))R_.classList.add('claro');
function cargar(cb){$('#tema').onclick=()=>{R_.classList.toggle('claro');localStorage.tema=R_.classList.contains('claro')?'claro':'oscuro'};
fetch('data/mercado.json?'+Date.now()).then(r=>r.json()).then(d=>{document.body.className=d.animo;
$('#act').textContent='Actualizado: '+new Date(d.actualizado).toLocaleString('es-AR',{timeZone:'America/Argentina/Buenos_Aires',hour12:false})+' (hora Argentina) · '+d.universo.total+' activos';
const c=d.cinta.map(x=>`<span><b>${x.t}</b> <i class="${sg(x.chg)}">${pm(x.chg)}</i></span>`).join('');$('#cinta').innerHTML=c+c;cb(d)}).catch(e=>{console.error(e);$('#act').textContent='No se pudieron cargar los datos.'})}
function squarify(items,x,y,w,h){const tot=items.reduce((s,a)=>s+a.v,0),out=[];let rest=items.slice();
while(rest.length){const short=Math.min(w,h),area=w*h,rem=rest.reduce((s,a)=>s+a.v,0);let row=[],best=Infinity;
for(const it of rest){const r2=[...row,it],s=r2.reduce((a,b)=>a+b.v,0)/rem*area,mx=Math.max(...r2.map(a=>a.v/rem*area)),mn=Math.min(...r2.map(a=>a.v/rem*area)),worst=Math.max(short*short*mx/(s*s),s*s/(short*short*mn));if(worst>best)break;best=worst;row=r2}
const s=row.reduce((a,b)=>a+b.v,0)/rem*area,thick=s/short;let off=0;
row.forEach(a=>{const len=a.v/rem*area/thick;out.push(w>=h?{...a,x:x,y:y+off,w:thick,h:len}:{...a,x:x+off,y:y,w:len,h:thick});off+=len});
if(w>=h){x+=thick;w-=thick}else{y+=thick;h-=thick}rest=rest.slice(row.length)}
return out.map(a=>({...a,x:Math.round(a.x),y:Math.round(a.y),w:Math.max(0,Math.round(a.w)-1),h:Math.max(0,Math.round(a.h)-1)}))}
