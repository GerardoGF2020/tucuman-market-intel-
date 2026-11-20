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


# ---------------------------------------------------------------------
# Sistema de Autenticación, Registro y Autogestión de Usuarios
# ---------------------------------------------------------------------
USUARIOS_DEFAULT = {
    "gerardocggf@gmail.com": {"clave": "tucuman2026", "estado": "activo", "rol": "admin", "nombre": "Gerardo (Admin)", "email": "gerardocggf@gmail.com"},
    "gerardo": {"clave": "tucuman2026", "estado": "activo", "rol": "admin", "nombre": "Gerardo (Admin)", "email": "gerardocggf@gmail.com"},
    "admin": {"clave": "tucuman2026", "estado": "activo", "rol": "admin", "nombre": "Administrador", "email": "admin@inmobiliaria.com"},
}
USUARIOS_FILE = os.path.join(os.path.dirname(__file__), "usuarios.json")


def _cargar_base_usuarios() -> dict:
    """Carga todos los usuarios normalizados (admin, guardados en JSON y secrets)."""
    cuentas = {u: dict(d) for u, d in USUARIOS_DEFAULT.items()}
    if os.path.exists(USUARIOS_FILE):
        try:
            import json
            with open(USUARIOS_FILE, "r", encoding="utf-8") as f:
                guardados = json.load(f)
                for u, datos in guardados.items():
                    u_norm = u.strip().lower()
                    if isinstance(datos, str):
                        cuentas[u_norm] = {"clave": datos, "estado": "activo", "rol": "operador", "nombre": u_norm, "email": u_norm}
                    elif isinstance(datos, dict):
                        cuentas[u_norm] = datos
        except Exception:
            pass
    try:
        if "passwords" in st.secrets:
            for u, p in dict(st.secrets["passwords"]).items():
                u_norm = u.strip().lower()
                cuentas[u_norm] = {"clave": str(p), "estado": "activo", "rol": "operador", "nombre": u_norm, "email": u_norm}
    except Exception:
        pass
    return cuentas


