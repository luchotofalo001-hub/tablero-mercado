# Tablero de Mercado
Sitio estático (`site/`) + job gratis de GitHub Actions que corre `scripts/build_data.py` (yfinance, Wikipedia, Nasdaq) y publica en GitHub Pages.
Cada 30 min en rueda (solo publica) y 21:15 UTC después del cierre (publica y guarda `data/historial/`: scores, RS diario, Top 10 semanal, lista de CEDEARs).

## Publicar (una sola vez)
1. Crear un repo público en GitHub y subir esta carpeta.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → "Datos y publicación" → Run workflow. URL: `https://<usuario>.github.io/<repo>/`.

Local: `pip install yfinance pandas lxml requests && python scripts/build_data.py && python -m http.server -d site`

## Indicador de Liquidez (Pipo Score)
Página `site/liquidez.html` (también un resumen en el dashboard). El job `scripts/build_data.py` llama a `scripts/liquidez.py` y deja un bloque `liquidez` en `site/data/mercado.json`.

Solo el indicador: `python scripts/liquidez.py` (prueba de la fórmula: `python scripts/liquidez.py --test`).

Fuentes: FRED (si hay `FRED_API_KEY` o el CSV de FRED responde) y, si no, Fed H.4.1 / H.6 / H.10 / PRates, NY Fed (SOFR) y Yahoo Finance (^VIX, ^MOVE, ^NDX). STLFSI4 y el OAS de high yield dependen de FRED; si no están, quedan fuera del promedio y se pueden activar a mano en el simulador.
