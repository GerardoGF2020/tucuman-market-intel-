"""Capa de acceso a datos (PostgreSQL / Supabase) - Market Intelligence Tucumán.

Dependencias:  pip install sqlalchemy psycopg2-binary pandas

Configuración (variables de entorno):
    DATABASE_URL  Cadena de conexión. En Supabase: Project Settings > Database >
                  Connection string (URI). Ejemplo:
                  postgresql+psycopg2://postgres:CLAVE@db.xxxx.supabase.co:5432/postgres?sslmode=require
    USD_ARS       (opcional) Tipo de cambio por defecto para estandarizar precios en ARS.
                  También se puede pasar `tipo_cambio` en cada llamada a upsert_propiedad.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_USD_ARS = float(os.getenv("USD_ARS", "1200"))


# ---------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------
def _get_sqlite_engine() -> Engine:
    """Devuelve un engine apuntando directamente a tucuman_local.db asegurando la estructura."""
    sqlite_path = os.path.join(os.path.dirname(__file__), "tucuman_local.db")
    eng_local = create_engine(f"sqlite:///{sqlite_path}", future=True)
    with eng_local.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS propiedades (
                id TEXT PRIMARY KEY,
                tipo TEXT NOT NULL,
                operacion TEXT NOT NULL,
                direccion TEXT,
                zona TEXT,
                latitud REAL,
                longitud REAL,
                m2_totales REAL,
                m2_cubiertos REAL,
                habitaciones INTEGER,
                url TEXT UNIQUE NOT NULL,
                url_imagenes TEXT,
                fuente TEXT,
                fuente_url TEXT,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS historial_estado (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                propiedad_id TEXT NOT NULL REFERENCES propiedades(id) ON DELETE CASCADE,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                precio NUMERIC(15, 2) NOT NULL,
                moneda TEXT NOT NULL,
                precio_usd NUMERIC(15, 2) NOT NULL,
                publicado_en_dolares BOOLEAN NOT NULL,
                estado TEXT NOT NULL DEFAULT 'activa'
            )
        """))
    return eng_local


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Crea (una sola vez) el engine de SQLAlchemy.
    Si Supabase está pausado o el Wi-Fi bloquea el puerto 5432, usa SQLite local (tucuman_local.db) automáticamente.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        secrets_file = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_file):
            for line in open(secrets_file, encoding="utf-8"):
                if line.strip().startswith("DATABASE_URL"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        url = parts[1].strip().strip('"').strip("'")
                        os.environ["DATABASE_URL"] = url
                        break
    if url and url.startswith("postgresql"):
        try:
            eng = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3}, future=True)
            with eng.connect() as c:
                c.execute(text("SELECT 1"))
            return eng
        except Exception:
            pass
    return _get_sqlite_engine()


def init_db(schema_path: str = "schema.sql") -> None:
    """Crea las tablas ejecutando schema.sql (idempotente)."""
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with get_engine().begin() as conn:
        conn.exec_driver_sql(sql)


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def generar_id(url: str) -> str:
    """ID único de la propiedad: SHA-256 de la URL normalizada."""
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()


def _a_usd(precio: float, moneda: str, tipo_cambio: float) -> float:
    """Estandariza un precio a USD."""
    return float(precio) if moneda == "USD" else float(precio) / tipo_cambio


