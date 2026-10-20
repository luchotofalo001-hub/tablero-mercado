"""Tablero de Mercado: genera site/data/mercado.json con datos gratis.
Universo: CEDEARs (BYMA) mapeados a tickers de EE.UU. + ADRs argentinos. Benchmark: SPY.
Fuentes: BYMA open data, Nasdaq (screener y calendarios), Yahoo Finance (yfinance)."""
import json, os, sys, datetime as dt, requests, pandas as pd, numpy as np, yfinance as yf
import warnings; warnings.filterwarnings("ignore")
OUT, HIST = "site/data/", "data/historial/"
os.makedirs(OUT, exist_ok=True); os.makedirs(HIST, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json"}
def jload(p, d):
    try: return json.load(open(p))
    except Exception: return d
def jsave(p, o): json.dump(o, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
def r(x, n=2):
    try: return None if x is None or not np.isfinite(float(x)) else round(float(x), n)
    except Exception: return None
log = lambda *a: print(*a, file=sys.stderr)

ETFS = {"XLK":"Tecnología","XLE":"Energía","XLV":"Salud","XLP":"Consumo básico","XLF":"Financiero","XLU":"Servicios públicos","XLI":"Industria",
        "XLY":"Consumo discrecional","XLB":"Materiales","XLRE":"Inmobiliario","XLC":"Comunicaciones","SMH":"Semiconductores","IBB":"Biotecnología",
        "XBI":"Biotech chicas","IGV":"Software","KRE":"Bancos regionales","ITA":"Defensa","XOP":"Petroleras","GDX":"Mineras de oro","XHB":"Construcción"}
SECES = {"Technology":"Tecnología","Telecommunications":"Comunicaciones","Health Care":"Salud","Finance":"Financiero","Real Estate":"Inmobiliario",
         "Consumer Discretionary":"Consumo discrecional","Consumer Staples":"Consumo básico","Industrials":"Industria","Basic Materials":"Materiales",
         "Energy":"Energía","Utilities":"Servicios públicos","Miscellaneous":"Otros"}
ADRS = ["YPF","GGAL","BMA","PAM","TGS","CEPU","LOMA","SUPV","CRESY","IRS","EDN","BBAR","TEO","VIST","MELI","GLOB","DESP","BIOX","CAAP","TX"]
ALIAS = {"BRKB":"BRK-B","DISN":"DIS","NOKA":"NOK","BBV":"BBVA","AKO.B":"AKO-B","FMX.B":"FMX","GOGL":"GOOGL"}
TAPE = ["SPY","QQQ","AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","MELI","YPF","GGAL","VIST","BMA","PAM"]

# ---------- Universo ----------
nq = requests.get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true", headers=UA, timeout=60).json()["data"]["rows"]
NQ = {x["symbol"].replace("/", "-").strip(): x for x in nq}
cache = jload(HIST + "cedears.json", [])
try:
    by = requests.post("https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/cedears", headers={**UA, "Content-Type": "application/json"},
                       json={"excludeZeroPxAndQty": False, "T2": True, "T1": False, "T0": False}, timeout=40, verify=False).json()
    syms = sorted({ALIAS.get(x["symbol"], x["symbol"]) for x in by})
    ced = [s for s in syms if s in NQ]
    if len(ced) > 150: jsave(HIST + "cedears.json", ced); cache = ced
except Exception as ex: log("byma", ex)
if not cache: sys.exit("sin lista de CEDEARs")
univ = sorted(set(cache) | {a for a in ADRS if a in NQ})
log("universo", len(univ))
def meta(t):
    x = NQ.get(t, {})
    try: cap = float(x.get("marketCap") or 0)
    except Exception: cap = 0
    return {"n": (x.get("name") or t).replace(" Common Stock", "").replace(" American Depositary Shares", "").split(" Class ")[0][:40],
            "sec": SECES.get(x.get("sector") or "", "Otros"), "ind": x.get("industry") or "", "cap": cap, "adr": t in ADRS}
M = {t: meta(t) for t in univ}

# ---------- Precios ----------
raw = yf.download(univ + list(ETFS) + ["SPY", "QQQ"], period="2y", interval="1d", auto_adjust=True, progress=False, threads=True, group_by="column")
C, H, L, V = (raw[k].ffill(limit=3) for k in ("Close", "High", "Low", "Volume"))
C = C.dropna(how="all"); H, L, V = H.loc[C.index], L.loc[C.index], V.loc[C.index]
univ = [t for t in univ if t in C and C[t].notna().sum() > 60]
spy = C["SPY"]
ema = lambda s, n: s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    d = s.diff(); up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))
S = C[univ]
# RS (0-99): percentil del rendimiento ponderado 3/6/9/12m relativo al SPY
def wperf(X):
    num = 0; den = 0
    for n, w in ((63, .4), (126, .2), (189, .2), (252, .2)):
        v = X / X.shift(n); ok = v.notna()
        num = num + v.fillna(0) * w; den = den + ok * w
    return num / den.replace(0, np.nan)
