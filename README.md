# Tablero de Mercado
Sitio estático (`site/`) + job gratis de GitHub Actions que corre `scripts/build_data.py` (yfinance, Wikipedia, Nasdaq) y publica en GitHub Pages.
Cada 30 min en rueda y 21:15 UTC después del cierre (lun–vie).

## Publicar (una sola vez)
1. Crear un repo público en GitHub y subir esta carpeta.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → "Datos y publicación" → Run workflow. URL: `https://<usuario>.github.io/<repo>/`.

Local: `pip install yfinance pandas lxml requests && python scripts/build_data.py && python -m http.server -d site`
