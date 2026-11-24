/* Indicador de Liquidez — medidor, serie histórica y simulador */
(function(){
const BANDAS=[
  {id:'inundacion',nombre:'Inundación',lo:80,hi:100,color:'#1a2a4a',dot:'#3a6ad4'},
  {id:'expansion',nombre:'Expansión',lo:60,hi:80,color:'#1a3d38',dot:'#3cb8a0'},
  {id:'neutral',nombre:'Neutral',lo:40,hi:60,color:'#2a3530',dot:'#9aa39a'},
  {id:'ajuste',nombre:'Ajuste',lo:20,hi:40,color:'#5a4520',dot:'#e0b84a'},
  {id:'sequia',nombre:'Sequía',lo:0,hi:20,color:'#d56a22',dot:'#e87520'}
];
const META=[
  {id:'m2',grupo:'liquidez',signo:1,modo:'chg13'},
  {id:'liq_neta',grupo:'liquidez',signo:1,modo:'chg13'},
  {id:'dolar',grupo:'liquidez',signo:-1,modo:'chg13'},
  {id:'amplitud',grupo:'liquidez',signo:1,modo:'manual'},
  {id:'vix',grupo:'estres',signo:-1,modo:'nivel'},
  {id:'move',grupo:'estres',signo:-1,modo:'nivel'},
  {id:'hy',grupo:'estres',signo:-1,modo:'nivel'},
  {id:'stlfsi',grupo:'estres',signo:-1,modo:'nivel'}
];
const GRP={
  liquidez:{t:'Liquidez',s:'qué tan fácil es conseguir dinero'},
  estres:{t:'Estrés',s:'qué tan asustados están los mercados'},
  fondeo:{t:'Fondeo',s:'plomería del dólar (unidades reales)'}
};

function erf(x){
  const s=x<0?-1:1; x=Math.abs(x);
  const a1=0.254829592,a2=-0.284496736,a3=1.421413741,a4=-1.453152027,a5=1.061405429,p=0.3275911;
  const t=1/(1+p*x);
  return s*(1-((((a5*t+a4)*t+a3)*t+a2)*t+a1)*t*Math.exp(-x*x));
}
const phi=x=>0.5*(1+erf(x/Math.SQRT2));
const scoreOf=x=>100*phi(x);
function rh(x,n){ if(x==null||!isFinite(x)) return null; const p=10**n; return Math.sign(x)*Math.floor(Math.abs(x)*p+0.5)/p; }
const r1=x=>rh(x,1), r2=x=>rh(x,2), r3=x=>rh(x,3);
function fondeoX(pb,res){ const a=pb==null?0:-0.025*Math.max(0,+pb); const b=res==null?0:-Math.max(0,3- +res); return {x:a+b,a,b}; }
function calcular(zSigned,pb,res){
  const act=zSigned.filter(z=>z!=null&&isFinite(z));
  const n=act.length, xb=n?act.reduce((s,z)=>s+z,0)/n:null;
  const f=fondeoX(pb,res), xt=xb==null?null:xb+f.x;
  const s=xt==null?null:scoreOf(xt), s0=xb==null?null:scoreOf(xb);
  const aportes=zSigned.map(z=>z==null||!n?null:z/n);
  return {n,x_base:xb,x_fondeo:f.x,x_total:xt,score:s,score_sin_fondeo:s0,
          fondeo_pts:(s==null||s0==null)?null:r1(r1(s)-r1(s0)),
          aportes,aporte_sofr:f.a,aporte_reservas:f.b};
}
function regimenDe(score){
  if(score==null) return {};
  const s=+score;
  let b=BANDAS[BANDAS.length-1];
  for(const x of BANDAS){ if(s>=x.lo && s<x.hi+1e-9 && (x.hi===100||s<x.hi)){ b=x; break; } }
  // Sequía <20, etc. — 80 exacto cuenta como Inundación (>=80)
  if(s>=80) b=BANDAS[0];
  else if(s>=60) b=BANDAS[1];
  else if(s>=40) b=BANDAS[2];
  else if(s>=20) b=BANDAS[3];
  else b=BANDAS[4];
  const prox=s<20?20:s<40?40:s<60?60:s<80?80:null;
  const titulo={Inundación:'INUNDACIÓN DE LIQUIDEZ',Expansión:'EXPANSIÓN DE LIQUIDEZ',Neutral:'LIQUIDEZ NEUTRAL',Ajuste:'AJUSTE DE LIQUIDEZ',Sequía:'SEQUÍA DE LIQUIDEZ'}[b.nombre];
  let sub='';
  if(b.nombre==='Sequía') sub=`Banda más baja · ${fmt(r1(20-s),1)} pts bajo ajuste`;
  else if(b.nombre==='Ajuste') sub=`Entre 20 y 40 · ${fmt(r1(40-s),1)} pts bajo neutral`;
  else if(b.nombre==='Neutral') sub='Banda media · 40 a 60';
  else if(b.nombre==='Expansión') sub=`Entre 60 y 80 · ${fmt(r1(s-60),1)} pts sobre neutral`;
  else sub='Banda más alta · sobre 80';
  return {regimen:b.nombre,titulo,subtitulo:sub,banda:b,
          al_proximo_regimen:prox==null?null:r1(prox-s),
          a_neutral:r1(Math.max(0,40-s))};
}
function fmt(n,d=1){ return n==null?'–':Number(n).toLocaleString('es-AR',{minimumFractionDigits:d,maximumFractionDigits:d}); }
function pm(n,d=1){ if(n==null) return '–'; const s=fmt(n,d); return (n>0?'+':'')+s; }
function el(html){ const t=document.createElement('template'); t.innerHTML=html.trim(); return t.content.firstChild; }
function svg(tag,attrs,text){
  const n=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const k in attrs) n.setAttribute(k,attrs[k]);
  if(text!=null) n.textContent=text;
  return n;
}

let L=null, state=null;

function signedFrom(st){
  return META.map(m=>{
    const e=st.entradas[m.id];
    if(!e||!e.activo||e.z==null||!isFinite(e.z)) return null;
    return m.signo*e.z;
  });
}
function evalState(st){
  const out=calcular(signedFrom(st), st.sofr_iorb_pb, st.reservas_t);
  return Object.assign({reg:regimenDe(out.score)}, out);
}

function renderKpis(node, items){
  node.innerHTML=items.map(([lab,val,cls])=>`<div class="kpi ${cls||''}"><small>${lab}</small><b>${val}</b></div>`).join('');
}

/* ---------- Vista 1 ---------- */
function renderV1(out){
  const s=r1(out.score), reg=out.reg||{};
  renderKpis($('#v1-kpis'),[
    ['Puntaje', fmt(s,1)],
    ['Régimen', reg.regimen||'–', 'or'],
    ['Al próximo régimen', pm(reg.al_proximo_regimen,1)],
    ['A neutral', pm(reg.a_neutral,1)]
  ]);
  $('#v1-score').textContent=fmt(s,1);
  $('#v1-title').textContent=reg.titulo||'';
  $('#v1-sub').textContent=reg.subtitulo||'';
  const s0=r1(out.score_sin_fondeo), fp=out.fondeo_pts;
  $('#v1-fondeo').textContent=`Sin fondeo ${fmt(s0,1)} · fondeo ${pm(fp,1)} pts`;
  // color del score según régimen
  const col=(reg.banda&&reg.banda.dot)||'#e87520';
  $('#v1-score').style.color=col;
  $('#v1-title').style.color=col;

  // tanque: 0 abajo, 100 arriba. viewBox 0 0 90 220, inner rect y=8..212 (h=204)
  const X=8,Y=8,W=52,H=204;
  const yOf=v=>Y+H*(1-v/100);
  const bands=$('#tankBands'); bands.innerHTML='';
  // dibujar de arriba hacia abajo
  const stack=[
    {lo:80,hi:100,c:'#1a2a4a'},
    {lo:60,hi:80,c:'#1a3d38'},
    {lo:40,hi:60,c:'#2a3530'},
    {lo:20,hi:40,c:'#5a4520'},
    {lo:0,hi:20,c:'#d56a22'}
  ];
  stack.forEach(b=>{
    const y=yOf(b.hi), h=yOf(b.lo)-yOf(b.hi);
    bands.appendChild(svg('rect',{x:X,y:y,width:W,height:h,fill:b.c}));
  });
  // onda en el nivel actual
  const wave=$('#tankWave'); wave.innerHTML='';
  const yl=yOf(Math.max(0,Math.min(100,s)));
  const amp=3.2, y0=yl;
  let d=`M ${X} 212 L ${X} ${y0}`;
  for(let i=0;i<=20;i++){
    const x=X+W*i/20;
    const y=y0+Math.sin(i/20*Math.PI*2)*amp;
    d+=` L ${x.toFixed(1)} ${y.toFixed(1)}`;
  }
  d+=` L ${X+W} 212 Z`;
  const wpath=svg('path',{d,fill:'url(#waveGrad)',opacity:.85});
  wpath.style.animation='none';
  wave.appendChild(wpath);
  // segunda onda desplazada, animada vía animate
  const d2Parts=['M '+X+' 212 L '+X+' '+y0];
  for(let i=0;i<=20;i++){ const x=X+W*i/20, y=y0+Math.sin(i/20*Math.PI*2+1.2)*amp; d2Parts.push('L '+x.toFixed(1)+' '+y.toFixed(1)); }
  d2Parts.push('L '+(X+W)+' 212 Z');
  const d2=d2Parts.join(' ');
  const w2=svg('path',{d:d2,fill:'#fff',opacity:.08});
  wave.appendChild(w2);

  // marcador punteado + flecha
  const mk=$('#tankMarker'); mk.innerHTML='';
  const line=svg('line',{x1:X-2,x2:X+W+18,y1:yl,y2:yl,stroke:'#fff',
    'stroke-width':'1.4','stroke-dasharray':'3 3','stroke-linecap':'round'});
  mk.appendChild(line);
  mk.appendChild(svg('polygon',{points:`${X+W+18},${yl} ${X+W+26},${yl-4} ${X+W+26},${yl+4}`,fill:'#fff'}));

  // labels de banda al lado del tanque (centros)
  const labs=$('#tankLabels');
  const Hpx=labs.clientHeight||340;
  labs.innerHTML=BANDAS.map(b=>{
    const mid=(b.lo+b.hi)/2;
    const on=reg.banda&&reg.banda.nombre===b.nombre;
    // el wrap tiene el svg; labels se posicionan en % del tanque interno (~ padding 8/220)
    const top=((8+204*(1-mid/100))/220)*100;
    return `<span class="${on?'on':''}" style="top:${top}%">${b.nombre}</span>`;
  }).join('');

  $('#v1-legend').innerHTML=BANDAS.map(b=>{
    const on=reg.banda&&reg.banda.nombre===b.nombre;
    const rng=b.lo===0?`< 20`:b.hi===100?`> 80`:`${b.lo}-${b.hi}`;
    return `<li class="${on?'on':''}"><i style="background:${b.dot}"></i>${b.nombre}
      ${on?`<span class="bar" style="background:${b.dot}"></span>`:''}
      <span class="rng">${rng}</span></li>`;
  }).join('');
}

/* ---------- Vista 2 ---------- */
function renderV2(){
  if(!L||!L.historia) return;
  const withF=$('#conFondeo').checked;
  const hist=L.historia;
  const last=hist[hist.length-1];
  const sc=withF?last.score:last.score_sin_fondeo;
  const reg=regimenDe(sc);
  renderKpis($('#v2-kpis'),[
    ['Pipo Score (serie)', fmt(sc,1), (sc<20?'or':'')],
    ['Nasdaq-100 · último', fmt(L.ndx_ultimo,0)],
    ['Régimen', reg.regimen||'–', 'or'],
    ['Correl. últimas 13 sem.', pm(L.correl_13s,2)]
  ]);
  const src=(L.fuentes||[]).join(' · ')||'FED + YAHOO';
  $('#v2-src').textContent='SERIE REAL · '+(src.length>48?'FED + YAHOO':src.toUpperCase());
  drawCharts(hist, withF);
}

function drawCharts(hist, withF){
  const ndx=$('#chartNdx'), sc=$('#chartScore');
  ndx.innerHTML=''; sc.innerHTML='';
  const W=1000, H1=280, H2=260;
  const pad={l:64,r:70,t:16,b:8};
  const xs=hist.map((_,i)=>pad.l+i/Math.max(1,hist.length-1)*(W-pad.l-pad.r));
  const xOf=i=>xs[i];
  // fondo por score (con o sin fondeo según checkbox, el sombreado sigue el score mostrado)
  const scoreAt=p=>withF?p.score:p.score_sin_fondeo;
  function shades(svgEl, top, bot){
    let i=0;
    while(i<hist.length){
      const s=scoreAt(hist[i]);
      let fill=null;
      if(s!=null && s<20) fill='rgba(200,70,20,.36)';
      else if(s!=null && s<40) fill='rgba(210,100,36,.20)';
      else if(s!=null && s>60) fill='rgba(40,150,95,.20)';
      if(!fill){ i++; continue; }
      let j=i;
      while(j+1<hist.length){
        const s2=scoreAt(hist[j+1]);
        const f2=s2!=null&&s2<20?'d':s2!=null&&s2<40?'o':s2!=null&&s2>60?'g':null;
        const f1=s<20?'d':s<40?'o':'g';
        if(f2!==f1) break;
        j++;
      }
      const x=xOf(i), w=xOf(j)-xOf(i)+Math.max(1,(xOf(1)-xOf(0)));
      svgEl.appendChild(svg('rect',{x,y:top,width:Math.max(1,w),height:bot-top,fill,stroke:'none'}));
      i=j+1;
    }
  }
  shades(ndx, pad.t, H1-pad.b-12);
  // NDX log
  const ndxVals=hist.map(p=>p.ndx).filter(v=>v!=null&&v>0);
  const nmin=Math.min(...ndxVals)*0.92, nmax=Math.max(...ndxVals)*1.05;
  const ly=v=>pad.t+(H1-pad.t-pad.b-16)*(1-(Math.log(v)-Math.log(nmin))/(Math.log(nmax)-Math.log(nmin)));
  // ticks log "redondos"
  const ticks=[];
  [5000,7000,10000,20000,30000,40000,50000].forEach(v=>{ if(v>=nmin && v<=nmax) ticks.push(v); });
  ticks.forEach(v=>{
    const y=ly(v);
    ndx.appendChild(svg('line',{x1:pad.l,x2:W-pad.r,y1:y,y2:y,stroke:'rgba(255,255,255,.06)','stroke-width':1}));
    ndx.appendChild(svg('text',{x:W-pad.r+8,y:y+4,'text-anchor':'start'}, v.toLocaleString('es-AR')));
  });
  ndx.appendChild(svg('text',{x:pad.l,y:14,fill:'#8c968d','font-size':11}, 'Nasdaq-100 · escala log'));
  let d='';
  hist.forEach((p,i)=>{
    if(p.ndx==null) return;
    d+=(d?' L':'M')+` ${xOf(i).toFixed(2)} ${ly(p.ndx).toFixed(2)}`;
  });
  ndx.appendChild(svg('path',{d,fill:'none',stroke:'#74c6e2','stroke-width':1.8,'stroke-linejoin':'round'}));
  // last pill (clamp inside viewBox so it never clips on mobile)
  const last=hist[hist.length-1];
  function addEndPill(el, x, y, w, fill, text, textFill){
    const cx=x, cy=y;
    el.appendChild(svg('circle',{cx:cx,cy:cy,r:3.5,fill:fill==='#e6dfc4'?'#0b110f':fill,stroke:fill==='#e6dfc4'?'#e6dfc4':undefined,'stroke-width':fill==='#e6dfc4'?1.6:undefined}));
    let px=x+8;
    if(px+w>W-4) px=Math.max(4, W-4-w);
    el.appendChild(svg('rect',{x:px,y:y-11,width:w,height:20,rx:10,fill:fill}));
    el.appendChild(svg('text',{x:px+w/2,y:y+3,'text-anchor':'middle',fill:textFill,'font-size':11,'font-weight':700}, text));
  }
  if(last.ndx!=null){
    addEndPill(ndx, xOf(hist.length-1), ly(last.ndx), 62, '#74c6e2', fmt(last.ndx,0), '#0b110f');
  }

  // Score chart
  const pad2={l:64,r:70,t:10,b:36};
  shades(sc, pad2.t, H2-pad2.b);
  const yS=v=>pad2.t+(H2-pad2.t-pad2.b)*(1-v/100);
  [0,20,50,80,100].forEach(v=>{
    sc.appendChild(svg('line',{x1:pad2.l,x2:W-pad2.r,y1:yS(v),y2:yS(v),stroke:'rgba(255,255,255,.06)'}));
    sc.appendChild(svg('text',{x:pad2.l-8,y:yS(v)+4,'text-anchor':'end'}, String(v)));
  });
  sc.appendChild(svg('text',{x:pad2.l,y:8,fill:'#8c968d','font-size':11}, 'Pipo Score 0–100'));
  // dashed 20
  sc.appendChild(svg('line',{x1:pad2.l,x2:W-pad2.r,y1:yS(20),y2:yS(20),stroke:'#e07a28',
    'stroke-dasharray':'5 4','stroke-width':1.3}));
  sc.appendChild(svg('text',{x:pad2.l-8,y:yS(20)+4,'text-anchor':'end',fill:'#e07a28','font-weight':700}, '20'));
  // sin fondeo dashed if checkbox on
  if(withF){
    let d0='';
    hist.forEach((p,i)=>{ if(p.score_sin_fondeo==null) return; d0+=(d0?' L':'M')+` ${xOf(i).toFixed(2)} ${yS(p.score_sin_fondeo).toFixed(2)}`; });
    sc.appendChild(svg('path',{d:d0,fill:'none',stroke:'#e6dfc4','stroke-width':1.1,'stroke-dasharray':'4 4',opacity:.55}));
  }
  let ds='';
  hist.forEach((p,i)=>{ const v=scoreAt(p); if(v==null) return; ds+=(ds?' L':'M')+` ${xOf(i).toFixed(2)} ${yS(v).toFixed(2)}`; });
  sc.appendChild(svg('path',{d:ds,fill:'none',stroke:'#e6dfc4','stroke-width':1.8,'stroke-linejoin':'round'}));
  // last score pill
  const ls=scoreAt(last);
  if(ls!=null){
    const y=yS(ls), x=xOf(hist.length-1);
    sc.appendChild(svg('circle',{cx:x,cy:y,r:4,fill:'#0b110f',stroke:'#e6dfc4','stroke-width':1.6}));
    const w=48;
    let px=x+8;
    if(px+w>W-4) px=Math.max(4, W-4-w);
    sc.appendChild(svg('rect',{x:px,y:y-11,width:w,height:20,rx:10,fill:'#e6dfc4'}));
    sc.appendChild(svg('text',{x:px+w/2,y:y+3,'text-anchor':'middle',fill:'#0b110f','font-size':11,'font-weight':700}, fmt(ls,1)));
  }
  // eje años
  const years={};
  hist.forEach((p,i)=>{ const y=p.fecha.slice(0,4); if(years[y]==null) years[y]=i; });
  Object.entries(years).forEach(([y,i])=>{
    if(i===0) return;
    sc.appendChild(svg('text',{x:xOf(i),y:H2-12,'text-anchor':'middle'}, y));
  });
  // hitos — cajas clampadas dentro del viewBox; textos más cortos en móvil
  const narrow=(typeof window!=='undefined' && window.innerWidth<=560);
  (L.hitos||[]).forEach((h,hi)=>{
    const i=hist.findIndex(p=>p.fecha>=h.fecha);
    if(i<0) return;
    const v=scoreAt(hist[i]); if(v==null) return;
    const x=xOf(i), y=yS(v);
    sc.appendChild(svg('circle',{cx:x,cy:y,r:3.2,fill:'#0b110f',stroke:'#e6dfc4','stroke-width':1.2}));
    let label=h.etiqueta||'';
    if(narrow){
      label=label.replace(/Pipo Score /g,'').replace(/el más profundo desde /g,'piso post-');
    }
    const tw=Math.min(narrow?150:196, Math.ceil((narrow?6.2:6.8)*label.length+12));
    const th=18;
    const isLast=hi===(L.hitos.length-1);
    const low=v<25;
    const minX=4, maxX=W-4, minY=pad2.t+2, maxY=H2-pad2.b-4;
    let dy=low?(isLast?-20:-40-(hi%2)*18):(isLast?-22:-28);
    let by=y+dy;
    if(by-13<minY) by=minY+13;
    if(by+5>maxY) by=maxY-5;
    let left=isLast || x>820 || (x+10+tw>maxX);
    let bx=left?x-10-tw:x+10;
    if(bx<minX){ bx=minX; left=false; if(x+10+tw<=maxX) bx=x+10; }
    if(bx+tw>maxX){ bx=maxX-tw; left=true; }
    sc.appendChild(svg('rect',{x:bx,y:by-13,width:tw,height:th,rx:4,fill:'#0c1412',stroke:'rgba(255,255,255,.15)'}));
    const textX=left?bx+tw-6:bx+6;
    sc.appendChild(svg('text',{x:textX,y:by,'text-anchor':left?'end':'start',fill:'#e6dfc4','font-size':narrow?9:10}, label));
  });

  // hover sincronizado
  const tip=$('#chartTip');
  function idxFromEvent(ev, svgEl){
    const r=svgEl.getBoundingClientRect();
    const x=(ev.clientX-r.left)/r.width*W;
    let best=0, bd=1e9;
    xs.forEach((xx,i)=>{ const d=Math.abs(xx-x); if(d<bd){bd=d;best=i;} });
    return best;
  }
  function onMove(ev, svgEl){
    const i=idxFromEvent(ev, svgEl);
    const p=hist[i];
    // vertical lines
    [ndx,sc].forEach(el=>{
      let v=el.querySelector('.hoverline');
      if(!v){ v=svg('line',{class:'hoverline',y1:0,y2:999,stroke:'#fff','stroke-width':1,opacity:.25}); el.appendChild(v); }
      v.setAttribute('x1',xOf(i)); v.setAttribute('x2',xOf(i));
    });
    const r=svgEl.getBoundingClientRect(), wrap=$('#charts').getBoundingClientRect();
    tip.hidden=false;
    tip.innerHTML=`<b>${p.fecha}</b><br>Pipo Score ${fmt(scoreAt(p),1)} · sin fondeo ${fmt(p.score_sin_fondeo,1)}<br>Nasdaq-100 ${fmt(p.ndx,0)}`;
    let left=ev.clientX-wrap.left+12, top=ev.clientY-wrap.top+12;
    if(left>wrap.width-220) left-=230;
    tip.style.left=left+'px'; tip.style.top=top+'px';
  }
  function onLeave(){ tip.hidden=true; [ndx,sc].forEach(el=>{ const v=el.querySelector('.hoverline'); if(v) v.remove(); }); }
  [ndx,sc].forEach(el=>{
    el.onmousemove=e=>onMove(e,el);
    el.onmouseleave=onLeave;
  });
}

/* ---------- Vista 3 ---------- */
function renderSliders(){
  const box=$('#sliders');
  const grupos=['liquidez','estres'];
  let html='';
  grupos.forEach(g=>{
    html+=`<div class="grp"><p class="grp-h">${GRP[g].t} <small>${GRP[g].s}</small></p>`;
    META.filter(m=>m.grupo===g).forEach(m=>{
      const src=L.entradas.find(e=>e.id===m.id)||{};
      const st=state.entradas[m.id];
      const off=!st.activo;
      html+=`<div class="slider-row ${off?'off':''}" data-id="${m.id}">
        <div class="lab">${src.nombre||m.id}<small>${src.detalle||''}</small></div>
        <div class="val" id="val-${m.id}">${st.activo&&st.z!=null?pm(st.z,2):'sin dato'}</div>
        <input type="range" min="-3.5" max="3.5" step="0.01" value="${st.z??0}" ${st.activo?'':'disabled'} data-id="${m.id}">
        ${(src.modo==='manual'||!src.activo||src.z==null)?`<label class="tog"><input type="checkbox" data-tog="${m.id}" ${st.activo?'checked':''}> Incluir en el promedio (manual)</label>`:''}
      </div>`;
    });
    html+='</div>';
  });
  // fondeo
  html+=`<div class="grp"><p class="grp-h">${GRP.fondeo.t} <small>${GRP.fondeo.s}</small></p>`;
  html+=`<div class="slider-row">
    <div class="lab">SOFR − IORB<small>Sobre 0 suma a la sequía</small></div>
    <div class="val" id="val-sofr">${pm(state.sofr_iorb_pb,1)} pb</div>
    <input type="range" min="-20" max="40" step="0.1" value="${state.sofr_iorb_pb??0}" data-f="sofr">
  </div>`;
  html+=`<div class="slider-row">
    <div class="lab">Reservas bancarias en la Fed<small>Bajo el umbral “ample” (3,00 T) suma a la sequía</small></div>
    <div class="val" id="val-res">$${fmt(state.reservas_t,2)}T</div>
    <input type="range" min="2" max="4.5" step="0.01" value="${state.reservas_t??3}" data-f="res">
  </div></div>`;
  box.innerHTML=html;
  box.oninput=onSlider;
  box.onchange=onSlider;
}
function onSlider(ev){
  const t=ev.target;
  if(t.dataset.tog){
    const id=t.dataset.tog;
    state.entradas[id].activo=t.checked;
    if(t.checked && state.entradas[id].z==null) state.entradas[id].z=0;
    renderAll(); return;
  }
  if(t.dataset.id){
    const id=t.dataset.id;
    state.entradas[id].z=+t.value;
    state.entradas[id].activo=true;
    $(`#val-${id}`).textContent=pm(state.entradas[id].z,2);
  } else if(t.dataset.f==='sofr'){
    state.sofr_iorb_pb=+t.value;
    $('#val-sofr').textContent=pm(state.sofr_iorb_pb,1)+' pb';
  } else if(t.dataset.f==='res'){
    state.reservas_t=+t.value;
    $('#val-res').textContent='$'+fmt(state.reservas_t,2)+'T';
  }
  const out=evalState(state);
  renderV1(out); renderAportes(out); renderEscenarios(out);
}

function renderEscenarios(out){
  const box=$('#escenarios');
  const list=L.escenarios||[];
  box.innerHTML=list.map((e,i)=>{
    // recompute live for Hoy; others keep stored score but we also recompute from their z
    const zmap=e.z||{};
    const signed=META.map(m=>zmap[m.id]==null?null:m.signo*zmap[m.id]);
    const ev=e.id==='hoy'||e.nombre==='Hoy'?out:calcular(signed, e.sofr_iorb_pb, e.reservas_t);
    const sc=r1(ev.score);
    const on=state.escenario===e.nombre || state.escenario===e.id;
    return `<div class="esc ${on?'on':''}" data-i="${i}">
      <div class="row"><b>${e.nombre}</b><span class="sc">→ ${fmt(sc,0)}</span></div>
      <p>${e.descripcion||''}${e.nota?' · '+e.nota:''}</p>
    </div>`;
  }).join('');
  box.onclick=ev=>{
    const n=ev.target.closest('.esc'); if(!n) return;
    const e=list[+n.dataset.i];
    state.escenario=e.nombre;
    META.forEach(m=>{
      const z=e.z?e.z[m.id]:null;
      state.entradas[m.id]={z:z, activo:z!=null};
    });
    state.sofr_iorb_pb=e.sofr_iorb_pb;
    state.reservas_t=e.reservas_t;
    renderAll();
  };
}

function renderAportes(out){
  const rows=[];
  META.forEach((m,i)=>{
    const ap=out.aportes[i];
    if(ap==null) return;
    const src=L.entradas.find(e=>e.id===m.id)||{};
    rows.push({nombre:src.nombre||m.id, ap, id:m.id});
  });
  if(out.aporte_sofr) rows.push({nombre:'SOFR−IORB sobre 0', ap:out.aporte_sofr, id:'sofr'});
  if(out.aporte_reservas) rows.push({nombre:'Colchón de reservas', ap:out.aporte_reservas, id:'res'});
  rows.sort((a,b)=>a.ap-b.ap);
  const max=Math.max(0.15, ...rows.map(r=>Math.abs(r.ap)));
  $('#aportes').innerHTML=rows.map(r=>{
    const pct=Math.min(50, Math.abs(r.ap)/max*50);
    const cls=r.ap<0?'neg':'pos';
    const style=r.ap<0?`width:${pct}%;right:50%`:`width:${pct}%;left:50%`;
    return `<div class="ap"><div class="n">${r.nombre}</div>
      <div class="tr"><i class="${cls}" style="${style}"></i></div>
      <div class="v ${cls}">${pm(r2(r.ap),2)}</div></div>`;
  }).join('');
  $('#aportes-foot').textContent=`Aporte de cada variable al exponente de Φ (cada una pesa 1/${out.n} mientras falten variables). Rojo resta, verde suma.`;
}

function renderAll(){
  const out=evalState(state);
  renderV1(out);
  renderV2();
  renderSliders();
  renderEscenarios(out);
  renderAportes(out);
}

cargar(d=>{
  L=d.liquidez;
  if(!L){ $('#act').textContent='No hay datos de liquidez en mercado.json.'; return; }
  const act=$('#act');
  const extra=` · Liquidez ${fmt(L.score,1)} (${L.regimen||'–'}) · ${L.fecha}`;
  if(act && !/Liquidez/.test(act.textContent)) act.textContent+=extra;
  state={
    entradas:{},
    sofr_iorb_pb:L.fondeo&&L.fondeo.sofr_iorb_pb,
    reservas_t:L.fondeo&&L.fondeo.reservas_t,
    escenario:'Hoy'
  };
  (L.entradas||[]).forEach(e=>{ state.entradas[e.id]={z:e.z, activo:!!e.activo}; });
  META.forEach(m=>{ if(!state.entradas[m.id]) state.entradas[m.id]={z:null,activo:false}; });
  $('#conFondeo').onchange=()=>renderV2();
  renderAll();
});
})();