REL = wperf(S).div(wperf(spy), axis=0)
RS = REL.rank(axis=1, pct=True) * 99
RSI = rsi(S)
SMA50, SMA200, SMA20 = S.rolling(50).mean(), S.rolling(200).mean(), S.rolling(20).mean()
E200 = ema(S, 200)
VAVG = V[univ].rolling(20).mean().shift(1)
BW = 4 * S.rolling(20).std() / SMA20

def clip(x, a=0, b=100): return float(min(b, max(a, x)))
def rsi_b(v):  # B: mejor entre 50 y 70
    return 100 if 50 <= v <= 70 else clip(100 - (50 - v) * 4) if v < 50 else clip(100 - (v - 70) * 5)
def rsi_c(v):  # C: neutral 40-65 ideal, castiga >75
    return 100 if 40 <= v <= 65 else clip(100 - (v - 65) * 10) if v > 65 else clip(100 - (40 - v) * 6)

def calcular(k):
    """Métricas y puntaje usando datos hasta la fila k (incluida)."""
    out = {}
    for t in univ:
        c = S[t].iloc[:k + 1].dropna()
        if len(c) < 60: continue
        p = c.iloc[-1]; s50 = SMA50[t].iloc[k]; s200 = SMA200[t].iloc[k]; s200p = SMA200[t].iloc[k - 20]
        h, l, v = H[t].iloc[:k + 1].loc[c.index], L[t].iloc[:k + 1].loc[c.index], V[t].iloc[:k + 1].loc[c.index].fillna(0)
        w = c.tail(252); lo = int(np.argmin(L[t].loc[w.index].values)); seg = w.index[lo:]
        tp = (h + l + c) / 3; av = (tp.loc[seg] * v.loc[seg]).sum() / max(v.loc[seg].sum(), 1)
        wk = c.resample("W-FRI").last().rolling(10).mean().iloc[-1]
        # A Tendencia
        A = 25 * (p > s200) + 20 * (p > s50) + 15 * (s200 > s200p) + 15 * (p > av) + 15 * (p > wk) + 10 * (s50 > s200)
        ext = (p / s200 - 1) * 100 if s200 == s200 else 0
        if ext > 40: A -= min(30, (ext - 40) * 1.5)
        A = clip(A) if s200 == s200 else clip(A * .8)
        # B Fuerza relativa
        rs = RS[t].iloc[k]; rsp = RS[t].iloc[k - 5]; drs = rs - rsp; ri = RSI[t].iloc[k]
        B = .6 * rs / .99 + .25 * clip(50 + drs * 2.5) + .15 * rsi_b(ri) if rs == rs else 0
        # C Contracción
        bw = BW[t].iloc[max(0, k - 251):k + 1].dropna(); bwp = (bw < bw.iloc[-1]).mean() if len(bw) > 20 else .5
        Cc = 60 * (1 - bwp) + .4 * rsi_c(ri)
        # D Setup (VCP heurístico)
        x = c.tail(60); ds = []
        for part in (x.iloc[:20], x.iloc[20:40], x.iloc[40:]):
            ds.append((part.max() - part.min()) / part.max())
        contr = (ds[0] > ds[1]) + (ds[1] > ds[2]); piv = x.max(); near = clip(100 - (1 - p / piv) * 100 * 10)
        dry = v.tail(10).mean() < v.tail(50).mean() * .85
        D = 20 * contr + 30 * dry + .3 * near
        score = .3 * A + .3 * B + .2 * Cc + .2 * D
        out[t] = dict(p=p, rs=rs, drs=drs, rsi=ri, A=A, B=B, C=Cc, D=D, s=score, s50=s50, s200=s200, av=av,
                      pivot=piv, vcp=bool(contr == 2 and dry))
    return pd.DataFrame(out).T

