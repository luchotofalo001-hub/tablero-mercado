"""Genera site/data/*.json con datos gratis (Yahoo vía yfinance, Wikipedia, Nasdaq)."""
import json, datetime as dt, io, sys, requests, pandas as pd, numpy as np, yfinance as yf
OUT = "site/data/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json"}
SECT = {"XLK":"Tecnología","XLE":"Energía","XLV":"Salud","XLP":"Consumo básico","XLF":"Financiero","XLU":"Servicios públicos",
        "XLI":"Industria","XLY":"Consumo discrecional","XLB":"Materiales","XLRE":"Inmobiliario","XLC":"Comunicaciones"}
GICS = {"Information Technology":"XLK","Energy":"XLE","Health Care":"XLV","Consumer Staples":"XLP","Financials":"XLF","Utilities":"XLU",
        "Industrials":"XLI","Consumer Discretionary":"XLY","Materials":"XLB","Real Estate":"XLRE","Communication Services":"XLC"}
def dump(n, o): json.dump(o, open(OUT+n, "w"), ensure_ascii=False, separators=(",", ":"))
r2 = lambda x: None if x is None or pd.isna(x) else round(float(x), 2)

sp = pd.read_html(io.StringIO(requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=UA, timeout=30).text))[0]
sp["t"] = sp["Symbol"].str.replace(".", "-", regex=False)
meta = {t: (n, GICS.get(g, "")) for t, n, g in zip(sp.t, sp["Security"], sp["GICS Sector"])}
tick = list(meta) + list(SECT) + ["SPY", "QQQ"]
px = yf.download(tick, period="2y", interval="1d", auto_adjust=True, progress=False, threads=True)["Close"].dropna(how="all")
px = px.ffill(limit=3)
spy = px["SPY"]
e = lambda s, n: s.ewm(span=n, adjust=False).mean()

# --- Rotación (JdK-like, semanal) ---
wk = px.resample("W-FRI").last()
rrg = {}
for t in SECT:
    rs = 100 * wk[t] / wk["SPY"]
    rsn = rs.rolling(10).mean()
    ratio = 100 + ((rs / rsn) - 1).ewm(span=4).mean() * 100
    mom = 100 + ((ratio / ratio.shift(1)) - 1).ewm(span=4).mean() * 100 * 5
    d = pd.DataFrame({"x": ratio, "y": mom}).dropna().tail(8)
    rrg[t] = {"nombre": SECT[t], "cola": [[r2(a), r2(b)] for a, b in zip(d.x, d.y)], "fechas": [i.strftime("%d/%m") for i in d.index]}

# --- Termómetro e indicadores por acción ---
stocks = [t for t in meta if t in px.columns]
S = px[stocks]
e20, e50, e200 = e(S, 20), e(S, 50), e(S, 200)
valid = S.notna()
a200 = ((S > e200) & valid).sum(axis=1) / valid.sum(axis=1) * 100
a50 = ((S > e50) & valid).sum(axis=1) / valid.sum(axis=1) * 100
h = pd.DataFrame({"a200": a200, "a50": a50}).iloc[200:].tail(250)
term = {"ema200": r2(a200.iloc[-1]), "ema50": r2(a50.iloc[-1]),
        "historia": [[i.strftime("%Y-%m-%d"), r2(a), r2(b)] for i, a, b in zip(h.index, h.a200, h.a50)]}

# --- Puntaje de fortaleza (0-100) ---
last = S.iloc[-1]
def ret(n): return S.iloc[-1] / S.iloc[-1 - n] - 1
spyr = lambda n: spy.iloc[-1] / spy.iloc[-1 - n] - 1
hi52 = S.tail(252).max()
pct = lambda s: s.rank(pct=True) * 100
tend = ((last > e20.iloc[-1]).astype(int) * 15 + (last > e50.iloc[-1]).astype(int) * 15 + (last > e200.iloc[-1]).astype(int) * 20
        + ((e20.iloc[-1] > e50.iloc[-1]) & (e50.iloc[-1] > e200.iloc[-1])).astype(int) * 50)  # 0-100