# ---------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------
def upsert_propiedad(datos: dict, tipo_cambio: float | None = None) -> str:
    """Inserta la propiedad si es nueva o agrega un registro al historial si cambió.

    `datos` (claves):
        obligatorias: url, tipo ('casa'|'depto'|'lote'|'local'), operacion ('venta'|'alquiler'),
                      precio, moneda ('USD'|'ARS')
        opcionales:   direccion, zona, latitud, longitud, m2_totales, m2_cubiertos,
                      habitaciones, url_imagenes, fuente (nombre de la
                      inmobiliaria/portal), fuente_url (sitio web de la fuente),
                      actualizar_geo (bool: reemplaza lat/lon ya guardadas),
                      publicado_en_dolares (bool),
                      estado ('activa'|'dada_de_baja', por defecto 'activa')

    Devuelve: 'nueva' | 'actualizada' | 'sin_cambios'.
    """
    tc = tipo_cambio or DEFAULT_USD_ARS
    pid = generar_id(datos["url"])
    moneda = datos["moneda"].upper()
    estado = datos.get("estado", "activa")
    precio = Decimal(str(datos["precio"]))
    en_dolares = datos.get("publicado_en_dolares", moneda == "USD")

    with get_engine().begin() as conn:  # transacción: todo o nada
        # 1) Propiedad: se inserta si no existe. Si existe, solo se completan
        #    datos estáticos que antes estaban vacíos (COALESCE no pisa lo ya cargado).
        existia = conn.execute(
            text("SELECT 1 FROM propiedades WHERE id = :id"), {"id": pid}
        ).first() is not None

        conn.execute(
            text("""
                INSERT INTO propiedades
                    (id, tipo, operacion, direccion, zona, latitud, longitud,
                     m2_totales, m2_cubiertos, habitaciones, url, url_imagenes, fuente, fuente_url)
                VALUES
                    (:id, :tipo, :operacion, :direccion, :zona, :latitud, :longitud,
                     :m2_totales, :m2_cubiertos, :habitaciones, :url, :url_imagenes,
                     :fuente, :fuente_url)
                ON CONFLICT (id) DO UPDATE SET
                    direccion    = COALESCE(propiedades.direccion,    EXCLUDED.direccion),
                    zona         = COALESCE(propiedades.zona,         EXCLUDED.zona),
                    -- con actualizar_geo=True las coordenadas nuevas (más precisas) reemplazan a las guardadas
                    latitud      = CASE WHEN :actualizar_geo THEN COALESCE(EXCLUDED.latitud,  propiedades.latitud)
                                        ELSE COALESCE(propiedades.latitud,  EXCLUDED.latitud) END,
                    longitud     = CASE WHEN :actualizar_geo THEN COALESCE(EXCLUDED.longitud, propiedades.longitud)
                                        ELSE COALESCE(propiedades.longitud, EXCLUDED.longitud) END,
                    m2_totales   = COALESCE(EXCLUDED.m2_totales,   propiedades.m2_totales),
                    m2_cubiertos = COALESCE(EXCLUDED.m2_cubiertos, propiedades.m2_cubiertos),
                    habitaciones = COALESCE(propiedades.habitaciones, EXCLUDED.habitaciones),
                    url_imagenes = COALESCE(propiedades.url_imagenes, EXCLUDED.url_imagenes),
                    fuente       = COALESCE(propiedades.fuente,       EXCLUDED.fuente),
                    fuente_url   = COALESCE(propiedades.fuente_url,   EXCLUDED.fuente_url)
            """),
            {
                "id": pid,
                "tipo": datos["tipo"].lower(),
                "operacion": datos["operacion"].lower(),
                "direccion": datos.get("direccion"),
                "zona": datos.get("zona"),
                "latitud": datos.get("latitud"),
                "longitud": datos.get("longitud"),
                "m2_totales": datos.get("m2_totales"),
                "m2_cubiertos": datos.get("m2_cubiertos"),
                "habitaciones": datos.get("habitaciones"),
                "url": datos["url"].strip(),
                "url_imagenes": datos.get("url_imagenes"),
                "fuente": datos.get("fuente"),
                "fuente_url": datos.get("fuente_url"),
                "actualizar_geo": bool(datos.get("actualizar_geo", False)),
            },
        )

        # 2) Último estado conocido, para detectar cambios
        ultimo = conn.execute(
            text("""
                SELECT precio, moneda, estado
                FROM historial_estado
                WHERE propiedad_id = :id
                ORDER BY fecha_registro DESC, id DESC
                LIMIT 1
            """),
            {"id": pid},
        ).first()

        if ultimo and (Decimal(str(ultimo.precio)), ultimo.moneda.strip(), ultimo.estado) == (
            precio, moneda, estado
        ):
            return "sin_cambios"

        # 3) Nuevo registro en el historial (primera aparición o cambio)
        conn.execute(
            text("""
                INSERT INTO historial_estado
                    (propiedad_id, precio, moneda, precio_usd, publicado_en_dolares, estado)
                VALUES (:id, :precio, :moneda, :precio_usd, :en_dolares, :estado)
            """),
            {
                "id": pid,
                "precio": float(precio),
                "moneda": moneda,
                "precio_usd": round(_a_usd(precio, moneda, tc), 2),
                "en_dolares": en_dolares,
                "estado": estado,
            },
        )
        return "actualizada" if existia else "nueva"