EXCL = jload("data/excluidos.json", {})
N = len(C) - 1
hoy = calcular(N).sort_values("s", ascending=False)

# ---------- Historial persistente ----------
fecha = C.index[-1].strftime("%Y-%m-%d")
sc = jload(HIST + "scores.json", {}); rsh = jload(HIST + "rs.json", {})
prev_dates = sorted(d for d in sc if d < fecha); prev = sc[prev_dates[-1]] if prev_dates else {}
sc[fecha] = {t: r(v, 1) for t, v in hoy.s.items()}; rsh[fecha] = {t: r(v, 0) for t, v in hoy.rs.items()}
for f, o in ((HIST + "scores.json", sc), (HIST + "rs.json", rsh)):
    jsave(f, {d: o[d] for d in sorted(o)[-180:]})

# Top 10 semanal: elegido al cierre de cada viernes, se mide hasta el viernes siguiente (o hasta hoy)
fri = [i for i in range(len(C) - 1) if C.index[i].weekday() == 4 or (i + 1 < len(C) and C.index[i + 1].isocalendar()[1] != C.index[i].isocalendar()[1])]
top = jload(HIST + "top10.json", {})
for i in fri[-9:]:
    d = C.index[i].strftime("%Y-%m-%d")
    if d not in top and i > 260:
        dfk = calcular(i).sort_values("s", ascending=False); dfk = dfk[~dfk.index.isin(list(EXCL))].head(10)
        top[d] = {"tickers": list(dfk.index), "precios": [r(x) for x in dfk.p], "spy": r(spy.iloc[i])}
top = {d: top[d] for d in sorted(top)[-30:]}; jsave(HIST + "top10.json", top)
def res_semana(d, hasta):
    o = top[d]; j = C.index.get_loc(pd.Timestamp(hasta)) if hasta else N
    sp = (spy.iloc[j] / o["spy"] - 1) * 100
    rets = [(C[t].iloc[j] / p0 - 1) * 100 if t in C and p0 else None for t, p0 in zip(o["tickers"], o["precios"])]
    return {"elegido": d, "hasta": C.index[j].strftime("%Y-%m-%d"), "spy": r(sp),
            "lista": [{"t": t, "ret": r(x)} for t, x in zip(o["tickers"], rets)],
            "promedio": r(np.nanmean([x for x in rets if x is not None])), "ganadas": sum(1 for x in rets if x is not None and x > sp)}
td = sorted(top)
semanas = [res_semana(td[i], td[i + 1]) for i in range(len(td) - 1)]
top10sem = {"ultima": semanas[-1] if semanas else None, "en_curso": res_semana(td[-1], None) if td else None,
            "historial": [{"elegido": s["elegido"], "prom": s["promedio"], "spy": s["spy"], "ganadas": s["ganadas"]} for s in semanas],
            "tasa_acierto": r(100 * sum(s["ganadas"] for s in semanas) / max(1, 10 * len(semanas)), 0)}

