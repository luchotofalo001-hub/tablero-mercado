#!/usr/bin/env python3
"""Indicador de Liquidez (Pipo Score) para el Tablero de Mercado.

Score 0–100 = 100 * Φ(X),  Φ(x) = 0.5 * (1 + erf(x / sqrt(2))),
X = X_base + X_fondeo.

X_base = promedio simple (1/N) de z-scores de 3 años (156 semanas),
con signo, solo sobre variables con dato:
  Liquidez (var. 13 semanas, luego z):
    1. M2 EE.UU.          WM2NS/M2SL     signo +
    2. Liquidez neta      WALCL−WTREGEN−RRPONTSYD (mismas unidades)  signo +
    3. Dólar amplio       DTWEXBGS       signo −
    4. Amplitud BCs       opcional/manual (si no hay dato, queda fuera de N)
  Estrés (z del nivel, signo −):
    5. VIX                VIXCLS / ^VIX
    6. MOVE               ^MOVE
    7. Spreads HY         BAMLH0A0HYM2   (si falta, queda fuera de N; se puede activar)
    8. Stress St. Louis   STLFSI4

X_fondeo (unidades reales, siempre ≤ 0):
    SOFR−IORB en pb:  -0.025 * max(0, pb)
    Reservas WRESBAL en T USD: -max(0, 3.00 − reservas_T)
      (WRESBAL viene en millones de USD → / 1e6)

Fuentes: FRED (API o CSV) cuando está disponible; si no,
Fed H.4.1 / H.6 / H.10 / PRates, NY Fed (SOFR/EFFR/ON RRP) y Yahoo.
"""
from __future__ import annotations
import io, json, math, os, sys, time, zipfile, datetime as dt, xml.etree.ElementTree as ET, re
import numpy as np, pandas as pd, requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json,text/csv,application/zip,*/*"}
OUT = os.path.join(os.path.dirname(__file__), "..", "site", "data", "mercado.json")
ROOT = os.path.join(os.path.dirname(__file__), "..")
START = "2010-01-01"
log = lambda *a: print(*a, file=sys.stderr)

# ---------- matemática ----------
def phi(x):
    if x is None or not np.isfinite(x):
        return None
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))

def score_of(x):
    p = phi(x)
    return None if p is None else 100.0 * p

def _r(x, n):
    """Redondeo half-up (0,205 → 0,21), el de las capturas."""
    if x is None or not np.isfinite(float(x)):
        return None
    x = float(x)
    p = 10 ** n
    return math.copysign(math.floor(abs(x) * p + 0.5), x) / p

def r1(x):
    return _r(x, 1)

def r2(x):
    return _r(x, 2)

def r3(x):
    return _r(x, 3)

# Umbral de reservas amplias: 10% del PBI nominal de EE.UU. (BEA NIPA A191RC,
# millones de USD, SAAR trimestral). Anclado en 3,00 T USD desde 2026 para
# que la fórmula viva y el simulador de Vista 3 coincidan con las unidades
# de Pipo (−max(0, 3,00 − reservas_T) hoy). Antes de 2026 el umbral sigue
# al PBI contemporáneo (2014–2017 ≈ 1,75–1,95 T; 2019 ≈ 2,14 T).
# Fuente: https://apps.bea.gov/national/Release/TXT/NipaDataQ.txt (4-nov-2026).
SOFR_INICIO = pd.Timestamp("2018-04-03")
UMBRAL_2026 = 3.00  # T USD

# year, quarter, GDP millions USD
_BEA_A191RC_Q = [
    (2010,1,14764610),(2010,2,14980193),(2010,3,15141607),(2010,4,15309474),
    (2011,1,15351448),(2011,2,15557539),(2011,3,15647680),(2011,4,15842259),
    (2012,1,16068805),(2012,2,16207115),(2012,3,16319541),(2012,4,16420419),
    (2013,1,16648189),(2013,2,16728687),(2013,3,16953838),(2013,4,17192019),
    (2014,1,17197738),(2014,2,17518508),(2014,3,17804228),(2014,4,17912079),
    (2015,1,18063529),(2015,2,18279784),(2015,3,18401626),(2015,4,18435137),
    (2016,1,18525933),(2016,2,18711702),(2016,3,18892639),(2016,4,19089379),
    (2017,1,19280084),(2017,2,19438643),(2017,3,19692595),(2017,4,20037088),
    (2018,1,20328553),(2018,2,20580912),(2018,3,20798730),(2018,4,20917867),
    (2019,1,21111600),(2019,2,21397938),(2019,3,21717171),(2019,4,21933217),
    (2020,1,21751238),(2020,2,19958291),(2020,3,21704437),(2020,4,22087160),
    (2021,1,22704650),(2021,2,23456708),(2021,3,23998844),(2021,4,24823190),
    (2022,1,25259992),(2022,2,25869353),(2022,3,26335374),(2022,4,26774117),
    (2023,1,27241282),(2023,2,27533925),(2023,3,28064032),(2023,4,28464306),
    (2024,1,28793191),(2024,2,29232964),(2024,3,29568256),(2024,4,29929552),
    (2025,1,30171979),(2025,2,30630174),(2025,3,31180493),(2025,4,31462523),
    (2026,1,31906274),(2026,2,32563030),(2026,3,33010036),
]

def gdp_nominal_t(fecha):
    """PBI nominal EE.UU. en billones (T) USD, escalón al inicio de trimestre (SAAR)."""
    if fecha is None:
        return None
    ts = pd.Timestamp(fecha)
    y, q = ts.year, (ts.month - 1) // 3 + 1
    last = None
    for yy, qq, mill in _BEA_A191RC_Q:
        if (yy, qq) <= (y, q):
            last = mill
        else:
            break
    if last is None:
        last = _BEA_A191RC_Q[0][2]
    return last / 1_000_000.0  # millions → T

def umbral_reservas(fecha=None):
    """Umbral de reservas amplias en T USD. 3,00 desde 2026 / si no hay fecha."""
    if fecha is None or pd.Timestamp(fecha) >= pd.Timestamp("2026-01-01"):
        return UMBRAL_2026
    g = gdp_nominal_t(fecha)
    if g is None or not np.isfinite(g):
        return UMBRAL_2026
    return 0.10 * float(g)

def fondeo_x(sofr_iorb_pb, reservas_t, fecha=None, umbral=None):
    """X_fondeo ≤ 0. SOFR−IORB = 0 antes del lanzamiento (3-abr-2018).
    Umbral de reservas: histórico = 10% PBI; vivo/2026 = 3,00 T."""
    pb = sofr_iorb_pb
    if fecha is not None and pd.Timestamp(fecha) < SOFR_INICIO:
        pb = 0.0
    a = 0.0 if pb is None else -0.025 * max(0.0, float(pb))
    u = UMBRAL_2026 if umbral is None and fecha is None else (
        umbral if umbral is not None else umbral_reservas(fecha)
    )
    b = 0.0 if reservas_t is None else -max(0.0, float(u) - float(reservas_t))
    return a + b, a, b

BANDAS = [
    ("Inundación", 80, 100.01, "INUNDACIÓN DE LIQUIDEZ"),
    ("Expansión", 60, 80, "EXPANSIÓN DE LIQUIDEZ"),
    ("Neutral", 40, 60, "LIQUIDEZ NEUTRAL"),
    ("Ajuste", 20, 40, "AJUSTE DE LIQUIDEZ"),
    ("Sequía", 0, 20, "SEQUÍA DE LIQUIDEZ"),
]

def regimen_de(score):
    if score is None:
        return {"regimen": None, "titulo": None, "al_proximo_regimen": None, "a_neutral": None, "subtitulo": None}
    s = float(score)
    nombre, lo, hi, titulo = BANDAS[-1]
    for n, a, b, t in BANDAS:
        if a <= s < b:
            nombre, lo, hi, titulo = n, a, b, t
            break
    # próximo régimen hacia "más liquidez" (hacia arriba)
    prox_piso = 20 if s < 20 else 40 if s < 40 else 60 if s < 60 else 80 if s < 80 else None
    al_prox = None if prox_piso is None else r1(prox_piso - s)
    a_neu = r1(max(0.0, 40.0 - s))
    if nombre == "Sequía":
        sub = f"Banda más baja · {r1(20 - s)} pts bajo ajuste"
    elif nombre == "Ajuste":
        sub = f"Entre 20 y 40 · {r1(40 - s)} pts bajo neutral"
    elif nombre == "Neutral":
        sub = "Banda media · 40 a 60"
    elif nombre == "Expansión":
        sub = f"Entre 60 y 80 · {r1(s - 60)} pts sobre neutral"
    else:
        sub = "Banda más alta · sobre 80"
    return {"regimen": nombre, "titulo": titulo, "al_proximo_regimen": al_prox,
            "a_neutral": a_neu, "subtitulo": sub}

# aportes y score a partir de z (ya con signo aplicado; None = inactiva)
def calcular(z_signed, sofr_pb, reservas_t, fecha=None, umbral=None):
    act = [z for z in z_signed if z is not None and np.isfinite(z)]
    n = len(act)
    x_base = (sum(act) / n) if n else None
    x_f, a_s, a_r = fondeo_x(sofr_pb, reservas_t, fecha=fecha, umbral=umbral)
    x_tot = None if x_base is None else x_base + x_f
    s = score_of(x_tot)
    s0 = score_of(x_base)
    aportes = []
    for z in z_signed:
        if z is None or not np.isfinite(z) or not n:
            aportes.append(None)
        else:
            aportes.append(z / n)
    fondeo_pts = None if s is None or s0 is None else r1(r1(s) - r1(s0))
    return {"n": n, "x_base": x_base, "x_fondeo": x_f, "x_total": x_tot,
            "score": s, "score_sin_fondeo": s0, "fondeo_pts": fondeo_pts,
            "aportes": aportes, "aporte_sofr": a_s, "aporte_reservas": a_r}

def test_formula():
    """Chequeo contra los números de las capturas de @Pipo_Bpo (20-nov)."""
    # z mostrados (después de aplicar signo) y fondeo +2,0 pb / $2,98T
    z = [-1.23, 0.29, -2.05, -3.00, -0.95, 1.13]
    out = calcular(z, 2.0, 2.98)
    s0, s = r1(out["score_sin_fondeo"]), r1(out["score"])
    ok = []
    ok.append(("sin fondeo 16,6", s0 == 16.6, s0))
    ok.append(("con fondeo 15,0", s == 15.0, s))
    ok.append(("fondeo −1,6 pts", r1(out["fondeo_pts"]) == -1.6, out["fondeo_pts"]))
    ok.append(("X_base ≈ −0,968", abs(out["x_base"] + 0.968) < 0.001, r3(out["x_base"])))
    ok.append(("X ≈ −1,038", abs(out["x_total"] + 1.038) < 0.001, r3(out["x_total"])))
    # aportes 1/6
    ap = [r2(x) for x in out["aportes"]]
    ok.append(("aporte VIX −0,50", ap[3] == -0.50, ap[3]))
    ok.append(("aporte DXY −0,34", ap[2] == -0.34, ap[2]))
    ok.append(("aporte M2 −0,21", ap[0] == -0.21, ap[0]))
    failed = [k for k, b, v in ok if not b]
    for k, b, v in ok:
        log(("OK" if b else "FAIL"), k, "→", v)
    if failed:
        raise SystemExit("test_formula FALLÓ: " + ", ".join(failed))
    log("test_formula OK")
    return True

def test_umbral_y_sofr():
    """Umbral histórico ~10% PBI, 3,00 T en 2026, y SOFR−IORB = 0 pre 3-abr-2018."""
    ok = []
    u14 = umbral_reservas("2014-06-15")
    u17 = umbral_reservas("2017-06-15")
    u19 = umbral_reservas("2019-06-15")
    u26 = umbral_reservas("2026-11-23")
    ok.append(("umbral 2014 ≈ 1,75 T", 1.72 <= u14 <= 1.82, r3(u14)))
    ok.append(("umbral 2017 ≈ 1,94 T", 1.90 <= u17 <= 1.98, r3(u17)))
    ok.append(("umbral 2019 ≈ 2,14 T", abs(u19 - 2.14) < 0.03, r3(u19)))
    ok.append(("umbral 2026 = 3,00", u26 == 3.00, u26))
    ok.append(("umbral None = 3,00", umbral_reservas(None) == 3.00, umbral_reservas(None)))
    # 2017: reservas típicas ~2,2 T, por encima del umbral → 0 penalidad
    xf, a, b = fondeo_x(0.0, 2.20, fecha="2017-06-15")
    ok.append(("2017 reservas 2,20 T sin penalidad", a == 0.0 and b == 0.0, (a, b)))
    # 2019: reservas ~1,50 T vs umbral ~2,14 → gap moderado (no −1,50 del umbral fijo 3,00)
    xf, a, b = fondeo_x(0.0, 1.50, fecha="2019-06-15")
    ok.append(("2019 gap moderado (no crush a −1,50)", -0.80 <= b <= -0.50, r3(b)))
    # vivo 2026 sigue en 3,00
    xf, a, b = fondeo_x(2.0, 2.98, fecha="2026-11-20")
    ok.append(("2026 umbral 3,00 / reservas 2,98 → −0,02", abs(b + 0.02) < 1e-9, r3(b)))
    # SOFR no existía
    xf, a, b = fondeo_x(25.0, 2.20, fecha="2017-06-15")
    ok.append(("pre-abr 2018 SOFR−IORB = 0", a == 0.0, a))
    xf, a, b = fondeo_x(25.0, 2.20, fecha="2018-04-02")
    ok.append(("2-abr-2018 SOFR−IORB = 0", a == 0.0, a))
    xf, a, b = fondeo_x(25.0, 2.98, fecha="2018-04-03")
    ok.append(("desde 3-abr-2018 SOFR cuenta", abs(a + 0.625) < 1e-9, r3(a)))
    # el chequeo vivo de la fórmula no se altera (fecha omitida → umbral 3,00)
    out = calcular([-1.23, 0.29, -2.05, -3.00, -0.95, 1.13], 2.0, 2.98)
    ok.append(("X_base=-0,968 → 16,6", r1(out["score_sin_fondeo"]) == 16.6, r1(out["score_sin_fondeo"])))
    ok.append(("X=-1,038 → 15,0", r1(out["score"]) == 15.0, r1(out["score"])))
    failed = [k for k, b, v in ok if not b]
    for k, b, v in ok:
        log(("OK" if b else "FAIL"), k, "→", v)
    if failed:
        raise SystemExit("test_umbral_y_sofr FALLÓ: " + ", ".join(failed))
    log("test_umbral_y_sofr OK")
    return True

def _punto_cerca(hist, fecha):
    ts = pd.Timestamp(fecha)
    return min(hist, key=lambda p: abs((pd.Timestamp(p["fecha"]) - ts).days))

def test_historia(hist=None):
    """Chequeos sobre la curva semanal: 2017 alineada, 2019 con gap moderado."""
    if hist is None:
        path = os.path.abspath(OUT)
        try:
            hist = (json.load(open(path)).get("liquidez") or {}).get("historia") or []
        except Exception:
            hist = []
    if len(hist) < 50:
        log("test_historia: sin historia suficiente, se omite")
        return True
    ok = []
    p17 = _punto_cerca(hist, "2017-06-15")
    p19 = _punto_cerca(hist, "2019-06-15")
    p20 = _punto_cerca(hist, "2020-03-18")
    s17, d17 = p17.get("score"), p17.get("score_sin_fondeo")
    gap17 = (s17 or 0) - (d17 or 0)
    ok.append(("Jun-2017 solid ≈ dashed (|gap|≤8)", abs(gap17) <= 8, (p17["fecha"], s17, d17, round(gap17, 1))))
    ok.append(("Jun-2017 alrededor 60-75", 55 <= (s17 or 0) <= 85 and 55 <= (d17 or 0) <= 90,
               (s17, d17)))
    s19, d19 = p19.get("score"), p19.get("score_sin_fondeo")
    gap19 = (s19 or 0) - (d19 or 0)
    ok.append(("Jun-2019 solid no crush (~1)", s19 is not None and s19 >= 8,
               (p19["fecha"], s19, d19, round(gap19, 1))))
    ok.append(("Jun-2019 gap moderado", s19 is not None and d19 is not None and -25 <= gap19 <= 0,
               (s19, d19, round(gap19, 1))))
    s20, d20 = p20.get("score"), p20.get("score_sin_fondeo")
    ok.append(("Mar-2020 ambos bajos", s20 is not None and s20 <= 20 and d20 is not None and d20 <= 25,
               (p20["fecha"], s20, d20)))
    failed = [k for k, b, v in ok if not b]
    for k, b, v in ok:
        log(("OK" if b else "FAIL"), k, "→", v)
    if failed:
        raise SystemExit("test_historia FALLÓ: " + ", ".join(failed))
    log("test_historia OK")
    return True

# ---------- HTTP ----------
def get(url, timeout=60, raw=False):
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.content if raw else r

# ---------- FRED ----------
# unidades FRED → factor para llevar a la unidad de trabajo
# net liquidity se trabaja en miles de millones (billions) USD
# reservas se trabajan en billones (trillions) USD
FRED_META = {
    "WM2NS":      ("billions", 1.0),
    "M2SL":       ("billions", 1.0),
    "WALCL":      ("millions", 1e-3),      # → billions
    "WTREGEN":    ("millions", 1e-3),      # → billions
    "RRPONTSYD":  ("billions", 1.0),
    "DTWEXBGS":   ("index", 1.0),
    "VIXCLS":     ("index", 1.0),
    "BAMLH0A0HYM2": ("percent", 1.0),
    "STLFSI4":    ("index", 1.0),
    "SOFR":       ("percent", 1.0),
    "IORB":       ("percent", 1.0),
    "IOER":       ("percent", 1.0),
    "WRESBAL":    ("millions", 1e-6),      # → trillions
    "NASDAQ100":  ("index", 1.0),
}

def _fred_key():
    return os.environ.get("FRED_API_KEY") or os.environ.get("FRED_KEY")

# Si el CSV de FRED falla una vez (p.ej. el host está filtrado), no reintentar el resto.
_FRED_CSV_OK = True

def fred_series(sid, start=START):
    """Devuelve Series float, índice diario, ya escalada a la unidad de trabajo. None si falla."""
    global _FRED_CSV_OK
    key = _fred_key()
    s = None
    if key:
        try:
            url = ("https://api.stlouisfed.org/fred/series/observations"
                   f"?series_id={sid}&api_key={key}&file_type=json"
                   f"&observation_start={start}&sort_order=asc")
            js = get(url).json()
            rows = []
            for o in js.get("observations", []):
                v = o.get("value")
                if v in (None, "", "."):
                    continue
                try:
                    rows.append((o["date"], float(v)))
                except Exception:
                    pass
            if rows:
                s = pd.Series({pd.Timestamp(d): v for d, v in rows}, dtype=float).sort_index()
        except Exception as ex:
            log("fred api", sid, ex)
    if (s is None or s.empty) and _FRED_CSV_OK and not os.environ.get("FRED_SKIP_CSV"):
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
            r = requests.get(url, headers=UA, timeout=8)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            col = [c for c in df.columns if c.lower() != "date"][0]
            df["DATE"] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
            val = pd.to_numeric(df[col], errors="coerce")
            s = pd.Series(val.values, index=df["DATE"]).dropna().sort_index()
        except Exception as ex:
            log("fred csv", sid, ex)
            _FRED_CSV_OK = False
    if s is None or s.empty:
        return None
    factor = FRED_META.get(sid, ("raw", 1.0))[1]
    s = s.astype(float) * factor
    s.name = sid
    return s

# ---------- Fed DDP (fallback) ----------
def _iter_series(zip_path, inner, pred):
    zf = zipfile.ZipFile(zip_path)
    with zf.open(inner) as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            loc = re.sub(r"\{.*\}", "", el.tag)
            if loc != "Series":
                continue
            if pred(el.attrib):
                obs, desc = [], ""
                for c in el:
                    cl = re.sub(r"\{.*\}", "", c.tag)
                    if cl == "Obs":
                        v, t, st = c.attrib.get("OBS_VALUE"), c.attrib.get("TIME_PERIOD"), c.attrib.get("OBS_STATUS")
                        if v not in (None, "", "ND", "NA") and st != "ND":
                            try:
                                obs.append((t, float(v)))
                            except Exception:
                                pass
                    elif cl == "Annotations":
                        for a in c:
                            typ = "".join((x.text or "") for x in a if re.sub(r"\{.*\}", "", x.tag) == "AnnotationType")
                            if typ == "Short Description":
                                desc = "".join((x.text or "") for x in a if re.sub(r"\{.*\}", "", x.tag) == "AnnotationText")
                yield el.attrib.get("SERIES_NAME"), dict(el.attrib), desc, obs
            el.clear()

def _download_ddp(rel, dest):
    url = f"https://www.federalreserve.gov/datadownload/Output.aspx?rel={rel}&filetype=zip"
    data = get(url, raw=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "wb").write(data)
    return dest

def _obs_to_series(obs, factor=1.0, name=""):
    if not obs:
        return None
    s = pd.Series({pd.Timestamp(d): v * factor for d, v in obs}, dtype=float).sort_index()
    s.name = name
    return s

def fed_h41():
    """Total assets, TGA, RRP others, reservas. Unidades de trabajo: bn (activos/TGA/RRP) y T (reservas)."""
    path = "/tmp/fed/FRB_H41.zip"
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        _download_ddp("H41", path)
    want = {"TA": "assets_bn", "DEPUSTG": "tga_bn", "RRPO": "rrp_bn", "RBFRB": "reservas_raw"}
    out = {}
    def pred(a):
        return (a.get("COMPONENT") in want and a.get("SERIESTYPE") == "L"
                and a.get("DISTRIBUTION") == "TOT" and a.get("FREQ") == "19")
    for name, attr, desc, obs in _iter_series(path, "H41_data.xml", pred):
        comp = attr.get("COMPONENT")
        # UNIT_MULT=1000000 → millones de USD
        if comp == "RBFRB":
            out["reservas_t"] = _obs_to_series(obs, 1e-6, "reservas_t")  # millions → T
        else:
            out[want[comp]] = _obs_to_series(obs, 1e-3, want[comp])      # millions → bn
        log("h41", name, comp, desc[:80], "n", len(obs), "last", obs[-1] if obs else None,
            "unit_mult", attr.get("UNIT_MULT"))
    return out

def fed_h6_m2():
    path = "/tmp/fed/FRB_H6.zip"
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        _download_ddp("H6", path)
    # Preferir M2 NSA semanal (WM2NS); fallback M2 SA mensual (M2SL)
    weekly = monthly = None
    def pred(a):
        return a.get("SERIES_NAME") in ("M2_N.WM", "M2.M")
    for name, attr, desc, obs in _iter_series(path, "h6_data.xml", pred):
        # UNIT_MULT=1e+09 → already billions
        s = _obs_to_series(obs, 1.0, name)
        log("h6", name, desc[:80], "n", len(obs), "last", obs[-1] if obs else None)
        if name == "M2_N.WM":
            weekly = s
        else:
            monthly = s
    return weekly, monthly

def fed_h10_dollar():
    path = "/tmp/fed/FRB_H10.zip"
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        _download_ddp("H10", path)
    def pred(a):
        return a.get("FX") == "BRD" and a.get("FREQ") == "9"  # daily Nominal Broad Dollar Index = DTWEXBGS
    for name, attr, desc, obs in _iter_series(path, "H10_data.xml", pred):
        s = _obs_to_series(obs, 1.0, "DTWEXBGS")
        log("h10", name, desc[:80], "n", len(obs), "last", obs[-1] if obs else None)
        return s
    return None

def fed_prates():
    """IORB (desde 2021-07-29) empalmado con IOER (hasta 2021-07-28). Porcentaje."""
    path = "/tmp/fed/FRB_PRates.zip"
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        _download_ddp("PRates", path)
    ioer = iorb = None
    def pred(a):
        return a.get("SERIES_NAME") in ("RESBME_N.D", "RESBM_N.D")
    for name, attr, desc, obs in _iter_series(path, "PRATES_data.xml", pred):
        s = _obs_to_series(obs, 1.0, name)
        log("prates", name, desc[:80], "n", len(obs), "last", obs[-1] if obs else None)
        if name == "RESBME_N.D":
            ioer = s
        else:
            iorb = s
    if iorb is None:
        return ioer
    if ioer is None:
        return iorb
    # IOER hasta el día previo al inicio de IORB
    cut = iorb.index.min()
    ioer = ioer[ioer.index < cut]
    s = pd.concat([ioer, iorb]).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    s.name = "IORB"
    return s

def nyfed_rate(kind, start=START, end=None):
    """kind: sofr | effr. Porcentaje."""
    end = end or dt.date.today().isoformat()
    path = {"sofr": "secured/sofr", "effr": "unsecured/effr"}[kind]
    url = f"https://markets.newyorkfed.org/api/rates/{path}/search.json?startDate={start}&endDate={end}"
    js = get(url).json()
    rows = []
    for o in js.get("refRates") or []:
        d, v = o.get("effectiveDate"), o.get("percentRate")
        if d and v is not None:
            try:
                rows.append((d, float(v)))
            except Exception:
                pass
    if not rows:
        return None
    s = pd.Series({pd.Timestamp(d): v for d, v in rows}, dtype=float).sort_index()
    s.name = kind.upper()
    log("nyfed", kind, "n", len(s), "last", (str(s.index[-1].date()), float(s.iloc[-1])))
    return s

def yahoo_close(ticker, start=START):
    import yfinance as yf
    h = yf.Ticker(ticker).history(start=start, auto_adjust=False, interval="1d")
    if h is None or h.empty:
        return None
    s = h["Close"].copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.name = ticker
    log("yahoo", ticker, "n", len(s), "last", (str(s.index[-1].date()), float(s.iloc[-1])))
    return s

# ---------- construcción de series ----------
def weekly(s, how="last"):
    if s is None or s.empty:
        return None
    s = s.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s = s[~s.index.duplicated(keep="last")].sort_index().astype(float)
    w = s.resample("W-WED").last()
    # No etiquetar la semana en curso con un miércoles futuro
    today = pd.Timestamp.today().normalize()
    if not w.empty and w.index[-1] > today:
        w.index = pd.DatetimeIndex(list(w.index[:-1]) + [today])
        w = w[~w.index.duplicated(keep="last")]
    w.attrs["last_obs"] = s.index.max()
    return w.dropna()

def roll_z(s, window=156, minp=104, ddof=1):
    if s is None or s.empty:
        return None
    mu = s.rolling(window, min_periods=minp).mean()
    sd = s.rolling(window, min_periods=minp).std(ddof=ddof)
    z = (s - mu) / sd.replace(0, np.nan)
    return z

def chg13(s):
    if s is None or s.empty:
        return None
    return s.pct_change(13)

def last_valid(s):
    if s is None or s.empty:
        return None, None
    s = s.dropna()
    if s.empty:
        return None, None
    return s.index[-1], float(s.iloc[-1])

# ---------- escenarios (ilustrativos, reproducen los scores de la captura) ----------
# Hoy se carga en vivo. Los demás son vectores fijos (z crudos, antes de signo)
# pensados para los scores 2, 22, 40 y 59 de la captura del 20-nov.

def escenarios_fijos(hoy_inputs, hoy_fondeo):
    """hoy_inputs: dict id → {z, activo}. hoy_fondeo: {sofr_iorb_pb, reservas_t}."""
    # baseline 20-nov (captura) — se usa como plantilla de los ilustrativos
    base_z = {
        "m2": -1.23, "liq_neta": 0.29, "dolar": 2.05, "amplitud": None,
        "vix": 3.00, "move": 0.95, "hy": None, "stlfsi": -1.13,
    }
    def pack(nombre, desc, zmap, sofr, res, nota=None):
        return {"id": nombre.lower().replace(" ", "_"), "nombre": nombre, "descripcion": desc,
                "z": zmap, "sofr_iorb_pb": sofr, "reservas_t": res, "nota": nota}

    # Vectores ilustrativos que reproducen los scores de la captura (2, 22, 40, 59)
    una = dict(base_z); una["vix"] = 1.50
    agr = {"m2": -0.4, "liq_neta": 0.0, "dolar": 0.8, "amplitud": None,
           "vix": 1.5, "move": 0.8, "hy": 1.5, "stlfsi": 0.3}
    agr_bp, agr_res = 50.0, 2.95
    vol = {"m2": -1.23, "liq_neta": 0.29, "dolar": 1.21, "amplitud": None,
           "vix": 0.5, "move": 0.0, "hy": None, "stlfsi": -1.13}
    giro = {"m2": 0.30, "liq_neta": 0.70, "dolar": 0.80, "amplitud": None,
            "vix": -0.20, "move": -0.20, "hy": None, "stlfsi": -0.80}

    hoy_z = {k: (hoy_inputs[k]["z"] if hoy_inputs[k]["activo"] else None)
             for k in ["m2", "liq_neta", "dolar", "amplitud", "vix", "move", "hy", "stlfsi"]}
    return [
        pack("Hoy", "z-scores calculados en la ventana móvil de 3 años", hoy_z,
             hoy_fondeo["sofr_iorb_pb"], hoy_fondeo["reservas_t"],
             nota="valores en vivo"),
        pack("Agresivo y desordenado", "Suba de 50 pb, crédito se rompe (ilustrativo)",
             agr, agr_bp, agr_res),
        pack("Una y listo", "Suba de 25 pb y pausa, VIX a 25 (z = 1,5)",
             una, 2.0, 2.98),
        pack("Volatilidad se normaliza", "VIX 20 (z = 0,5), crédito se calma",
             vol, 0.0, 3.10),
        pack("Giro de política", "Cesan las subas, mercados calmos (ilustrativo)",
             giro, 0.0, 3.20),
    ]

# ---------- orquestación ----------
ENTRADAS_META = [
    # id, grupo, nombre, detalle, signo, modo: 'chg13' o 'nivel'
    ("m2", "liquidez", "M2 de EE.UU. (sustituye al M2 global)",
     "Variación a 13 semanas · M2 global en dólares pendiente", 1, "chg13"),
    ("liq_neta", "liquidez", "Liquidez neta de EE.UU.",
     "Variación a 13 semanas · balance de la Fed − caja del Tesoro − repo inverso", 1, "chg13"),
    ("dolar", "liquidez", "Dólar amplio (sustituye al DXY)",
     "Variación a 13 semanas · dólar más fuerte = dinero más escaso", -1, "chg13"),
    ("amplitud", "liquidez", "Amplitud de bancos centrales",
     "Sin dato: falta cargarla a mano. Queda fuera del promedio", 1, "manual"),
    ("vix", "estres", "VIX", "Volatilidad de acciones", -1, "nivel"),
    ("move", "estres", "MOVE", "Volatilidad de bonos", -1, "nivel"),
    ("hy", "estres", "Spreads de crédito high yield",
     "ICE BofA US High Yield OAS (FRED BAMLH0A0HYM2). Si no hay dato, queda fuera del promedio", -1, "nivel"),
    ("stlfsi", "estres", "Índice de estrés de la Fed de St. Louis", "STLFSI4", -1, "nivel"),
]

def _pick(*cands):
    for s, fuente in cands:
        if s is not None and not s.empty:
            return s, fuente
    return None, None

def recolectar():
    fuentes = []
    # FRED primero
    fred = {}
    for sid in ["WM2NS", "M2SL", "WALCL", "WTREGEN", "RRPONTSYD", "DTWEXBGS",
                "VIXCLS", "BAMLH0A0HYM2", "STLFSI4", "SOFR", "IORB", "IOER",
                "WRESBAL", "NASDAQ100"]:
        try:
            fred[sid] = fred_series(sid)
        except Exception as ex:
            log("fred fail", sid, ex)
            fred[sid] = None
        if fred.get(sid) is not None:
            fuentes.append(f"FRED:{sid}")

    # Fallbacks oficiales
    h41 = h6w = h6m = dxy = iorb = sofr = None
    need_h41 = fred.get("WALCL") is None or fred.get("WTREGEN") is None or fred.get("RRPONTSYD") is None or fred.get("WRESBAL") is None
    if need_h41:
        try:
            h41 = fed_h41(); fuentes.append("Fed H.4.1")
        except Exception as ex:
            log("h41 fail", ex); h41 = {}
    if fred.get("WM2NS") is None and fred.get("M2SL") is None:
        try:
            h6w, h6m = fed_h6_m2(); fuentes.append("Fed H.6")
        except Exception as ex:
            log("h6 fail", ex)
    if fred.get("DTWEXBGS") is None:
        try:
            dxy = fed_h10_dollar(); fuentes.append("Fed H.10")
        except Exception as ex:
            log("h10 fail", ex)
    if fred.get("IORB") is None and fred.get("IOER") is None:
        try:
            iorb = fed_prates(); fuentes.append("Fed PRates")
        except Exception as ex:
            log("prates fail", ex)
    if fred.get("SOFR") is None:
        try:
            sofr = nyfed_rate("sofr"); fuentes.append("NY Fed SOFR")
        except Exception as ex:
            log("sofr fail", ex)
            sofr = None

    # Yahoo
    vix_y = move = ndx = None
    try:
        vix_y = yahoo_close("^VIX")
        if vix_y is not None:
            fuentes.append("Yahoo ^VIX")
    except Exception as ex:
        log("yahoo vix", ex)
    try:
        move = yahoo_close("^MOVE")
        if move is not None:
            fuentes.append("Yahoo ^MOVE")
    except Exception as ex:
        log("yahoo move", ex)
    try:
        ndx = yahoo_close("^NDX")
        if ndx is not None:
            fuentes.append("Yahoo ^NDX")
    except Exception as ex:
        log("yahoo ndx", ex)

    # Series en unidad de trabajo
    m2, m2_src = _pick((fred.get("WM2NS"), "FRED WM2NS"), (h6w, "Fed H.6 M2 NSA semanal"),
                       (fred.get("M2SL"), "FRED M2SL"), (h6m, "Fed H.6 M2 SA mensual"))
    assets, _ = _pick((fred.get("WALCL"), "FRED WALCL"), ((h41 or {}).get("assets_bn"), "H.4.1 TA"))
    tga, _ = _pick((fred.get("WTREGEN"), "FRED WTREGEN"), ((h41 or {}).get("tga_bn"), "H.4.1 TGA"))
    rrp, _ = _pick((fred.get("RRPONTSYD"), "FRED RRPONTSYD"), ((h41 or {}).get("rrp_bn"), "H.4.1 RRPO"))
    reservas, res_src = _pick((fred.get("WRESBAL"), "FRED WRESBAL"), ((h41 or {}).get("reservas_t"), "H.4.1 RBFRB"))
    dolar, dxy_src = _pick((fred.get("DTWEXBGS"), "FRED DTWEXBGS"), (dxy, "Fed H.10 BRD"))
    vix, vix_src = _pick((fred.get("VIXCLS"), "FRED VIXCLS"), (vix_y, "Yahoo ^VIX"))
    hy, hy_src = _pick((fred.get("BAMLH0A0HYM2"), "FRED BAMLH0A0HYM2"))
    stl, stl_src = _pick((fred.get("STLFSI4"), "FRED STLFSI4"))
    sofr_s, sofr_src = _pick((fred.get("SOFR"), "FRED SOFR"), (sofr, "NY Fed SOFR"))
    # IORB empalmado con IOER
    if fred.get("IORB") is not None and fred.get("IOER") is not None:
        cut = fred["IORB"].index.min()
        iorb_s = pd.concat([fred["IOER"][fred["IOER"].index < cut], fred["IORB"]]).sort_index()
        iorb_s = iorb_s[~iorb_s.index.duplicated(keep="last")]
        iorb_src = "FRED IORB+IOER"
    elif fred.get("IORB") is not None:
        iorb_s, iorb_src = fred["IORB"], "FRED IORB"
    else:
        iorb_s, iorb_src = iorb, "Fed PRates IORB+IOER"

    # Liquidez neta: las tres patas YA están en billions si el escalado fue correcto
    liq = None
    liq_src = None
    if assets is not None and tga is not None and rrp is not None:
        # alinear por unión y ffill corto (hasta 10 días) antes de restar
        a, t, p = weekly(assets), weekly(tga), weekly(rrp)
        idx = a.index.union(t.index).union(p.index)
        liq = a.reindex(idx).ffill(limit=2) - t.reindex(idx).ffill(limit=2) - p.reindex(idx).ffill(limit=2)
        liq.name = "liq_neta_bn"
        liq_src = "WALCL − WTREGEN − RRPONTSYD (billions USD)"
        # sanity: liquidez neta típica 3–8 T = 3.000–8.000 bn
        last = float(liq.dropna().iloc[-1])
        log("liq_neta last bn", round(last, 1), "T", round(last / 1000, 3))
        if not (1000 < last < 20000):
            log("ALERTA: liquidez neta fuera de rango esperado (¿unidades?)")

    if reservas is not None:
        last_r = float(weekly(reservas).dropna().iloc[-1])
        log("reservas last T", round(last_r, 3))
        if not (0.5 < last_r < 8):
            log("ALERTA: reservas fuera de rango en T USD (¿unidades?)")

    series = {
        "m2": (weekly(m2), m2_src, "chg13"),
        "liq_neta": (liq, liq_src, "chg13"),
        "dolar": (weekly(dolar), dxy_src, "chg13"),
        "vix": (weekly(vix), vix_src, "nivel"),
        "move": (weekly(move), "Yahoo ^MOVE" if move is not None else None, "nivel"),
        "hy": (weekly(hy), hy_src, "nivel"),
        "stlfsi": (weekly(stl), stl_src, "nivel"),
        "reservas_t": (weekly(reservas), res_src, "nivel"),
        "sofr": (weekly(sofr_s) if sofr_s is not None else None, sofr_src, "nivel"),
        "iorb": (weekly(iorb_s) if iorb_s is not None else None, iorb_src, "nivel"),
        "ndx": (weekly(ndx) if ndx is not None else weekly(fred.get("NASDAQ100")),
                "Yahoo ^NDX" if ndx is not None else ("FRED NASDAQ100" if fred.get("NASDAQ100") is not None else None),
                "nivel"),
    }
    return series, sorted(set(fuentes))

def construir(series):
    # z semanales desde 2014 (con historial desde 2010/11)
    z = {}
    niveles = {}
    for eid, grupo, nombre, det, signo, modo in ENTRADAS_META:
        if modo == "manual":
            z[eid] = None
            niveles[eid] = None
            continue
        s, src, md = series[eid]
        if s is None or s.empty:
            z[eid] = None
            niveles[eid] = None
            continue
        niveles[eid] = s
        base = chg13(s) if md == "chg13" else s
        z[eid] = roll_z(base)

    reservas = series["reservas_t"][0]
    sofr, iorb = series["sofr"][0], series["iorb"][0]
    sofr_iorb_pb = None
    if sofr is not None and iorb is not None:
        idx = sofr.index.union(iorb.index)
        sofr_iorb_pb = (sofr.reindex(idx).ffill() - iorb.reindex(idx).ffill()) * 100.0  # pp → pb
        sofr_iorb_pb.name = "sofr_iorb_pb"

    ndx = series["ndx"][0]

    # índice semanal común desde 2014
    parts = [x for x in list(z.values()) + [sofr_iorb_pb, reservas, ndx] if x is not None]
    if not parts:
        raise RuntimeError("sin series para armar el indicador")
    idx = parts[0].index
    for p in parts[1:]:
        idx = idx.union(p.index)
    idx = idx[(idx >= "2014-01-01") & (idx <= (pd.Timestamp.today() + pd.Timedelta(days=7)))]
    idx = pd.DatetimeIndex(sorted(idx))

    def at(s, t):
        if s is None:
            return None
        v = s.reindex(idx).ffill()
        x = v.loc[t] if t in v.index else np.nan
        return None if pd.isna(x) else float(x)

    hist = []
    for t in idx:
        zs, used = [], []
        for eid, grupo, nombre, det, signo, modo in ENTRADAS_META:
            zv = at(z[eid], t) if z.get(eid) is not None else None
            if zv is None:
                continue
            zs.append(signo * zv)
            used.append(eid)
        if len(zs) < 3:
            continue
        pb = at(sofr_iorb_pb, t)
        res = at(reservas, t)
        out = calcular(zs, pb, res, fecha=t)
        if out["score"] is None:
            continue
        hist.append({
            "fecha": t.strftime("%Y-%m-%d"),
            "score": r1(out["score"]),
            "score_sin_fondeo": r1(out["score_sin_fondeo"]),
            "ndx": r1(at(ndx, t)),
            "x_base": r3(out["x_base"]),
            "x_fondeo": r3(out["x_fondeo"]),
        })

    if not hist:
        raise RuntimeError("historia vacía")

    # punto actual = última fila con score
    last = hist[-1]
    fecha = last["fecha"]
    t = pd.Timestamp(fecha)

    entradas = []
    z_hoy = []
    for eid, grupo, nombre, det, signo, modo in ENTRADAS_META:
        src = series[eid][1] if eid in series else None
        s_nivel = niveles.get(eid)
        zv = at(z[eid], t) if z.get(eid) is not None else None
        activo = zv is not None
        fecha_v, valor = last_valid(s_nivel) if s_nivel is not None else (None, None)
        # fecha nativa (último dato real), no el cierre de semana
        if s_nivel is not None and hasattr(s_nivel, "attrs") and s_nivel.attrs.get("last_obs") is not None:
            fecha_v = s_nivel.attrs["last_obs"]
        z_hoy.append((signo * zv) if activo else None)
        entradas.append({
            "id": eid, "grupo": grupo, "nombre": nombre, "detalle": det,
            "signo": signo, "modo": modo, "activo": activo,
            "z": r2(zv), "valor": r2(valor) if valor is not None else None,
            "fecha": fecha_v.strftime("%Y-%m-%d") if fecha_v is not None else None,
            "fuente": src, "manual": modo == "manual",
        })

    pb = at(sofr_iorb_pb, t)
    res = at(reservas, t)
    out = calcular(z_hoy, pb, res, fecha=t)
    for e, ap in zip(entradas, out["aportes"]):
        e["aporte"] = r2(ap)

    # correl 13 semanas (cambios del score vs retornos del NDX)
    hdf = pd.DataFrame(hist)
    hdf["fecha"] = pd.to_datetime(hdf["fecha"])
    hdf = hdf.set_index("fecha")
    corr = None
    if "ndx" in hdf and hdf["ndx"].notna().sum() >= 14:
        a = hdf["score"].diff()
        b = hdf["ndx"].pct_change()
        tail = pd.concat([a, b], axis=1).dropna().tail(13)
        if len(tail) >= 8:
            corr = float(tail.iloc[:, 0].corr(tail.iloc[:, 1]))

    ndx_fecha, ndx_val = last_valid(series["ndx"][0] if series["ndx"][0] is not None else None)

    reg = regimen_de(out["score"])
    hoy_inputs = {e["id"]: {"z": e["z"], "activo": e["activo"]} for e in entradas}
    esc = escenarios_fijos(hoy_inputs, {"sofr_iorb_pb": r2(pb), "reservas_t": r3(res)})
    # anotar score de cada escenario
    def signed_from(zmap):
        xs = []
        for eid, grupo, nombre, det, signo, modo in ENTRADAS_META:
            v = zmap.get(eid)
            xs.append(None if v is None else signo * v)
        return xs
    for e in esc:
        ev = calcular(signed_from(e["z"]), e["sofr_iorb_pb"], e["reservas_t"])
        e["score"] = r1(ev["score"])
        e["score_sin_fondeo"] = r1(ev["score_sin_fondeo"])

    # hitos históricos (fechas aproximadas como en la captura, con score real)
    def hito(fecha_obj, etiqueta, fallback_range=None):
        # buscar el punto más cercano
        if hdf.empty:
            return None
        i = hdf.index[np.argmin(np.abs((hdf.index - pd.Timestamp(fecha_obj)).days))]
        return {"fecha": i.strftime("%Y-%m-%d"), "score": float(hdf.loc[i, "score"]), "etiqueta": etiqueta}

    hitos = []
    # 2017: etiqueta 60–75, anclar en un punto de esa banda (junio), no en el máximo (~90)
    y17 = hdf.loc["2017-01-01":"2017-12-31", "score"].dropna() if "2017-01-01" <= hdf.index.max().strftime("%Y-%m-%d") else pd.Series(dtype=float)
    if not y17.empty:
        band = y17[(y17 >= 60) & (y17 <= 75)]
        if band.empty:
            band = y17
        target = pd.Timestamp("2017-06-15")
        i = band.index[int(np.argmin(np.abs((band.index - target).days)))]
        hitos.append({"fecha": i.strftime("%Y-%m-%d"), "score": float(y17.loc[i]),
                      "etiqueta": "2017: Pipo Score 60-75"})
    # Mar 2020: mínimo alrededor de marzo
    y20 = hdf.loc["2020-02-01":"2020-04-30", "score"].dropna()
    if not y20.empty:
        i = y20.idxmin()
        hitos.append({"fecha": i.strftime("%Y-%m-%d"), "score": float(y20.min()),
                      "etiqueta": "Mar 2020: Pipo Score ~5"})
    # Pisos 2022: mínimo 2022 donde score < 20
    y22 = hdf.loc["2022-01-01":"2022-12-31", "score"].dropna()
    if not y22.empty:
        i = y22.idxmin()
        hitos.append({"fecha": i.strftime("%Y-%m-%d"), "score": float(y22.min()),
                      "etiqueta": "Pisos 2022: Pipo Score < 20"})
    # Hoy
    hoy_lab = "Hoy"
    desde22 = hdf.loc["2022-01-01":, "score"].dropna()
    if not desde22.empty and float(out["score"]) <= float(desde22.min()) + 0.15:
        hoy_lab = "Hoy: el más profundo desde 2022"
    hitos.append({"fecha": fecha, "score": r1(out["score"]), "etiqueta": hoy_lab})

    block = {
        "actualizado": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fecha": fecha,
        "score": r1(out["score"]),
        "score_sin_fondeo": r1(out["score_sin_fondeo"]),
        "fondeo_pts": out["fondeo_pts"],
        "regimen": reg["regimen"],
        "titulo": reg["titulo"],
        "subtitulo": reg["subtitulo"],
        "al_proximo_regimen": reg["al_proximo_regimen"],
        "a_neutral": reg["a_neutral"],
        "x_base": r3(out["x_base"]),
        "x_fondeo": r3(out["x_fondeo"]),
        "x_total": r3(out["x_total"]),
        "n_entradas": out["n"],
        "correl_13s": r2(corr),
        "ndx_ultimo": r1(ndx_val) if ndx_val is not None else (r1(last.get("ndx")) if last.get("ndx") is not None else None),
        "ndx_fecha": ndx_fecha.strftime("%Y-%m-%d") if ndx_fecha is not None else None,
        "entradas": entradas,
        "fondeo": {
            "sofr_iorb_pb": r2(pb),
            "reservas_t": r3(res),
            "aporte_sofr_iorb": r2(out["aporte_sofr"]),
            "aporte_reservas": r2(out["aporte_reservas"]),
            "x_fondeo": r3(out["x_fondeo"]),
            "umbral_reservas_t": 3.00,
            "umbral_reservas_t_historico": r3(umbral_reservas(fecha)),
            "umbral_modelo": "10% del PBI nominal EE.UU. (BEA A191RC); 3,00 T desde 2026",
        },
        "escenarios": esc,
        "hitos": hitos,
        "fuentes": series_fuentes_list(series),
        "formula": "100 * Φ(X_base + X_fondeo), Φ = CDF normal estándar; X_base = promedio de z (3a) con signo; X_fondeo = −0,025·max(0, SOFR−IORB en pb) − max(0, umbral(t)−reservas_T); umbral(t)=10% del PBI nominal EE.UU. (BEA A191RC) y 3,00 T desde 2026; SOFR−IORB=0 antes del 3-abr-2018",
        "historia": [{"fecha": h["fecha"], "score": h["score"],
                      "score_sin_fondeo": h["score_sin_fondeo"], "ndx": h["ndx"]} for h in hist],
    }
    return block

def series_fuentes_list(series):
    out = []
    for k, (s, src, md) in series.items():
        if src:
            out.append(src)
    # unique preserve order
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x); uniq.append(x)
    return uniq

def compute_liquidez():
    series, fuentes = recolectar()
    block = construir(series)
    # fuentes recolectadas (intento) + las que realmente se usaron
    used = block.get("fuentes") or []
    block["fuentes"] = used or fuentes
    return block

def merge_into_mercado(block, path=None):
    path = path or os.path.abspath(OUT)
    try:
        data = json.load(open(path))
    except Exception:
        data = {}
    data["liquidez"] = block
    # no pisar actualizado global del tablero (es de precios)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    log("mercado.json actualizado con liquidez en", path)
    return path

def main(argv=None):
    argv = argv or sys.argv[1:]
    if "--test" in argv:
        test_formula()
        test_umbral_y_sofr()
        test_historia()
        return 0
    test_formula()
    test_umbral_y_sofr()
    block = compute_liquidez()
    log("SCORE", block["score"], "sin fondeo", block["score_sin_fondeo"],
        "fondeo_pts", block["fondeo_pts"], "régimen", block["regimen"],
        "fecha", block["fecha"], "N", block["n_entradas"],
        "NDX", block["ndx_ultimo"], "corr13", block["correl_13s"])
    for e in block["entradas"]:
        log(" ", e["id"], "z=", e["z"], "activo=", e["activo"], "valor=", e["valor"], "fecha=", e["fecha"], e.get("fuente"))
    log(" fondeo", block["fondeo"])
    test_historia(block.get("historia") or [])
    merge_into_mercado(block)
    # snapshot compacto por si hace falta
    snap = os.path.join(ROOT, "data", "historial", "liquidez-last.json")
    os.makedirs(os.path.dirname(snap), exist_ok=True)
    slim = {k: block[k] for k in block if k != "historia"}
    slim["historia_n"] = len(block["historia"])
    json.dump(slim, open(snap, "w"), ensure_ascii=False, indent=2)
    print(json.dumps({
        "score": block["score"], "score_sin_fondeo": block["score_sin_fondeo"],
        "fondeo_pts": block["fondeo_pts"], "regimen": block["regimen"],
        "fecha": block["fecha"], "n_entradas": block["n_entradas"],
        "ndx_ultimo": block["ndx_ultimo"], "correl_13s": block["correl_13s"],
        "x_base": block["x_base"], "x_fondeo": block["x_fondeo"],
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