def marcar_bajas_fuente(fuente: str, urls_vistas: set[str]) -> int:
    """Marca como 'dada_de_baja' las propiedades ACTIVAS de una fuente que ya no aparecen en el sitio.

    Llamar solo después de un scraping COMPLETO de esa fuente (todas las páginas), porque
    todo lo que no esté en `urls_vistas` se considera retirado. Devuelve cuántas se dieron de baja.
    """
    if not urls_vistas:
        return 0  # seguridad: un scraping vacío (sitio caído) no debe dar de baja todo
    with get_engine().begin() as conn:
        res = conn.execute(
            text("""
                INSERT INTO historial_estado
                    (propiedad_id, precio, moneda, precio_usd, publicado_en_dolares, estado)
                SELECT u.propiedad_id, u.precio, u.moneda, u.precio_usd, u.publicado_en_dolares,
                       'dada_de_baja'
                FROM (
                    SELECT DISTINCT ON (h.propiedad_id)
                           h.propiedad_id, h.precio, h.moneda, h.precio_usd,
                           h.publicado_en_dolares, h.estado
                    FROM historial_estado h
                    JOIN propiedades p ON p.id = h.propiedad_id
                    WHERE p.fuente = :fuente AND NOT (p.url = ANY(:urls))
                    ORDER BY h.propiedad_id, h.fecha_registro DESC, h.id DESC
                ) u
                WHERE u.estado = 'activa'
            """),
            {"fuente": fuente, "urls": list(urls_vistas)},
        )
        return res.rowcount


def marcar_dada_de_baja(url: str) -> bool:
    """Registra que un aviso ya no está online (conserva el último precio)."""
    pid = generar_id(url)
    with get_engine().begin() as conn:
        res = conn.execute(
            text("""
                INSERT INTO historial_estado
                    (propiedad_id, precio, moneda, precio_usd, publicado_en_dolares, estado)
                SELECT propiedad_id, precio, moneda, precio_usd, publicado_en_dolares, 'dada_de_baja'
                FROM historial_estado
                WHERE propiedad_id = :id
                ORDER BY fecha_registro DESC, id DESC
                LIMIT 1
            """),
            {"id": pid},
        )
        return res.rowcount > 0


# ---------------------------------------------------------------------
# Lectura (para app.py)
# ---------------------------------------------------------------------
_QUERY_ACTUAL = """
WITH rankeado AS (
    SELECT propiedad_id, fecha_registro, precio, moneda, precio_usd, estado,
           ROW_NUMBER() OVER (PARTITION BY propiedad_id ORDER BY fecha_registro DESC, id DESC) AS rn
    FROM historial_estado
),
ultimo AS (
    SELECT propiedad_id, fecha_registro, precio, moneda, precio_usd, estado
    FROM rankeado
    WHERE rn = 1
),
primero AS (
    SELECT propiedad_id, MIN(fecha_registro) AS primera_fecha
    FROM historial_estado
    GROUP BY propiedad_id
)
SELECT p.id, p.latitud AS lat, p.longitud AS lon, p.zona, p.direccion,
       p.tipo, p.operacion,
       p.m2_totales, p.m2_cubiertos,
       COALESCE(p.m2_totales, p.m2_cubiertos) AS m2,
       u.precio_usd, u.moneda AS moneda_original, u.estado,
       pr.primera_fecha, u.fecha_registro AS ultima_fecha,
       p.url, p.url_imagenes, p.fuente, p.fuente_url
FROM propiedades p
JOIN ultimo  u  ON u.propiedad_id  = p.id
JOIN primero pr ON pr.propiedad_id = p.id
WHERE p.latitud IS NOT NULL AND p.longitud IS NOT NULL
  AND u.precio_usd IS NOT NULL
  AND (:solo_activas = FALSE OR u.estado = 'activa')
"""

_TIPO_LABEL = {"casa": "Casa", "depto": "Depto", "lote": "Lote", "local": "Local"}
_OPERACION_LABEL = {"venta": "Venta", "alquiler": "Alquiler"}