# ---------- Filas por acción ----------
ytd0 = S[S.index.year == S.index[-1].year].iloc[0] if (S.index.year == S.index[-1].year).any() else S.iloc[0]
acc = []
for t, x in hoy.iterrows():
    c = S[t]; p = c.iloc[-1]; pp = c.iloc[-2]; vr = V[t].iloc[-1] / VAVG[t].iloc[-1] if VAVG[t].iloc[-1] else np.nan
    lo3 = L[t].iloc[-3:].min(); e2 = E200[t]
    rebote = bool(x.s50 > x.s200 and SMA200[t].iloc[-1] > SMA200[t].iloc[-21] and lo3 <= e2.iloc[-1] * 1.005 and p > e2.iloc[-1])
    chg = (p / pp - 1) * 100
    cc = c.dropna(); s200 = cc.tail(200).mean() if len(cc) >= 200 else np.nan
    pil = {k: r(x[k], 0) for k in "ABCD"}
    acc.append({"t": t, **{k: M[t][k] for k in ("n", "sec", "ind", "adr")}, "cap": r(M[t]["cap"] / 1e9, 1),
        "p": r(p), "chg": r(chg), "vol_rel": r(vr), "rs": r(x.rs, 0), "drs": r(x.drs, 0), "rsi": r(x.rsi, 0),
        **pil, "s": r(.3 * pil["A"] + .3 * pil["B"] + .2 * pil["C"] + .2 * pil["D"], 1), "excluido": EXCL.get(t), "s_prev": prev.get(t),
        "dist50": r((p / x.s50 - 1) * 100, 1), "dist200": r((p / s200 - 1) * 100, 1) if s200 == s200 else None, "volat": r(c.pct_change().tail(20).std() * np.sqrt(252) * 100, 0),
        "ytd": r((p / ytd0[t] - 1) * 100, 1), "r1s": r((p / c.iloc[-6] - 1) * 100, 1), "r1m": r((p / c.iloc[-22] - 1) * 100, 1),
        "corto": "alcista" if p > SMA20[t].iloc[-1] and p > x.s50 else "bajista" if p < SMA20[t].iloc[-1] and p < x.s50 else "mixta",
        "largo": "alcista" if p > x.s200 and SMA200[t].iloc[-1] > SMA200[t].iloc[-21] else "bajista" if p < x.s200 else "mixta",
        "vcp": x.vcp, "pivot": r(x.pivot), "rebote200": rebote, "pivot_hoy": bool(abs(chg) > 4 and vr > 2),
        "rs_hist": [r(v, 0) for v in RS[t].iloc[-22:]]})
acc.sort(key=lambda a: -(a["s"] or 0))
A_ = {a["t"]: a for a in acc}

# ---------- Termómetro ----------
last = S.iloc[-1]; ok = last.notna()
n_ = len(acc); a200 = sum(1 for a in acc if (a["dist200"] or 0) > 0); a50 = sum(1 for a in acc if (a["dist50"] or 0) > 0)
volu = sum(1 for a in acc if (a["vol_rel"] or 0) > 1.5); sobre = sum(1 for a in acc if (a["rsi"] or 0) > 70)
amp = sum(1 for a in acc if (a["rs"] or 0) > 70 and (a["dist50"] or -1) > 0)
spy200 = spy.rolling(200).mean().iloc[-1]; spy1m = (spy.iloc[-1] / spy.iloc[-22] - 1) * 100
temp = .4 * a200 / n_ * 100 + .3 * a50 / n_ * 100 + .15 * (100 if spy.iloc[-1] > spy200 else 0) + .15 * clip(50 + spy1m * 5)
consejo = ("Mercado fuerte: buen momento para operar con normalidad." if temp >= 70 else "Mercado mixto: ser selectivo, solo las acciones más fuertes." if temp >= 50
           else "Mercado flojo: escenarios óptimos solamente, posiciones chicas." if temp >= 30 else "Mercado débil: priorizar liquidez y cuidar el capital.")
