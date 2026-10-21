# Catálogo de bonos y letras soberanas argentinas para la app Finanzas.
# Fuentes gratuitas: data912 (qué cotiza), BYMA Open Data (ficha técnica: emisión, vencimiento, interés, amortización), BCRA (CER base).
# Los curados a mano (scripts/bonos-base.json) mandan. Salida: site/data/bonos-catalogo.json
import json, re, datetime as dt, urllib.request, ssl, time, os
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE   # open.bymadata usa una cadena incompleta
BY = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/bnown/fichatecnica/especies/general"
def get(u, data=None):
    r = urllib.request.Request(u, data=data, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(r, timeout=30, context=CTX).read())
MES = {m: i + 1 for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())}
def fechas(txt):
    out = []
    for d, m, y in re.findall(r"(\d{1,2}) de (\w+) (?:de |del )?(\d{4})", txt.lower()):
        if m in MES: out.append(f"{int(y):04d}-{MES[m]:02d}-{int(d):02d}")
    return out
def habiles_antes(f, n):
    d = dt.date.fromisoformat(f)
    while n:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d.isoformat()
_cer = None
def cer_en(f):
    global _cer
    if _cer is None:
        _cer = []
        y = 2016
        while y <= dt.date.today().year:
            j = get(f"https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/30?desde={y}-01-01&hasta={y}-12-31&limit=3000")
            _cer += [(x["fecha"][:10], x["valor"]) for x in j["results"][0]["detalle"]]; y += 1
        _cer.sort()
    v = None
    for d, x in _cer:
        if d <= f: v = x
        else: break
    return v
def pct(txt):
    m = re.search(r"(\d+(?:,\d+)?)\s*%", txt); return float(m.group(1).replace(",", ".")) if m else None
def parse(t, f):
    den = (f.get("denominacion") or "").upper(); it = f.get("interes") or ""; am = f.get("formaAmortizacion") or ""
    em = (f.get("fechaEmision") or "")[:10]; vto = (f.get("fechaVencimiento") or "")[:10]
    if not vto: return None
    b = {"t": t, "n": den.title()[:90], "emision": em, "vto": vto, "fuente": "BYMA", "lote": f.get("denominacionMinima") or 1}
    usd = (f.get("moneda") or "").startswith("D")
    if "VINCULAD" in den: b.update(tipo="DL", tasas=[], amort=[{"f": vto, "p": 100}]); return b
    if "DUAL" in den or "TAMAR" in den:
        b.update(tipo="LECAP", tem=pct(it) or 2.0, estimado=True, nota="Paga el máximo entre tasa fija y TAMAR (o TAMAR): se estima con tasa fija" if "DUAL" in den else "Tasa TAMAR variable: se estima con 2% mensual"); return b
    if "CAPITALIZABLE" in den: b.update(tipo="LECAP", tem=pct(it)); b["estimado"] = b["tem"] is None; return b
    cer = "CER" in den
    if cer:
        base = cer_en(habiles_antes(em, 10)) if em else None
        b["cerBase"] = round(base, 4) if base else None
        if not base: b["estimado"] = True
    if "CERO CUP" in den or "DESCUENTO" in den or "descuento" in it.lower():
        b.update(tipo="CER" if cer else ("USD" if usd else "TF"), tasas=[], amort=[{"f": vto, "p": 100}]); return b
    r = pct(it); b["tipo"] = "CER" if cer else ("USD" if usd else "TF")
    b["tasas"] = [{"d": em, "t": r or 0}]
    fi = [x for x in fechas(it) if em < x <= vto]
    if len(fi) >= 2: b["fechas"] = sorted(set(fi))
    else: b["freq"] = 1 if "mes vencid" in it.lower() or "mensual" in it.lower() else 3 if "trimestr" in it.lower() else 6
    fa = [x for x in fechas(am) if em < x <= vto]
    m = re.search(r"(\d+)\s+cuotas", am)
    if m and len(fa) >= 2 and int(m.group(1)) == len(fa): b["amort"] = [{"f": x, "p": round(100 / len(fa), 6)} for x in fa]
    elif m and fa:   # "N cuotas semestrales ... comenzando el <fecha>"
        n = int(m.group(1)); d = dt.date.fromisoformat(fa[0]); out = []
        for k in range(n):
            mm = d.month - 1 + 6 * k; y = d.year + mm // 12; mo = mm % 12 + 1
            import calendar; out.append({"f": f"{y:04d}-{mo:02d}-{min(d.day, calendar.monthrange(y, mo)[1]):02d}", "p": round(100 / n, 6)})
        b["amort"] = out
    else: b["amort"] = [{"f": vto, "p": 100}]
    if r is None or "capitaliz" in it.lower() or ("cuotas" in am and "amort" not in b): b["estimado"] = True
    return b
def main():
    base = json.load(open(os.path.join(os.path.dirname(__file__), "bonos-base.json")))
    cur = {b["t"]: b for b in base}
    syms = sorted({x["symbol"] for u in ("arg_bonds", "arg_notes") for x in get("https://data912.com/live/" + u)})
    porIsin, fichas = {}, {}
    for s in syms:
        try: d = get(BY, json.dumps({"symbol": s}).encode()).get("data") or []
        except Exception: d = []
        time.sleep(0.15)
        if not d: continue
        f = d[0]; fichas[s] = f; porIsin.setdefault(f.get("codigoIsin") or s, []).append(s)
    out, alias = {}, {}
    for isin, ss in porIsin.items():
        f = fichas[ss[0]]
        if re.match(r"TVP", ss[0]) or "PBI" in (f.get("denominacion") or "").upper(): continue   # cupones PBI: no son bonos
        if f.get("emisor") not in ("Gobierno Nacional", "Banco Central de la República Argentina", "BCRA") and "BOPREAL" not in (f.get("denominacion") or "").upper(): continue   # solo soberanos (y BOPREAL)
        cand = sorted(ss, key=lambda s: (s[-1] in "DC", len(s), s))   # el ticker en pesos (sin D/C) es la base
        t = next((s for s in cand if s in cur), cand[0])
        b = dict(cur[t]) if t in cur else parse(t, f)
        if b and t in ("PAY0", "PAP0", "DIP0"): b["estimado"] = True
        if not b: continue
        b["isin"] = isin
        al = [s for s in ss if s != t and not (s[:-1] == t and s[-1] in "DC")]
        if al: b["alias"] = al
        out[t] = b
    for t, b in cur.items(): out.setdefault(t, b)
    cat = {"version": dt.date.today().isoformat(), "fuente": "data912 (cotizan) + BYMA Open Data (fichas) + BCRA (CER base) + curados", "bonos": sorted(out.values(), key=lambda b: b["t"])}
    os.makedirs("site/data", exist_ok=True)
    json.dump(cat, open("site/data/bonos-catalogo.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(len(cat["bonos"]), "bonos;", sum(1 for b in cat["bonos"] if b.get("estimado")), "estimados")
if __name__ == "__main__": main()