def load_data(solo_activas: bool = True) -> pd.DataFrame:
    """Devuelve un DataFrame con las columnas que espera app.py:

    id, lat, lon, zona, direccion, tipo, operacion, m2, precio_usd, precio_m2_usd,
    moneda_original, dom, url, url_imagenes, fuente, fuente_url

    DOM (días en el mercado) = fecha de referencia - primera aparición, donde la
    fecha de referencia es HOY si la propiedad sigue activa, o su último registro
    si fue dada de baja (así una propiedad activa que no cambió de precio hace
    semanas no queda con un DOM artificialmente bajo).
    """
    cache_csv = os.path.join(os.path.dirname(__file__), "cache_propiedades.csv")
    df = None
    try:
        with get_engine().connect() as conn:
            df = pd.read_sql(text(_QUERY_ACTUAL), conn, params={"solo_activas": solo_activas})
    except Exception:
        # Fallback inmediato a SQLite local
        try:
            get_engine.cache_clear()
            with _get_sqlite_engine().connect() as conn:
                df = pd.read_sql(text(_QUERY_ACTUAL), conn, params={"solo_activas": solo_activas})
        except Exception:
            pass

    if df is None or df.empty:
        if os.path.exists(cache_csv):
            try:
                df_cache = pd.read_csv(cache_csv).fillna({"direccion": "", "url": "", "url_imagenes": "", "fuente": "", "fuente_url": ""})
                if not df_cache.empty:
                    return df_cache
            except Exception:
                pass
        if df is None:
            return pd.DataFrame(columns=[
                "id", "lat", "lon", "zona", "direccion", "tipo", "operacion", "m2", "precio_usd",
                "precio_m2_usd", "moneda_original", "dom", "url", "url_imagenes", "fuente", "fuente_url"])

    if df.empty:
        return pd.DataFrame(columns=[
            "id", "lat", "lon", "zona", "direccion", "tipo", "operacion", "m2", "precio_usd",
            "precio_m2_usd", "moneda_original", "dom", "url", "url_imagenes", "fuente", "fuente_url"])

    ahora = pd.Timestamp(datetime.now(timezone.utc))
    primera = pd.to_datetime(df["primera_fecha"], utc=True)
    ultima = pd.to_datetime(df["ultima_fecha"], utc=True)
    fin = ultima.where(df["estado"] != "activa", ahora)
    df["dom"] = (fin - primera).dt.days.clip(lower=0).astype(int)

    # Tipos numéricos (Postgres devuelve Decimal) y valores derivados
    df["precio_usd"] = df["precio_usd"].astype(float).round(0)
    df["m2"] = pd.to_numeric(df["m2"], errors="coerce")
    df["m2_totales"] = pd.to_numeric(df["m2_totales"], errors="coerce").fillna(df["m2"]).fillna(0).round().astype(int)
    df["m2_cubiertos"] = pd.to_numeric(df["m2_cubiertos"], errors="coerce").fillna(0).round().astype(int)
    df["precio_m2_usd"] = (df["precio_usd"] / df["m2"]).round(1)
    df["m2"] = df["m2"].fillna(0).round().astype(int)
    df["precio_m2_usd"] = df["precio_m2_usd"].fillna(0.0)

    # Etiquetas tal como las usa app.py
    df["tipo"] = df["tipo"].map(_TIPO_LABEL)
    df["operacion"] = df["operacion"].map(_OPERACION_LABEL)
    df["moneda_original"] = df["moneda_original"].str.strip()
    df["zona"] = df["zona"].fillna("Sin zona")
    df["fuente"] = df["fuente"].fillna("")
    df["fuente_url"] = df["fuente_url"].fillna("")

    columnas = ["id", "lat", "lon", "zona", "direccion", "tipo", "operacion", "m2",
                "m2_totales", "m2_cubiertos",
                "precio_usd", "precio_m2_usd", "moneda_original", "dom", "url", "url_imagenes",
                "fuente", "fuente_url"]
    out_df = df[columnas]
    try:
        out_df.to_csv(cache_csv, index=False, encoding="utf-8-sig")
    except Exception:
        pass
    return out_df


if __name__ == "__main__":
    # Prueba rápida:  python database.py
    init_db()
    print(upsert_propiedad({
        "url": "https://www.argenprop.com/casa-en-venta-en-yerba-buena--ejemplo-1",
        "tipo": "casa", "operacion": "venta", "direccion": "Av. Aconquija 1234",
        "zona": "Yerba Buena", "latitud": -26.8167, "longitud": -65.3,
        "m2_totales": 300, "m2_cubiertos": 180, "habitaciones": 3,
        "url_imagenes": "https://www.argenprop.com/casa-en-venta-en-yerba-buena--ejemplo-1#fotos",
        "precio": 150000, "moneda": "USD",
    }))
    print(load_data().head())
