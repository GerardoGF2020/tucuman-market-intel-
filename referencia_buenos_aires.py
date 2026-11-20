"""Genera referencia_buenos_aires.csv: muestra de precios de VENTA en USD del portal
deinmobiliarios (CABA / GBA) para comparar contra Tucumán en la app.

IMPORTANTE: es un archivo APARTE. Estas propiedades NO se cargan en la base de Tucumán
ni en el mapa. Solo usa listados públicos (no usa /property/markers, prohibido por robots.txt).

Uso:  python referencia_buenos_aires.py [--max-paginas 80]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import scraper_web as sw  # noqa: E402

BASE = "https://propiedades.deinmobiliarios.com"
SALIDA = BASE_DIR / "referencia_buenos_aires.csv"
ETIQUETA = {"casa": "Casa", "depto": "Depto", "lote": "Lote", "local": "Local"}


def grupo(region: str) -> str:
    r = (region or "").lower()
    if r.startswith("capital federal"):
        return "CABA"
    if "g.b.a" in r:
        return "GBA"
    return "Interior BA"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-paginas", type=int, default=80)
    args = ap.parse_args()

    filas, vistas = [], set()
    for pagina in range(1, args.max_paginas + 1):
        url = f"{BASE}/propiedades/todas/venta" + (f"?page={pagina}" if pagina > 1 else "")
        print(f"> {url}")
        html = sw._get_html_remax(url)
        if not html:
            break
        items = [i for i in sw.parsear_listado_deinmobiliarios(html) if i["url"] and i["url"] not in vistas]
        if not items:
            break
        for it in items:
            vistas.add(it["url"])
            if it["tipo"] not in ETIQUETA or it["moneda"] != "USD":
                continue
            if it["precio"] <= 0 or it["m2"] <= 10:
                continue
            filas.append({
                "grupo": grupo(it["region"]),
                "region": it["region"],
                "localidad": it["localidad"],
                "tipo": ETIQUETA[it["tipo"]],
                "m2": it["m2"],
                "precio_usd": it["precio"],
                "precio_m2_usd": round(it["precio"] / it["m2"], 1),
                "url": it["url"],
            })

    df = pd.DataFrame(filas)
    if df.empty:
        print("Sin datos: no se sobrescribe el archivo anterior.")
        return
    df["fecha_muestra"] = datetime.now().strftime("%d/%m/%Y")
    df.to_csv(SALIDA, index=False, encoding="utf-8-sig")
    print(f"OK: {len(df)} avisos de referencia -> {SALIDA}")
    print(df.groupby(["grupo", "tipo"])["precio_m2_usd"].agg(["count", "median"]))


if __name__ == "__main__":
    main()
