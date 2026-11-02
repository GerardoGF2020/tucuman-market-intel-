"""Dashboard de Market Intelligence inmobiliario - Tucumán.

Ejecutar con:  streamlit run app.py
Dependencias:  pip install streamlit streamlit-folium folium pandas numpy
"""
import html
import os
import numpy as np
import pandas as pd
import folium
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Market Intelligence Tucumán", page_icon="🏠", layout="wide")

CENTER = (-26.8083, -65.2176)  # San Miguel de Tucumán
NEW_DAYS, OLD_DAYS = 7, 90
TIPO_LABEL = {"Casa": "Casa", "Depto": "Departamento", "Lote": "Lote", "Local": "Local comercial"}
CACHE_TTL = 300  # segundos: los datos se recargan cada 5 minutos
ARGENPROP_TIPO = {"Casa": "casas", "Depto": "departamentos", "Lote": "terrenos", "Local": "locales"}
CALLES = ["Av. Aconquija", "Av. Mate de Luna", "Av. Sarmiento", "Muñecas", "Laprida", "San Martín",
          "Av. Perón", "Lamadrid", "Av. Belgrano", "Av. Kirchner", "Marcos Paz", "Crisóstomo Álvarez"]
FUENTES_MOCK = {"Datos de prueba": ""}  # ficticia: no se muestra como inmobiliaria real
TIPOS = ["Casa", "Depto", "Lote", "Local"]

# Zonas (lat, lon, dispersión en grados, nombre)
ZONAS = [
    (-26.8241, -65.2226, 0.012, "Centro"),
    (-26.8083, -65.2176, 0.010, "Barrio Norte"),
    (-26.8400, -65.2000, 0.012, "Villa Luján"),
    (-26.8167, -65.3000, 0.012, "Yerba Buena"),
    (-26.7900, -65.2900, 0.010, "Yerba Buena Norte"),
    (-26.8300, -65.2600, 0.010, "Oeste"),
    (-26.7800, -65.2300, 0.010, "Norte"),
    (-26.8550, -65.2300, 0.010, "Sur"),
]


def _configurar_conexion():
    """Toma DATABASE_URL del entorno o de .streamlit/secrets.toml."""
    if os.getenv("DATABASE_URL"):
        return
    try:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    except Exception:
        pass


@st.cache_data(ttl=CACHE_TTL)
def load_data():
    """Punto único de carga. Devuelve (DataFrame, hora, origen, aviso).

    origen = 'real' (Supabase o base local de respaldo) o 'prueba' (datos ficticios).
    """
    _configurar_conexion()
    aviso = ""
    try:
        import database
        real = database.load_data()
        if len(real):
            es_supabase = os.getenv("DATABASE_URL", "").startswith("postgresql") and "pooler.supabase" in os.getenv("DATABASE_URL", "")
            fuente_desc = "Supabase (Nube)" if es_supabase else "Base local / Offline"
            return real, pd.Timestamp.now(), "real", fuente_desc
    except Exception as e:
        aviso = f"Aviso de conexión: {type(e).__name__}"

    # Respaldo garantizado de archivo cache_propiedades.csv
    cache_csv = os.path.join(os.path.dirname(__file__), "cache_propiedades.csv")
    if os.path.exists(cache_csv):
        try:
            real_cache = pd.read_csv(cache_csv).fillna("")
            if len(real_cache):
                return real_cache, pd.Timestamp.now(), "real", "Caché local verificada"
        except Exception:
            pass

    return generate_mock_data(), pd.Timestamp.now(), "prueba", (aviso or "No se encontraron propiedades reales.")