def _guardar_usuarios_disco(cuentas: dict) -> bool:
    """Persiste el diccionario de usuarios en usuarios.json."""
    import json
    try:
        with open(USUARIOS_FILE, "w", encoding="utf-8") as f:
            json.dump(cuentas, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _solicitar_registro(email: str, clave: str, nombre: str) -> tuple[bool, str]:
    """Registra un nuevo operador por correo electrónico en estado pendiente."""
    cuentas = _cargar_base_usuarios()
    em = email.strip().lower()
    nom = nombre.strip()
    if not em or not clave or not nom:
        return False, "Completá todos los campos requeridos (Nombre, Correo y Contraseña)."
    if "@" not in em or "." not in em.split("@")[-1]:
        return False, f"El correo '{em}' no tiene un formato válido (ejemplo: usuario@dominio.com)."
    if len(clave) < 6:
        return False, "La contraseña debe tener al menos 6 caracteres."
    if em in cuentas:
        if cuentas[em].get("estado") == "pendiente":
            return False, f"Ya existe una solicitud pendiente de autorización para '{em}'."
        return False, f"El correo '{em}' ya está registrado. Podés iniciar sesión o cambiar tu clave."

    cuentas[em] = {
        "clave": clave.strip(),
        "estado": "pendiente",
        "rol": "operador",
        "nombre": nom,
        "email": em,
        "fecha_solicitud": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")
    }
    if _guardar_usuarios_disco(cuentas):
        return True, f"¡Solicitud registrada con éxito para {em}! El Administrador (Gerardo) debe autorizar tu acceso para que puedas ingresar."
    return False, "Error al registrar la solicitud en el sistema."


def _aprobar_usuario(email_o_user: str) -> bool:
    """El administrador aprueba una cuenta pendiente."""
    cuentas = _cargar_base_usuarios()
    u = email_o_user.strip().lower()
    if u in cuentas:
        cuentas[u]["estado"] = "activo"
        return _guardar_usuarios_disco(cuentas)
    return False


def _rechazar_usuario(email_o_user: str) -> bool:
    """El administrador rechaza o elimina un usuario."""
    cuentas = _cargar_base_usuarios()
    u = email_o_user.strip().lower()
    if u in ["gerardocggf@gmail.com", "gerardo", "admin"]:
        return False
    if u in cuentas:
        del cuentas[u]
        return _guardar_usuarios_disco(cuentas)
    return False


def _cambiar_propia_clave(email_o_user: str, clave_actual: str, clave_nueva: str) -> tuple[bool, str]:
    """Permite al usuario cambiar su propia contraseña sin intervención del administrador."""
    cuentas = _cargar_base_usuarios()
    u = email_o_user.strip().lower()
    if u not in cuentas:
        return False, "Correo o usuario no encontrado en el sistema."
    if cuentas[u].get("clave") != clave_actual:
        return False, "La contraseña actual no coincide."
    if not clave_nueva or len(clave_nueva) < 6:
        return False, "La nueva contraseña debe tener al menos 6 caracteres."
    if clave_actual == clave_nueva:
        return False, "La nueva contraseña debe ser diferente a la anterior."
    cuentas[u]["clave"] = clave_nueva.strip()
    if _guardar_usuarios_disco(cuentas):
        return True, "¡Contraseña actualizada exitosamente! Ya podés ingresar con tu nueva clave."
    return False, "Error al guardar la nueva contraseña."
    cuentas = _cargar_base_usuarios()
    u = usuario.strip().lower()
    if u not in cuentas:
        return False, "Usuario no encontrado."
    if cuentas[u]["clave"] != clave_actual:
        return False, "La contraseña actual no coincide."
    if not clave_nueva or len(clave_nueva) < 4:
        return False, "La nueva contraseña debe tener al menos 4 caracteres."
    cuentas[u]["clave"] = clave_nueva.strip()
    if _guardar_usuarios_disco(cuentas):
        return True, "¡Contraseña actualizada exitosamente!"
    return False, "Error al guardar la nueva contraseña."


def verificar_autenticacion():
    """Pantalla de acceso idéntica a la plataforma de inteligencia de mercado."""
    cuentas = _cargar_base_usuarios()

    if st.session_state.get("authenticated", False):
        return True

    st.write("")
    st.write("")
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("## 🏠 Mercado Inmobiliario Tucumán")
        st.caption("Plataforma de Inteligencia y Monitoreo del Sector")

        # Selector visual de acción idéntico
        opcion = st.radio(
            "Seleccione qué desea hacer:",
            ["🔑 Iniciar Sesión", "📝 Solicitar Cuenta Nueva", "🔄 Olvidé mi Contraseña"],
            horizontal=True,
            label_visibility="collapsed",
        )

        st.markdown("---")

        # --------------------------------------------------------- 1: INICIAR SESIÓN
        if opcion == "🔑 Iniciar Sesión":
            st.subheader("Ingreso al Sistema")
            bloqueado = st.session_state.get("intentos", 0) >= 5
            with st.form("form_login"):
                u = st.text_input("Correo Electrónico (o usuario admin)", placeholder="ejemplo@correo.com", key="login_email").strip().lower()
                p = st.text_input("Contraseña", type="password", key="login_pass")
                submit = st.form_submit_button("Ingresar", use_container_width=True, disabled=bloqueado)

            if bloqueado:
                st.error("🔒 Demasiados intentos fallidos. Espere unos momentos y recargue la página.")
            elif submit:
                if u in cuentas:
                    u_info = cuentas[u]
                    if u_info.get("estado") == "pendiente":
                        st.warning("⏳ Tu cuenta fue registrada pero **está pendiente de autorización por el Administrador (Gerardo)**. Apenas te dé de alta podrás ingresar.")
                    elif u_info.get("clave") == p:
                        st.session_state["authenticated"] = True
                        st.session_state["username"] = u
                        st.session_state["is_admin"] = (u in ["gerardo", "admin"])
                        st.session_state["intentos"] = 0
                        st.rerun()
                    else:
                        st.session_state["intentos"] = st.session_state.get("intentos", 0) + 1
                        st.error("Contraseña incorrecta. Verificá tu clave.")
                else:
                    st.session_state["intentos"] = st.session_state.get("intentos", 0) + 1
                    st.error("El usuario o correo no está registrado en el sistema.")

        # --------------------------------------------------------- 2: SOLICITAR CUENTA NUEVA
        elif opcion == "📝 Solicitar Cuenta Nueva":
            st.subheader("Registro de Nuevo Usuario")
            st.info("💡 **Tu Correo Electrónico o Usuario será tu acceso**. Por seguridad, el Administrador (Gerardo) debe autorizar tu acceso antes de que puedas ingresar.")

            with st.form("form_registro"):
                reg_nombre = st.text_input("Nombre y Apellido", placeholder="Ej. Juan Pérez")
                reg_email = st.text_input("Correo Electrónico o Usuario deseado", placeholder="juan.perez@empresa.com.ar").strip().lower()
                reg_pass1 = st.text_input("Contraseña deseada (mínimo 6 caracteres)", type="password")
                reg_pass2 = st.text_input("Confirmar Contraseña", type="password")
                reg_submit = st.form_submit_button("Solicitar Acceso al Administrador", use_container_width=True)

            if reg_submit:
                if not reg_nombre or not reg_email or not reg_pass1:
                    st.warning("Todos los campos son obligatorios.")
                elif reg_pass1 != reg_pass2:
                    st.warning("Las contraseñas no coinciden.")
                elif len(reg_pass1) < 6:
                    st.warning("La contraseña debe tener al menos 6 caracteres.")
                else:
                    ok, msg = _solicitar_registro(reg_email, reg_pass1, reg_nombre)
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(msg)

        # --------------------------------------------------------- 3: OLVIDÉ MI CONTRASEÑA
        elif opcion == "🔄 Olvidé mi Contraseña":
            st.subheader("Recuperación de Contraseña")
            st.caption("Ingresá tu correo o usuario registrado para actualizar tu clave.")

            with st.form("form_recup"):
                rec_user = st.text_input("Correo Electrónico o Usuario registrado", placeholder="tu.correo@empresa.com.ar").strip().lower()
                c_anterior = st.text_input("Contraseña anterior (si la recordás)", type="password")
                c_nueva = st.text_input("Nueva Contraseña deseada", type="password")
                rec_submit = st.form_submit_button("Actualizar mi Contraseña", use_container_width=True)

            if rec_submit:
                if not rec_user or not c_nueva:
                    st.warning("Completá los campos requeridos.")
                elif rec_user in cuentas:
                    ok, msg = _cambiar_propia_clave(rec_user, c_anterior, c_nueva)
                    if ok:
                        st.success(f"✅ {msg} Ya podés ir a 'Iniciar Sesión' con tu nueva clave.")
                    else:
                        st.error(f"{msg} Si no recordás tu clave anterior, contactá a Gerardo para que te la restablezca en 1 clic.")
                else:
                    st.error("Ese usuario o correo no figura en el sistema.")

    st.stop()


verificar_autenticacion()

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
usuario_activo = st.session_state.get("username", "autorizado")
es_admin = st.session_state.get("is_admin", usuario_activo in ["gerardo", "admin"])
st.sidebar.markdown(f"👤 **Usuario:** `{usuario_activo}` {'*(Administrador)*' if es_admin else '*(Operador)*'}")

# Autogestión de clave para cualquier usuario conectado
with st.sidebar.expander("🔑 Cambiar mi contraseña"):
    with st.form("form_cambio_clave_propia"):
        c_act = st.text_input("Contraseña actual", type="password")
        c_nue = st.text_input("Nueva contraseña", type="password")
        c_nue2 = st.text_input("Confirmar nueva contraseña", type="password")
        if st.form_submit_button("Actualizar mi Clave", use_container_width=True):
            if not c_act or not c_nue:
                st.warning("Completá todos los campos.")
            elif c_nue != c_nue2:
                st.error("Las nuevas contraseñas no coinciden.")
            else:
                ok, msg = _cambiar_propia_clave(usuario_activo, c_act, c_nue)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

# Panel Exclusivo del Administrador (Gerardo)
if es_admin:
    cuentas_todas = _cargar_base_usuarios()
    pendientes = [u for u, d in cuentas_todas.items() if d.get("estado") == "pendiente"]
    
    if pendientes:
        st.sidebar.warning(f"🔔 **{len(pendientes)} solicitud(es) de alta pendiente(s)**")

    with st.sidebar.expander(f"👥 Gestión y Altas de Operadores ({len(pendientes)} pendientes)", expanded=bool(pendientes)):
        if pendientes:
            st.markdown("### 🔔 Solicitudes por Aprobar:")
            for p_user in pendientes:
                p_info = cuentas_todas[p_user]
                st.markdown(f"**Nombre:** {p_info.get('nombre', p_user)}  \n**Usuario:** `{p_user}`  \n*Fecha:* {p_info.get('fecha_solicitud', '')}")
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    if st.button("✅ Dar de Alta", key=f"apr_{p_user}", use_container_width=True):
                        _aprobar_usuario(p_user)
                        st.success(f"¡{p_user} dado de alta! Ya puede ingresar con su clave.")
                        st.rerun()
                with c_btn2:
                    if st.button("❌ Rechazar", key=f"rec_{p_user}", use_container_width=True):
                        _rechazar_usuario(p_user)
                        st.info(f"Solicitud de {p_user} rechazada.")
                        st.rerun()
                st.markdown("---")
        else:
            st.caption("No hay solicitudes pendientes de aprobación.")

        # Operadores activos
        activos = [u for u, d in cuentas_todas.items() if d.get("estado") == "activo" and u not in ["gerardo", "admin"]]
        if activos:
            st.markdown("**Operadores Habilitados:**")
            for act_u in activos:
                nom = cuentas_todas[act_u].get("nombre", act_u)
                st.markdown(f"• `{act_u}` ({nom})")
            
            st.markdown("---")
            st.markdown("**Revocar Acceso:**")
            u_baja = st.selectbox("Seleccionar operador a dar de baja", activos, key="sel_baja")
            if st.button("🗑️ Dar de Baja", use_container_width=True):
                if _rechazar_usuario(u_baja):
                    st.success(f"Acceso de `{u_baja}` revocado.")
                    st.rerun()

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state["authenticated"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("is_admin", None)
    st.rerun()
st.sidebar.markdown("---")

if origen == "real":
    n_ig = int((df["canal"] == "Instagram").sum())
    n_web = int((df["canal"] == "Web Oficial").sum())
    tag_fuente = f" ({aviso})" if aviso else ""
    st.sidebar.success(f"✅ Datos reales{tag_fuente}: {len(df)} prop. ({n_web} Web · {n_ig} IG)")
else:
    st.sidebar.warning(f"⚠️ DATOS DE PRUEBA (ficticios). {aviso}")
st.sidebar.caption(f"🕒 Última actualización: {last_update:%d/%m/%Y %H:%M:%S}  \nSe actualiza cada {CACHE_TTL // 60} min")

col_act1, col_act2 = st.sidebar.columns(2)
with col_act1:
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col_act2:
    excel_path = os.path.join(os.path.dirname(__file__), "Propiedades_Tucuman_Market_Intel.xlsx")
    if os.path.exists(excel_path):
        with open(excel_path, "rb") as f:
            st.download_button("📥 Descargar Excel", data=f.read(), file_name="Propiedades_Tucuman.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

st.sidebar.markdown("☁️ [**Abrir Planilla en Google Drive**](https://drive.google.com/drive/folders/1-0RY6p6X4R7cvi0W8TTzyb7cwDaaZe2u)")
st.sidebar.markdown("---")
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

if "habitaciones" not in df.columns:
    df["habitaciones"] = 0
df["habitaciones"] = pd.to_numeric(df["habitaciones"], errors="coerce").fillna(0).astype(int)
st.sidebar.subheader("🛏️ Dormitorios")
dorm_opts = {"Cualquiera": 0, "1+": 1, "2+": 2, "3+": 3, "4+": 4}
dorm_sel = st.sidebar.select_slider(
    "Mínimo de dormitorios (los avisos sin dato siempre se muestran)",
    options=list(dorm_opts), value="Cualquiera",
)
dorm_min = dorm_opts[dorm_sel]

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
    & ((df.habitaciones == 0) | (df.habitaciones >= dorm_min))
    & df.fuente.replace("", "Sin fuente").isin(fuentes_sel)
]

# ---------------- Main ----------------
import altair as alt
from folium.plugins import MarkerCluster

st.markdown(
    """
<style>
.block-container {padding-top: 1.4rem; max-width: 1500px;}
div[data-testid="stMetric"] {
    background: #ffffff; border: 1px solid #e3e8ef; border-left: 5px solid #2a6fdb;
    border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
div[data-testid="stMetricValue"] {font-size: 1.7rem;}
button[data-baseweb="tab"] {font-size: 1.02rem; font-weight: 600;}
@media (max-width: 768px) {
    .block-container {padding: .6rem .5rem;}
    div[data-testid="stMetricValue"] {font-size: 1.25rem;}
    h1 {font-size: 1.4rem !important;}
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🏠 Market Intelligence Inmobiliario – Tucumán")
st.caption("Mapa, análisis de mercado, comparativa con Buenos Aires y planilla de propiedades. Usá los filtros de la barra lateral.")

# KPIs (los USD/m² ignoran avisos sin superficie para no distorsionar la mediana)
f_m2 = f[(f.m2 > 0) & (f.precio_m2_usd > 0)]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Propiedades", f"{len(f):,}")
k2.metric("Precio mediano (USD)", f"{f.precio_usd.median():,.0f}" if len(f) else "–")
k3.metric("USD/m² mediano", f"{f_m2.precio_m2_usd.median():,.0f}" if len(f_m2) else "–")
k4.metric("DOM mediano (días)", f"{f.dom.median():.0f}" if len(f) else "–")
k5.metric("Inmobiliarias", f"{f.fuente.replace('', 'Sin fuente').nunique()}")

if f.empty:
    st.warning("No hay propiedades con los filtros actuales. Ampliá los filtros en la barra lateral.")
    st.stop()

tab_mapa, tab_analisis, tab_comp, tab_tabla = st.tabs(
    ["🗺️ Mapa", "📊 Análisis de mercado", "⚖️ Tucumán vs Buenos Aires", "📋 Planilla"]
)

# ============================ TAB 1: MAPA ============================
with tab_mapa:
    mc1, mc2 = st.columns([1, 1])
    agrupar = mc1.toggle("📍 Agrupar pines cercanos (clusters)", value=True)
    base_mapa = mc2.selectbox(
        "Estilo de mapa", ["Calles (OpenStreetMap)", "Claro (CartoDB)", "Oscuro (CartoDB)"], label_visibility="collapsed"
    )
    tiles = {"Calles (OpenStreetMap)": "OpenStreetMap", "Claro (CartoDB)": "CartoDB positron",
             "Oscuro (CartoDB)": "CartoDB dark_matter"}[base_mapa]

    m = folium.Map(location=CENTER, zoom_start=12, tiles=tiles)
    destino = MarkerCluster(name="Propiedades").add_to(m) if agrupar else m
    vistos_coord: dict[tuple[float, float], int] = {}
    for r in f.itertuples():
        es_ig = getattr(r, "canal", "") == "Instagram"
        col = "purple" if es_ig else color_for(r.dom)
        icono = "camera" if es_ig else "home"

        # Sin clusters: separa pines con idéntica coordenada para que no se tapen
        lat_pin, lon_pin = float(r.lat), float(r.lon)
        if not agrupar:
            clave_c = (round(lat_pin, 4), round(lon_pin, 4))
            idx_c = vistos_coord.get(clave_c, 0)
            vistos_coord[clave_c] = idx_c + 1
            if idx_c > 0:
                angulo = idx_c * 2.39996
                radio = 0.0014 * np.sqrt(idx_c)
                lat_pin += radio * float(np.cos(angulo))
                lon_pin += radio * float(np.sin(angulo))

        m2_pin = int(getattr(r, "m2_totales", 0) or getattr(r, "m2", 0) or 0)
        m2_cub_pin = int(getattr(r, "m2_cubiertos", 0) or 0)
        m2_badge = f"Total: {m2_pin:,} m² | Constr.: {m2_cub_pin:,} m²" if m2_pin > 0 else "s/d m²"
        prefijo_ig = "📸 [IG] " if es_ig else ""
        folium.Marker(
            [lat_pin, lon_pin],
            popup=folium.Popup(popup_html(r), max_width=275),
            tooltip=f"{prefijo_ig}{TIPO_LABEL[r.tipo]} · USD {r.precio_usd:,.0f} · 📏 {m2_badge}",
            icon=folium.Icon(color=col, icon=icono, prefix="fa"),
        ).add_to(destino)

    legend = f"""
<div style="position:fixed;bottom:25px;left:25px;z-index:9999;background:#fff;padding:8px 12px;
            border:1px solid #888;border-radius:6px;font-size:12px;">
<span style="color:#2e9e4f;">●</span> Nueva (&lt;{NEW_DAYS} días)<br>
<span style="color:#2a6fdb;">●</span> Activa (Web)<br>
<span style="color:#d63a3a;">●</span> Antigua (&gt;{OLD_DAYS} días)<br>
<span style="color:#9c27b0;">●</span> 📸 Publicación de Instagram</div>"""
    m.get_root().html.add_child(folium.Element(legend))
    st_folium(m, use_container_width=True, height=620, returned_objects=[])

# ============================ TAB 2: ANÁLISIS ============================
with tab_analisis:
    vta = f_m2[f_m2.operacion == "Venta"]
    ca, cb = st.columns(2)

    with ca:
        st.subheader("💵 USD/m² mediano por zona (venta)")
        z = vta.groupby("zona").precio_m2_usd.agg(["median", "count"]).reset_index()
        z = z[z["count"] >= 3].sort_values("median", ascending=False).head(15)
        if z.empty:
            st.info("Se necesitan al menos 3 avisos por zona.")
        else:
            st.altair_chart(
                alt.Chart(z).mark_bar(color="#2a6fdb").encode(
                    y=alt.Y("zona:N", sort="-x", title=None),
                    x=alt.X("median:Q", title="USD/m² mediano"),
                    tooltip=[alt.Tooltip("zona:N", title="Zona"), alt.Tooltip("median:Q", format=",.0f", title="USD/m²"),
                             alt.Tooltip("count:Q", title="Avisos")],
                ).properties(height=380),
                use_container_width=True,
            )

    with cb:
        st.subheader("🏢 Propiedades por inmobiliaria (top 15)")
        fu = f.fuente.replace("", "Sin fuente").value_counts().head(15).rename_axis("fuente").reset_index(name="avisos")
        st.altair_chart(
            alt.Chart(fu).mark_bar(color="#9c27b0").encode(
                y=alt.Y("fuente:N", sort="-x", title=None), x=alt.X("avisos:Q", title="Avisos"),
                tooltip=["fuente", "avisos"],
            ).properties(height=380),
            use_container_width=True,
        )

    cc, cd = st.columns(2)
    with cc:
        st.subheader("🏷️ USD/m² mediano por tipo y operación")
        t = f_m2.groupby(["tipo", "operacion"]).precio_m2_usd.agg(["median", "count"]).reset_index()
        st.altair_chart(
            alt.Chart(t).mark_bar().encode(
                x=alt.X("tipo:N", title=None), y=alt.Y("median:Q", title="USD/m² mediano"),
                color=alt.Color("operacion:N", title="Operación"), xOffset="operacion:N",
                tooltip=["tipo", "operacion", alt.Tooltip("median:Q", format=",.0f"), alt.Tooltip("count:Q", title="Avisos")],
            ).properties(height=320),
            use_container_width=True,
        )
    with cd:
        st.subheader("⏱️ Días en el mercado (DOM)")
        st.altair_chart(
            alt.Chart(f).mark_bar(color="#2e9e4f").encode(
                x=alt.X("dom:Q", bin=alt.Bin(maxbins=20), title="Días en el mercado"),
                y=alt.Y("count():Q", title="Avisos"),
            ).properties(height=320),
            use_container_width=True,
        )

    st.subheader("🔵 Precio vs superficie (venta)")
    if vta.empty:
        st.info("Sin ventas con superficie informada para graficar.")
    else:
        sc = vta[vta.m2 < vta.m2.quantile(0.98)]
        st.altair_chart(
            alt.Chart(sc).mark_circle(size=60, opacity=0.6).encode(
                x=alt.X("m2:Q", title="Superficie total (m²)"), y=alt.Y("precio_usd:Q", title="Precio (USD)"),
                color=alt.Color("tipo:N", title="Tipo"),
                tooltip=["tipo", "zona", "fuente", alt.Tooltip("m2:Q", title="m²"),
                         alt.Tooltip("precio_usd:Q", format=",.0f", title="USD")],
            ).properties(height=380).interactive(),
            use_container_width=True,
        )
        st.caption("Se excluye el 2 % de superficies más grandes para que el gráfico sea legible.")

# ============================ TAB 3: TUCUMÁN VS BUENOS AIRES ============================
with tab_comp:
    st.subheader("⚖️ ¿Cuánto más barato (o caro) es Tucumán que Buenos Aires?")
    ref_path = os.path.join(os.path.dirname(__file__), "referencia_buenos_aires.csv")
    if not os.path.exists(ref_path):
        st.info("Todavía no se generó la referencia de Buenos Aires. Ejecutá `python referencia_buenos_aires.py`.")
    else:
        ref = pd.read_csv(ref_path)
        fecha_ref = ref["fecha_muestra"].iloc[0] if "fecha_muestra" in ref.columns and len(ref) else "s/d"
        tuc = df[(df.operacion == "Venta") & (df.m2 > 0) & (df.precio_m2_usd > 0) & (df.moneda_original == "USD")].copy()
        tuc = tuc.assign(grupo="Tucumán")[["grupo", "tipo", "precio_m2_usd"]]
        bsas = ref[["grupo", "tipo", "precio_m2_usd"]]
        comp = pd.concat([tuc, bsas]).groupby(["tipo", "grupo"]).precio_m2_usd.agg(["median", "count"]).reset_index()
        comp = comp[comp["count"] >= 3]

        if comp.empty:
            st.info("No hay suficientes avisos para comparar.")
        else:
            st.altair_chart(
                alt.Chart(comp).mark_bar().encode(
                    x=alt.X("tipo:N", title=None), y=alt.Y("median:Q", title="USD/m² mediano (venta)"),
                    color=alt.Color("grupo:N", title="Zona", sort=["Tucumán", "CABA", "GBA", "Interior BA"]),
                    xOffset="grupo:N",
                    tooltip=["tipo", "grupo", alt.Tooltip("median:Q", format=",.0f", title="USD/m²"),
                             alt.Tooltip("count:Q", title="Avisos")],
                ).properties(height=380),
                use_container_width=True,
            )
            piv = comp.pivot(index="tipo", columns="grupo", values="median")
            if "Tucumán" in piv.columns and "CABA" in piv.columns:
                piv["Tucumán vs CABA"] = ((piv["Tucumán"] / piv["CABA"] - 1) * 100).round(0)
            st.dataframe(piv.round(0), use_container_width=True)
            st.caption(
                f"Referencia Buenos Aires: muestra del portal deinmobiliarios del {fecha_ref} "
                f"({len(ref)} avisos de venta en USD). 'Tucumán vs CABA' = diferencia % del USD/m² mediano. "
                "Sólo se comparan combinaciones con 3 o más avisos. Es una comparación orientativa, no un índice oficial."
            )

# ============================ TAB 4: PLANILLA ============================
with tab_tabla:
    st.subheader("📋 Planilla de propiedades filtradas")
    tc1, tc2 = st.columns([2, 1])
    buscar = tc1.text_input("🔎 Buscar por dirección, zona o inmobiliaria", placeholder="Ej: Yerba Buena, Remax, Laprida…")
    orden = tc2.selectbox(
        "Ordenar por",
        ["Más recientes", "Precio: menor a mayor", "Precio: mayor a menor", "USD/m²: menor a mayor", "USD/m²: mayor a menor"],
    )
    ft = f
    if buscar.strip():
        q = buscar.strip().lower()
        ft = f[(f.direccion.fillna("").astype(str).str.lower().str.contains(q, regex=False)
                | f.zona.fillna("").astype(str).str.lower().str.contains(q, regex=False)
                | f.fuente.fillna("").astype(str).str.lower().str.contains(q, regex=False))]
    col_orden, asc = {
        "Más recientes": ("dom", True), "Precio: menor a mayor": ("precio_usd", True),
        "Precio: mayor a menor": ("precio_usd", False), "USD/m²: menor a mayor": ("precio_m2_usd", True),
        "USD/m²: mayor a menor": ("precio_m2_usd", False),
    }[orden]
    ft = ft.sort_values(col_orden, ascending=asc)
    st.caption(f"{len(ft):,} propiedades")

    tabla = ft.drop(columns=["lat", "lon", "fuente_url", "m2", "id", "canal"], errors="ignore").rename(columns={
        "m2_totales": "M² Totales (Terreno/Prop.)", "m2_cubiertos": "M² Cubiertos", "habitaciones": "Dorm.",
        "precio_usd": "Precio USD", "precio_m2_usd": "USD/m²", "dom": "DOM (días)",
        "moneda_original": "Moneda orig.", "fuente": "Fuente", "direccion": "Dirección", "operacion": "Operación",
        "tipo": "Tipo", "url": "Publicación", "url_imagenes": "Foto"})
    st.dataframe(
        tabla, use_container_width=True, hide_index=True,
        column_config={
            "Foto": st.column_config.ImageColumn("Foto", width="small"),
            "Publicación": st.column_config.LinkColumn("Publicación", display_text="Ver publicación"),
            "Precio USD": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.download_button("⬇️ Descargar CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                       "propiedades_tucuman.csv", "text/csv")
