const $=s=>document.querySelector(s),f=(n,d=2)=>n==null?'–':n.toLocaleString('es-AR',{minimumFractionDigits:d,maximumFractionDigits:d});
const SEC={XLK:'Tecnología',XLE:'Energía',XLV:'Salud',XLP:'Consumo básico',XLF:'Financiero',XLU:'Servicios públicos',XLI:'Industria',XLY:'Consumo discrecional',XLB:'Materiales',XLRE:'Inmobiliario',XLC:'Comunicaciones'};
const COL=['#60a5fa','#f59e0b','#22c55e','#a78bfa','#f472b6','#2dd4bf','#fb923c','#e879f9','#facc15','#94a3b8','#38bdf8'];
const r=document.documentElement;if(localStorage.tema==='claro'||(!localStorage.tema&&matchMedia('(prefers-color-scheme: light)').matches))r.classList.add('claro');
$('#tema').onclick=()=>{r.classList.toggle('claro');localStorage.tema=r.classList.contains('claro')?'claro':'oscuro'};
let D;
const sgn=x=>x>=0?'up':'dn',pm=x=>(x>0?'+':'')+f(x)+'%';
function cab(){$('#cab').innerHTML=['SPY','QQQ'].map(t=>{const c=D.cabecera[t];return`<div class="card"><small>${t==='SPY'?'S&P 500 (SPY)':'Nasdaq 100 (QQQ)'}</small><div class="big">US$ ${f(c.p)}</div><div class="${sgn(c.chg)}">${pm(c.chg)} hoy</div><small>${c.vsEma>=0?'Arriba':'Abajo'} de su EMA200 (${pm(c.vsEma)})</small></div>`}).join('')}
function rrg(){const R=D.rotacion,pts=Object.values(R).flatMap(s=>s.cola),dx=Math.max(...pts.map(p=>Math.abs(p[0]-100)),1)*1.15,dy=Math.max(...pts.map(p=>Math.abs(p[1]-100)),1)*1.15;
const X=v=>180+(v-100)/dx*170,Y=v=>180-(v-100)/dy*170;
let s=`<rect x="10" y="10" width="170" height="170" fill="#60a5fa" opacity=".08"/><rect x="180" y="10" width="170" height="170" fill="#22c55e" opacity=".08"/><rect x="10" y="180" width="170" height="170" fill="#ef4444" opacity=".08"/><rect x="180" y="180" width="170" height="170" fill="#f59e0b" opacity=".08"/>
<line x1="180" y1="10" x2="180" y2="350" stroke="var(--bd)"/><line x1="10" y1="180" x2="350" y2="180" stroke="var(--bd)"/>
<text class="q" x="16" y="24">Mejorando</text><text class="q" x="344" y="24" text-anchor="end">Liderando</text><text class="q" x="16" y="344">Rezagado</text><text class="q" x="344" y="344" text-anchor="end">Debilitándose</text>
<text x="180" y="358" text-anchor="middle" opacity=".6">Fuerza relativa →</text>`;
Object.entries(R).forEach(([t,o],i)=>{const c=o.cola,l=c[c.length-1];s+=`<polyline fill="none" stroke="${COL[i]}" stroke-width="1.6" opacity=".7" points="${c.map(p=>X(p[0])+','+Y(p[1])).join(' ')}"/>`+c.slice(0,-1).map(p=>`<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="1.8" fill="${COL[i]}" opacity=".6"/>`).join('')+
`<circle class="dot" data-t="${t}" cx="${X(l[0])}" cy="${Y(l[1])}" r="5" fill="${COL[i]}"/><text x="${X(l[0])+7}" y="${Y(l[1])+3}" pointer-events="none">${t}</text>`});
$('#rrg').innerHTML=s;$('#rrg').onclick=e=>{const t=e.target.dataset.t;if(!t)return;const o=R[t],l=o.cola.at(-1),q=l[0]>=100?(l[1]>=100?'Liderando':'Debilitándose'):(l[1]>=100?'Mejorando':'Rezagado');
$('#lider').innerHTML=`<p><b>${t} · ${o.nombre}</b> — ${q}</p>`+o.lideres.map(x=>{const k=D.ranking.find(z=>z.t===x)||D._todo?.[x];return`<span class="chip">${x}</span>`}).join('')+'<p class="help">Acciones del S&P 500 de este sector con mayor puntaje.</p>'}}
function gauge(el,v,lab){const a=Math.PI*(1-v/100),c=v<30?'var(--bad)':v<60?'var(--wa)':'var(--ok)';
$(el).innerHTML=`<svg viewBox="0 0 120 72"><path d="M10 62A50 50 0 0 1 110 62" fill="none" stroke="var(--bd)" stroke-width="10" stroke-linecap="round"/><path d="M10 62A50 50 0 0 1 ${60+50*Math.cos(a)} ${62-50*Math.sin(a)}" fill="none" stroke="${c}" stroke-width="10" stroke-linecap="round"/><text x="60" y="58" text-anchor="middle" style="font-size:18px;font-weight:700">${f(v,0)}%</text></svg><small>${lab}</small>`}
function hist(){const h=D.termometro.historia,n=h.length,X=i=>10+i/(n-1)*340,Y=v=>110-v;const L=k=>h.map((p,i)=>X(i)+','+Y(p[k])).join(' ');
$('#hist').innerHTML=`<line x1="10" x2="350" y1="${Y(30)}" y2="${Y(30)}" stroke="var(--bad)" stroke-dasharray="3 3" opacity=".6"/><line x1="10" x2="350" y1="${Y(70)}" y2="${Y(70)}" stroke="var(--ok)" stroke-dasharray="3 3" opacity=".6"/><polyline fill="none" stroke="var(--wa)" stroke-width="1.2" points="${L(2)}"/><polyline fill="none" stroke="var(--ac)" stroke-width="2" points="${L(1)}"/><text x="10" y="8" opacity=".6">${h[0][0].slice(0,7)} → ${h[n-1][0].slice(0,7)}</text>`}
function tabla(){const q=$('#q').value.trim().toLowerCase(),s=$('#fs').value;
$('#tb').innerHTML=D.ranking.map((x,i)=>[x,i+1]).filter(([x])=>(!s||x.etf===s)&&(!q||x.t.toLowerCase().includes(q)||x.n.toLowerCase().includes(q))).map(([x,i])=>
`<tr><td>${i}</td><td><b>${x.t}</b><br><small>${x.n}</small></td><td><small>${SEC[x.etf]||''}</small></td><td><b>${f(x.s,0)}</b><span class="bar" style="width:${x.s*.3}px"></span></td><td class="${sgn(x.r6)}">${pm(x.r6)}</td><td>${f(x.dist,1)}%</td></tr>`).join('')||'<tr><td colspan="6">Sin resultados</td></tr>'}
const dia=d=>new Date(d+'T12:00').toLocaleDateString('es-AR',{weekday:'short',day:'numeric'});
function ev(){const E=D.eventos;$('#mac').innerHTML=E.macro.map(m=>`<li><span>${m.ev}<br><small>${m.orig}</small></span><span>${dia(m.fecha)} ${m.hora} (hora NY)</span></li>`).join('')||'<li>Sin datos clave esta semana</li>';
$('#bal').innerHTML=E.balances.map(b=>`<li><span><b>${b.t}</b> <small>${b.n}</small></span><span>${dia(b.fecha)} ${b.hora}</span></li>`).join('')||'<li>Sin balances grandes</li>'}
fetch('data/mercado.json?'+Date.now()).then(r=>r.json()).then(d=>{D=d;document.body.className=d.animo;
$('#act').textContent='Actualizado: '+new Date(d.actualizado).toLocaleString('es-AR',{timeZone:'America/Argentina/Buenos_Aires'})+' (hora Argentina)';
cab();rrg();gauge('#g200',d.termometro.ema200,'arriba de EMA200');gauge('#g50',d.termometro.ema50,'arriba de EMA50');hist();ev();
Object.entries(SEC).forEach(([k,v])=>$('#fs').add(new Option(v,k)));tabla();$('#q').oninput=$('#fs').onchange=tabla}).catch(()=>$('#act').textContent='No se pudieron cargar los datos.');