@st.cache_data
def generate_mock_data(n: int = 400, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        lat0, lon0, sd, zona = ZONAS[rng.integers(len(ZONAS))]
        lat, lon = lat0 + rng.normal(0, sd), lon0 + rng.normal(0, sd)
        tipo = rng.choice(TIPOS, p=[0.35, 0.35, 0.1, 0.2])
        op = rng.choice(["Venta", "Alquiler"], p=[0.65, 0.35])
        m2 = {"Casa": rng.integers(80, 350), "Depto": rng.integers(35, 140),
              "Lote": rng.integers(250, 1200), "Local": rng.integers(30, 250)}[tipo]
        if op == "Venta":
            usd_m2 = {"Casa": rng.normal(1100, 250), "Depto": rng.normal(1400, 300),
                      "Lote": rng.normal(180, 60), "Local": rng.normal(1300, 350)}[tipo]
            precio = max(usd_m2, 60) * m2
        else:
            precio = max(rng.normal(6, 1.5), 2) * m2 / (1 if tipo != "Lote" else 3)
            precio = max(precio, 120)
        moneda = rng.choice(["USD", "ARS"], p=[0.55, 0.45])
        dom = int(min(rng.exponential(45), 400))
        fuente = rng.choice(list(FUENTES_MOCK))
        rows.append({
            "id": i + 1,
            "lat": lat,
            "lon": lon,
            "direccion": f"{rng.choice(CALLES)} {rng.integers(100, 2900)}",
            "fuente": fuente, "fuente_url": FUENTES_MOCK[fuente],
            "zona": zona, "tipo": tipo, "operacion": op, "m2": int(m2),
            "precio_usd": round(float(precio), 0),
            "precio_m2_usd": round(float(precio) / m2, 1),
            "moneda_original": moneda, "dom": dom,
            # Datos de prueba: no existen publicaciones reales, por eso no hay enlaces.
            "url": "",
            "url_imagenes": "",
        })
    return pd.DataFrame(rows)


def color_for(dom: int) -> str:
    if dom < NEW_DAYS:
        return "green"
    if dom > OLD_DAYS:
        return "red"
    return "blue"


def _has(v) -> bool:
    """True si el dato existe (no es None/NaN/vacío)."""
    return isinstance(v, str) and v.strip() != ""


def popup_html(r) -> str:
    c = {"green": "#2e9e4f", "blue": "#2a6fdb", "red": "#d63a3a"}[color_for(r.dom)]
    # La dirección exacta y los links solo se muestran si el dato está disponible.
    ubic = r.zona
    if _has(getattr(r, "direccion", None)):
        ubic = f"{r.direccion}, {r.zona}"
    m2_tot = int(getattr(r, "m2_totales", 0) or getattr(r, "m2", 0) or 0)
    m2_cub = int(getattr(r, "m2_cubiertos", 0) or 0)
    tot_str = f"<b>{m2_tot:,} m²</b>" if m2_tot > 0 else "No informado"
    if m2_cub > 0:
        cub_str = f"<b>{m2_cub:,} m²</b>"
    elif getattr(r, "tipo", "") == "Lote":
        cub_str = "0 m² (Terreno)"
    else:
        cub_str = "No informado"
    fuente = ""
    if _has(getattr(r, "fuente", None)):
        nombre = html.escape(r.fuente)
        if _has(getattr(r, "fuente_url", None)):
            nombre = f'<a href="{r.fuente_url}" target="_blank" rel="noopener">{nombre}</a>'
        fuente = f'<span style="color:#777;">🏢 Fuente: {nombre}</span><br>'
    links = ""
    if _has(getattr(r, "url", None)):
        links += f'<a href="{r.url}" target="_blank" rel="noopener">🔗 Ver publicación original</a><br>'
    if _has(getattr(r, "url_imagenes", None)):
        links += f'<a href="{r.url_imagenes}" target="_blank" rel="noopener">🖼️ Ver imágenes</a>'
    return f"""
    <div style="font-family:Arial,sans-serif;width:255px;">
      <div style="background:{c};color:#fff;padding:8px 10px;border-radius:6px 6px 0 0;
                  font-weight:bold;font-size:14px;">
        {TIPO_LABEL[r.tipo]} en {r.operacion}
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:10px;border-radius:0 0 6px 6px;
                  font-size:13px;line-height:1.6;">
        📍 {ubic}<br>
        📏 M² Totales (Propiedad): {tot_str}<br>
        🏗️ M² Construidos: {cub_str}<br>
        💵 <b>USD {r.precio_usd:,.0f}</b><br>
        📐 USD {r.precio_m2_usd:,.1f} / m²<br>
        ⏱️ Días en el mercado: <b>{r.dom}</b><br>
        <span style="color:#777;">Moneda original: {r.moneda_original}</span><br>
        {fuente}
        {links}
      </div>
    </div>"""


df, last_update, origen, aviso = load_data()
df["canal"] = np.where(
    df["fuente"].fillna("").str.contains(r"\(IG\)", case=False, regex=True)
    | df["url"].fillna("").str.contains("instagram.com", case=False),
    "Instagram",
    "Web Oficial",
)

# ---------------- Sidebar ----------------
if origen == "real":
    n_ig = int((df["canal"] == "Instagram").sum())
    n_web = int((df["canal"] == "Web Oficial").sum())
    tag_fuente = f" ({aviso})" if aviso else ""
    st.sidebar.success(f"✅ Datos reales{tag_fuente}: {len(df)} prop. ({n_web} Web · {n_ig} IG)")
else:
    st.sidebar.warning(f"⚠️ DATOS DE PRUEBA (ficticios). {aviso}")
st.sidebar.caption(f"🕒 Última actualización: {last_update:%d/%m/%Y %H:%M:%S}  \nSe actualiza cada {CACHE_TTL // 60} min")
if st.sidebar.button("🔄 Actualizar ahora"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.header("🔎 Filtros")
canales_sel = st.sidebar.multiselect(
    "📡 Canal de origen",
    ["Web Oficial", "Instagram"],
    default=["Web Oficial", "Instagram"],
)
ops = st.sidebar.multiselect("Operación", ["Venta", "Alquiler"], default=["Venta", "Alquiler"])
tipos = st.sidebar.multiselect("Tipo", TIPOS, default=TIPOS)

st.sidebar.subheader("📍 Filtro por Barrio / Zona")
zonas_disp = sorted(df.zona.fillna("Sin zona").replace("", "Sin zona").unique())
zonas_sel = st.sidebar.multiselect("Barrio / Localidad", zonas_disp, default=zonas_disp)

st.sidebar.subheader("💵 Filtro por Precio (USD)")
pmin, pmax = int(df.precio_usd.min()), max(int(df.precio_usd.max()), int(df.precio_usd.min()) + 1)
col_p1, col_p2 = st.sidebar.columns(2)
precio_min_in = col_p1.number_input("Mínimo USD", min_value=0, max_value=pmax, value=pmin, step=1000)
precio_max_in = col_p2.number_input("Máximo USD", min_value=0, max_value=pmax, value=pmax, step=5000)
rango = st.sidebar.slider(
    "Rango de precio (USD)",
    pmin,
    pmax,
    (min(int(precio_min_in), int(precio_max_in)), max(int(precio_min_in), int(precio_max_in))),
    step=500,
)

st.sidebar.subheader("📏 Superficie Total (m²)")
m2_max_db = max(int(df.m2.max()), 100)
rango_m2 = st.sidebar.slider("Rango de m² totales (0 = incluye sin dato)", 0, m2_max_db, (0, m2_max_db), step=10)
monedas = st.sidebar.multiselect("Moneda original", ["USD", "ARS"], default=["USD", "ARS"])

fuentes_disp = sorted(df.fuente.replace("", "Sin fuente").unique())
fuentes_sel = st.sidebar.multiselect("Inmobiliaria / fuente", fuentes_disp, default=fuentes_disp)
with st.sidebar.expander("🏢 Inmobiliarias en el mapa", expanded=True):
    resumen = df.fuente.replace("", "Sin fuente").value_counts().rename_axis("Inmobiliaria").reset_index(name="Propiedades")
    st.dataframe(resumen, hide_index=True, use_container_width=True)

with st.sidebar.expander("📸 Inyectar posteo de Instagram", expanded=False):
    ig_cuenta = st.text_input("Usuario Instagram", value="@inmobiliaria.wainer")
    ig_url = st.text_input("URL del posteo (opcional)", placeholder="https://www.instagram.com/p/...")
    ig_texto = st.text_area(
        "Descripción del posteo (caption)",
        placeholder="Ej: Casa en venta en Yerba Buena, terreno 574 m2, 250 m2 cubiertos. Precio USD 185.000",
    )
    if st.button("🚀 Extraer e Inyectar a Supabase"):
        if ig_texto.strip():
            from scraper_instagram import parsear_caption_instagram
            from scraper_web import geocodificar
            import database as db_mod

            ext = parsear_caption_instagram(ig_texto)
            if not ext.get("tipo") or not ext.get("precio"):
                st.error("No se detectó tipo de inmueble o precio numérico en el texto.")
            else:
                u_clean = ig_cuenta.strip().lstrip("@") or "instagram"
                post_url = ig_url.strip() or f"https://www.instagram.com/{u_clean}/?post={abs(hash(ig_texto)) % 100000}"
                lat, lon, prec = geocodificar(ext.get("direccion"), ext.get("ubicacion_zona"), None)
                est = db_mod.upsert_propiedad({
                    "url": post_url,
                    "tipo": ext["tipo"],
                    "operacion": ext["operacion"],
                    "precio": ext["precio"],
                    "moneda": ext["moneda"],
                    "zona": ext["ubicacion_zona"],
                    "direccion": ext.get("direccion"),
                    "latitud": lat,
                    "longitud": lon,
                    "m2_totales": ext.get("m2_totales"),
                    "m2_cubiertos": ext.get("m2_cubiertos"),
                    "fuente": f"{u_clean.title()} (IG)",
                    "fuente_url": f"https://www.instagram.com/{u_clean}/",
                    "actualizar_geo": prec != "zona",
                })
                st.success(f"Guardado ({est}): {ext['tipo'].title()} · {ext['moneda']} {ext['precio']:,.0f} · Total: {ext.get('m2_totales')} m² | Constr.: {ext.get('m2_cubiertos')} m²")
                st.cache_data.clear()
                st.rerun()

f = df[
    df.canal.isin(canales_sel)
    & df.operacion.isin(ops)
    & df.tipo.isin(tipos)
    & df.zona.fillna("Sin zona").replace("", "Sin zona").isin(zonas_sel)
    & df.moneda_original.isin(monedas)
    & df.precio_usd.between(*rango)
    & df.m2.between(*rango_m2)
    & df.fuente.replace("", "Sin fuente").isin(fuentes_sel)
]

# ---------------- Main ----------------
st.title("🏠 Market Intelligence Inmobiliario – Tucumán")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Propiedades", len(f))
c2.metric("Precio mediano (USD)", f"{f.precio_usd.median():,.0f}" if len(f) else "–")
c3.metric("USD/m² mediano", f"{f.precio_m2_usd.median():,.0f}" if len(f) else "–")
c4.metric("DOM mediano", f"{f.dom.median():.0f}" if len(f) else "–")

m = folium.Map(location=CENTER, zoom_start=12, tiles="OpenStreetMap")
vistos_coord: dict[tuple[float, float], int] = {}
for r in f.itertuples():
    es_ig = getattr(r, "canal", "") == "Instagram"
    col = "purple" if es_ig else color_for(r.dom)
    icono = "camera" if es_ig else "home"

    # Evita que dos propiedades con la misma coordenada de zona se tapen entre sí
    clave_c = (round(float(r.lat), 4), round(float(r.lon), 4))
    idx_c = vistos_coord.get(clave_c, 0)
    vistos_coord[clave_c] = idx_c + 1
    if idx_c > 0:
        angulo = idx_c * 2.39996  # ángulo áureo en radianes para dispersión uniforme
        radio = 0.0014 * np.sqrt(idx_c)
        lat_pin = float(r.lat) + radio * float(np.cos(angulo))
        lon_pin = float(r.lon) + radio * float(np.sin(angulo))
    else:
        lat_pin, lon_pin = float(r.lat), float(r.lon)

    m2_pin = int(getattr(r, "m2_totales", 0) or getattr(r, "m2", 0) or 0)
    m2_cub_pin = int(getattr(r, "m2_cubiertos", 0) or 0)
    m2_badge = f"Total: {m2_pin:,} m² | Constr.: {m2_cub_pin:,} m²" if m2_pin > 0 else "s/d m²"
    prefijo_ig = "📸 [IG] " if es_ig else ""
    folium.Marker(
        [lat_pin, lon_pin],
        popup=folium.Popup(popup_html(r), max_width=275),
        tooltip=f"{prefijo_ig}{TIPO_LABEL[r.tipo]} · USD {r.precio_usd:,.0f} · 📏 {m2_badge}",
        icon=folium.Icon(color=col, icon=icono, prefix="fa"),
    ).add_to(m)

legend = f"""
<div style="position:fixed;bottom:25px;left:25px;z-index:9999;background:#fff;padding:8px 12px;
            border:1px solid #888;border-radius:6px;font-size:12px;">
<span style="color:#2e9e4f;">●</span> Nueva (&lt;{NEW_DAYS} días)<br>
<span style="color:#2a6fdb;">●</span> Activa (Web)<br>
<span style="color:#d63a3a;">●</span> Antigua (&gt;{OLD_DAYS} días)<br>
<span style="color:#9c27b0;">●</span> 📸 Publicación de Instagram</div>"""
m.get_root().html.add_child(folium.Element(legend))

st_folium(m, use_container_width=True, height=620, returned_objects=[])

st.subheader("📋 Planilla de propiedades filtradas")
tabla = f.drop(columns=["lat", "lon", "fuente_url", "m2"], errors="ignore").sort_values("dom").rename(columns={
    "m2_totales": "M² Totales (Terreno/Prop.)", "m2_cubiertos": "M² Cubiertos",
    "precio_usd": "Precio USD", "precio_m2_usd": "USD/m²", "dom": "DOM (días)",
    "moneda_original": "Moneda orig.", "fuente": "Fuente", "direccion": "Dirección", "operacion": "Operación", "tipo": "Tipo",
    "url": "Publicación", "url_imagenes": "Imágenes"})
st.dataframe(
    tabla, use_container_width=True, hide_index=True,
    column_config={
        "Publicación": st.column_config.LinkColumn("Publicación", display_text="Ver publicación"),
        "Imágenes": st.column_config.LinkColumn("Imágenes", display_text="Ver imágenes"),
        "Precio USD": st.column_config.NumberColumn(format="%d"),
    },
)
st.download_button("⬇️ Descargar CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                   "propiedades_tucuman.csv", "text/csv")