mom = pct(0.5 * ret(63) + 0.5 * ret(126))
rsv = pct((ret(126) - spyr(126)) * 0.6 + (ret(63) - spyr(63)) * 0.4)
dist = (last / hi52 - 1) * 100
cerca = (100 + dist * 4).clip(0, 100)  # 0% del máximo=100, -25% o peor=0
score = (0.30 * tend + 0.25 * mom + 0.25 * rsv + 0.20 * cerca).round(1)
df = pd.DataFrame({"score": score, "tend": tend, "mom": mom, "rs": rsv, "dist": dist, "r3": ret(63) * 100, "r6": ret(126) * 100, "precio": last}).dropna()
df = df.sort_values("score", ascending=False)
rank = [{"t": t, "n": meta[t][0], "etf": meta[t][1], "s": r2(r.score), "tend": int(r.tend), "mom": r2(r.mom), "rs": r2(r.rs),
         "dist": r2(r.dist), "r3": r2(r.r3), "r6": r2(r.r6), "p": r2(r.precio)} for t, r in df.iterrows()]
for t in SECT:  # líderes por sector = mejores acciones del S&P en ese sector
    rrg[t]["lideres"] = [x["t"] for x in rank if x["etf"] == t][:8]

# --- Cabecera ---
hdr = {}
for t in ["SPY", "QQQ"]:
    c = px[t].dropna(); p = c.iloc[-1]; prev = c.iloc[-2]
    try:
        fi = yf.Ticker(t).fast_info; p = float(fi["last_price"]); prev = float(fi["previous_close"])
    except Exception: pass
    em = e(c, 200).iloc[-1]
    hdr[t] = {"p": r2(p), "chg": r2((p / prev - 1) * 100), "ema200": r2(em), "vsEma": r2((p / em - 1) * 100)}

# --- Eventos de la semana (Nasdaq, gratis) ---
hoy = dt.date.today(); lunes = hoy - dt.timedelta(days=hoy.weekday())
big = set(sp.t)  # universo S&P 500
caps, macro = [], []
KEY = {"CPI": "Inflación (CPI)", "Consumer Price Index": "Inflación (CPI)", "FOMC": "Fed (FOMC)", "Fed Interest Rate": "Fed: tasa de interés",
       "Nonfarm Payrolls": "Empleo (NFP)", "PCE": "Inflación PCE", "GDP": "PBI", "Unemployment Rate": "Desempleo", "PPI": "Inflación mayorista (PPI)"}
for i in range(5):
    d = (lunes + dt.timedelta(days=i)).isoformat()
    try:
        j = requests.get(f"https://api.nasdaq.com/api/calendar/earnings?date={d}", headers=UA, timeout=20).json()
        for r in (j.get("data") or {}).get("rows") or []:
            if r["symbol"].replace(".", "-") in big:
                mc = float((r.get("marketCap") or "0").replace("$", "").replace(",", "") or 0)
                caps.append({"fecha": d, "t": r["symbol"], "n": r["name"], "cap": mc, "hora": {"time-pre-market": "antes de abrir", "time-after-hours": "después del cierre"}.get(r.get("time"), "")})
    except Exception as ex: print("earn", d, ex, file=sys.stderr)
    try:
        j = requests.get(f"https://api.nasdaq.com/api/calendar/economicevents?date={d}", headers=UA, timeout=20).json()
        for r in (j.get("data") or {}).get("rows") or []:
            if r.get("country") != "United States": continue
            for k, v in KEY.items():
                if k.lower() in r["eventName"].lower():
                    macro.append({"fecha": d, "hora": r.get("gmt", ""), "ev": v, "orig": r["eventName"]}); break
    except Exception as ex: print("eco", d, ex, file=sys.stderr)
caps = sorted(caps, key=lambda x: -x["cap"])[:25]
caps.sort(key=lambda x: x["fecha"])
spy_chg = hdr["SPY"]["chg"]
dump("mercado.json", {"actualizado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "cabecera": hdr, "termometro": term, "rotacion": rrg,
     "ranking": rank[:100], "universo": len(rank), "eventos": {"semana": lunes.isoformat(), "balances": caps, "macro": macro},
     "animo": "malo" if (spy_chg is not None and spy_chg < -1.5) or term["ema200"] < 30 else "bueno"})
print("ok", len(rank), term["ema200"], len(caps), len(macro))