p200 = ((S > SMA200) & S.notna()).sum(axis=1) / S.notna().sum(axis=1) * 100
p50 = ((S > SMA50) & S.notna()).sum(axis=1) / S.notna().sum(axis=1) * 100
hh = pd.DataFrame({"a": p200, "b": p50}).iloc[220:].tail(250)
term = {"total": n_, "sobre_sma200": a200, "sobre_sma50": a50, "vol_inusual": volu, "rsi_70": sobre, "amplitud_rs70": amp, "amplitud_rs70_bruto": sum(1 for a in acc if (a["rs"] or 0) > 70),
        "pct_sma200": r(a200 / n_ * 100, 1), "pct_sma50": r(a50 / n_ * 100, 1), "indice": r(temp, 0), "consejo": consejo,
        "historia": [[i.strftime("%Y-%m-%d"), r(a, 1), r(b, 1)] for i, a, b in zip(hh.index, hh.a, hh.b)]}

# ---------- Rotación (JdK-like semanal, 30 semanas para el reproductor) ----------
wk = C.resample("W-FRI").last()
rot = {}
for t in ETFS:
    if t not in wk: continue
    rs_ = 100 * wk[t] / wk["SPY"]; ratio = 100 + ((rs_ / rs_.rolling(10).mean()) - 1).ewm(span=4).mean() * 100
    mom = 100 + ((ratio / ratio.shift(1)) - 1).ewm(span=4).mean() * 500
    d = pd.DataFrame({"x": ratio, "y": mom}).dropna().tail(30)
    lid = [a["t"] for a in acc if a["sec"] == ETFS[t]][:8]
    rot[t] = {"nombre": ETFS[t], "puntos": [[r(a), r(b)] for a, b in zip(d.x, d.y)], "lideres": lid, "zona": ("Liderando" if d.y.iloc[-1] >= 100 else "Debilitándose") if d.x.iloc[-1] >= 100 else ("Mejorando" if d.y.iloc[-1] >= 100 else "Rezagado")}
semanas_rot = [i.strftime("%d/%m") for i in d.index]

# ---------- Sectores ----------
sect = {}
for a in acc:
    s = sect.setdefault(a["sec"], {"r1s": [], "r1m": [], "vol": [], "chg": [], "n": 0})
    for k, kk in (("r1s", "r1s"), ("r1m", "r1m"), ("vol", "vol_rel"), ("chg", "chg")):
        if a[kk] is not None: s[k].append(a[kk])
    s["n"] += 1
sectores = sorted([{"sec": k, "n": v["n"], "semana": r(np.median(v["r1s"]), 1), "mes": r(np.median(v["r1m"]), 1),
                    "hoy": r(np.median(v["chg"]), 2), "vol_rel": r(np.mean(v["vol"]), 2)} for k, v in sect.items()], key=lambda x: -(x["mes"] or 0))

# ---------- Cabecera y cinta ----------
cab = {}
for t in ["SPY", "QQQ"]:
    c = C[t].dropna(); p, pv = c.iloc[-1], c.iloc[-2]; e2 = ema(c, 200).iloc[-1]
    cab[t] = {"p": r(p), "chg": r((p / pv - 1) * 100), "ema200": r(e2), "vsEma": r((p / e2 - 1) * 100)}
cinta = [{"t": t, "chg": r((C[t].iloc[-1] / C[t].iloc[-2] - 1) * 100)} for t in TAPE if t in C]

# ---------- Eventos (Nasdaq) ----------
hoyd = dt.date.today(); lunes = hoyd - dt.timedelta(days=hoyd.weekday()); U = set(univ)
bal, macro, prox = [], [], []
KEY = {"CPI": "Inflación (CPI)", "Consumer Price Index": "Inflación (CPI)", "FOMC": "Fed (FOMC)", "Fed Interest Rate": "Fed: tasa de interés",
       "Nonfarm Payrolls": "Empleo (NFP)", "PCE": "Inflación PCE", "GDP": "PBI", "Unemployment Rate": "Desempleo", "PPI": "Inflación mayorista (PPI)"}
HORA = {"time-pre-market": "antes de abrir", "time-after-hours": "después del cierre"}
dias = sorted({lunes + dt.timedelta(days=i) for i in range(5)} | {hoyd + dt.timedelta(days=i) for i in range(29)})
for d0 in dias:
    d = d0.isoformat()
    try:
        rows = (requests.get(f"https://api.nasdaq.com/api/calendar/earnings?date={d}", headers=UA, timeout=20).json().get("data") or {}).get("rows") or []
        for x in rows:
            t = x["symbol"].replace(".", "-")
            if t in U:
                e = {"fecha": d, "t": t, "n": M[t]["n"], "cap": M[t]["cap"], "hora": HORA.get(x.get("time"), "")}
                if lunes <= d0 <= lunes + dt.timedelta(days=4): bal.append(e)
                if hoyd <= d0 <= hoyd + dt.timedelta(days=28): prox.append(e)
    except Exception as ex: log("earn", d, ex)
    if lunes <= d0 <= lunes + dt.timedelta(days=4):
        try:
            for x in (requests.get(f"https://api.nasdaq.com/api/calendar/economicevents?date={d}", headers=UA, timeout=20).json().get("data") or {}).get("rows") or []:
                if x.get("country") != "United States": continue
                for k, v in KEY.items():
                    if k.lower() in x["eventName"].lower(): macro.append({"fecha": d, "hora": x.get("gmt", ""), "ev": v, "orig": x["eventName"]}); break
        except Exception as ex: log("eco", d, ex)
bal = sorted(sorted(bal, key=lambda x: -x["cap"])[:25], key=lambda x: x["fecha"])
prox = sorted(prox, key=lambda x: (x["fecha"], -x["cap"]))
for e in prox:
    e["s"] = A_[e["t"]]["s"]; A_[e["t"]].setdefault("earnings", e["fecha"])
for a in acc: a.setdefault("earnings", None)

# ---------- Listas ----------
srt = lambda k, rev=True, n=10, f=lambda a: True: [a["t"] for a in sorted([a for a in acc if a[k] is not None and f(a)], key=lambda a: a[k], reverse=rev)[:n]]
dump = {
    "actualizado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "fecha_datos": fecha, "benchmark": "SPY",
    "universo": {"total": len(acc), "fuente": "CEDEARs de BYMA + ADRs argentinos"},
    "cabecera": cab, "cinta": cinta, "termometro": term,
    "animo": "malo" if (cab["SPY"]["chg"] or 0) < -1.5 or term["pct_sma200"] < 30 else "bueno",
    "podio": [a["t"] for a in acc if not a["excluido"]][:3], "excluidos": EXCL,
    "cartera_del_dia": {"suben": srt("chg"), "bajan": srt("chg", False), "rsi_sobrecompra": srt("rsi", f=lambda a: a["rsi"] > 70),
                         "rsi_sobreventa": srt("rsi", False, f=lambda a: a["rsi"] < 30)},
    "pivots_hoy": [a["t"] for a in acc if a["pivot_hoy"]], "rebotes_ema200": [a["t"] for a in acc if a["rebote200"]],
    "vol_inusual": srt("vol_rel", n=15, f=lambda a: a["vol_rel"] > 1.5),
    "rotacion": rot, "rotacion_semanas": semanas_rot, "sectores": sectores, "top10_semana": top10sem,
    "proximos_earnings": prox, "eventos": {"semana": lunes.isoformat(), "balances": bal, "macro": macro},
    "acciones": acc, "ranking": acc[:100],
}
jsave(OUT + "mercado.json", dump)
print("ok", len(acc), term["indice"], len(prox), len(semanas), "pivots", len(dump["pivots_hoy"]), "rebotes", len(dump["rebotes_ema200"]))
