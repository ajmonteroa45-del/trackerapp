# app.py - Trip Counter (TrackerApp v4.0 - Cloud Ready + GPH)
import streamlit as st
import pandas as pd
import os, json, hashlib, re
from datetime import date, datetime, timedelta # <-- timedelta es crucial para el cálculo de tiempo
from io import BytesIO
import matplotlib.pyplot as plt
from PIL import Image

# Necesario: Configurar el entorno de despliegue con las credenciales de Google Sheets.
# Las credenciales se deben guardar en st.secrets:
# [connections.gsheets]
# type = "oauth"
# scopes = [...]
# token = {...}

# ----- Configuración y Conexión -----
st.set_page_config(page_title="Trip Counter", layout="wide", initial_sidebar_state="auto")
APP_NAME = "Trip Counter"
BUTTON_COLOR = "#1034A6" # azul rey

# Define los nombres de los Hojas de Cálculo (Sheets) para persistencia
GSHEET_USERS_TITLE = "TripCounter_Users"
GSHEET_TRIPS_TITLE = "TripCounter_Trips"
GSHEET_GASTOS_TITLE = "TripCounter_Gastos"
GSHEET_SUMMARIES_TITLE = "TripCounter_Summaries"
# Nota: La persistencia de imágenes (.png) y logos será manejada como un punto pendiente.
# En la nube, estas se deberían almacenar en un bucket (S3, GCS) o base de datos.
# Por ahora, solo se guardarán temporalmente en memoria para la descarga.
# Si los logos 'logo_app.png' y 'logo_uber.png' son estáticos, deben estar en el repo.

# Establecer conexión (se asume que las credenciales están en st.secrets)


# ----- Helpers Actualizados (Google Sheets) -----

import gspread # <--- ASEGÚRATE DE QUE ESTÉ EN TUS IMPORTS

# Función que toma las credenciales de st.secrets y autentica gspread
@st.cache_resource(ttl=3600) # Usamos cache_resource porque es una conexión/recurso
def get_gspread_client():
    # Carga las credenciales del formato que Streamlit guardó
    gspread_info = st.secrets["connections"]["gsheets"]
    
    # gspread espera un diccionario, por lo que cargamos la clave privada
    # usando el formato que ya corregimos (una sola línea)
    creds_dict = {
        "type": gspread_info["type"],
        "project_id": gspread_info["project_id"],
        "private_key_id": gspread_info["private_key_id"],
        "private_key": gspread_info["private_key"].replace("\\n", "\n"), # Revertimos '\n' a saltos de línea reales
        "client_email": gspread_info["client_email"],
        "client_id": gspread_info["client_id"],
        "auth_uri": gspread_info["auth_uri"],
        "token_uri": gspread_info["token_uri"],
        "auth_provider_x509_cert_url": gspread_info["auth_provider_x509_cert_url"],
        "client_x509_cert_url": gspread_info["client_x509_cert_url"]
    }
    
    # Autenticación de gspread
    client = gspread.service_account_from_dict(creds_dict)
    return client

# Creamos la instancia del cliente para usarla en el resto de los helpers
GSPREAD_CLIENT = get_gspread_client()

@st.cache_data(ttl=3600) # Cache para reducir llamadas a la API de Sheets
@st.cache_data(ttl=3600)
def load_data_from_sheet(sheet_title):
    try:
        # Abrir el libro de cálculo por su título
        sh = GSPREAD_CLIENT.open(sheet_title)
        # Seleccionar la primera hoja de trabajo
        ws = sh.get_worksheet(0)
        
        # Leer todos los registros y convertirlos a DataFrame
        data = ws.get_all_records(head=1, empty2zero=True)
        df = pd.DataFrame(data)

        # Si el DataFrame está vacío o tiene menos columnas de las esperadas, lo inicializamos.
        if df.empty or len(df.columns) < 2:
            raise Exception("Hoja vacía o con formato incorrecto")
        
        return df.dropna(how='all', axis=1)

    except Exception as e:
        # Si la hoja no existe (o falla la lectura), creamos un DF vacío para inicializar
        if "spreadsheet not found" in str(e).lower() or "Hoja vacía" in str(e):
            if sheet_title == GSHEET_USERS_TITLE:
                return pd.DataFrame(columns=["alias", "pin_hash"])
            # ... (el resto de las inicializaciones)
            if sheet_title == GSHEET_TRIPS_TITLE:
                return pd.DataFrame(columns=["alias", "fecha","tipo","viaje_num","hora_inicio","hora_fin","ganancia_base","aeropuerto","propina","total_viaje", "ganancia_por_hora"]) 
            if sheet_title == GSHEET_GASTOS_TITLE:
                return pd.DataFrame(columns=["alias", "fecha","concepto","monto"])
            if sheet_title == GSHEET_SUMMARIES_TITLE:
                return pd.DataFrame(columns=["alias", "date", "total_viajes", "ingresos", "gastos", "combustible", "kilometraje", "total_neto", "image_id"])
            return pd.DataFrame()

        st.warning(f"Error al leer hoja {sheet_title}: {e}. Usando datos vacíos.")
        return pd.DataFrame()

def load_users():
    # Llama al cliente dentro de la función (más seguro para Streamlit)
    client = get_gspread_client() 
    
    # Abrir la hoja de usuarios usando el cliente
    try:
        sh = client.open(GSHEET_USERS_TITLE)
        ws = sh.get_worksheet(0)
        
        data = ws.get_all_records(head=1, empty2zero=True)
        df = pd.DataFrame(data)
        
        # El resto de la lógica de load_users se mantiene
        return {row['alias']: {"pin_hash": row['pin_hash']} for index, row in df.iterrows()} if not df.empty else {}
    except Exception:
        # Si falla (hoja no existe o error), retorna diccionario vacío
        return {}
    
def save_users(u):
    df = pd.DataFrame([{"alias": k, "pin_hash": v["pin_hash"]} for k, v in u.items()])
    
    # NUEVA LÓGICA DE ESCRITURA:
    try:
        sh = GSPREAD_CLIENT.open(GSHEET_USERS_TITLE)
        ws = sh.get_worksheet(0)
        # Limpia y escribe el DataFrame con encabezados
        ws.clear()
        ws.set_dataframe(df, 'A1', include_index=False)
        
    except gspread.exceptions.SpreadsheetNotFound:
        # Si el libro de cálculo no existe, lo creamos
        sh = GSPREAD_CLIENT.create(GSHEET_USERS_TITLE)
        sh.share(st.secrets["connections"]["gsheets"]["client_email"], perm_type='user', role='writer')
        ws = sh.get_worksheet(0)
        ws.set_dataframe(df, 'A1', include_index=False)

    load_data_from_sheet.clear() # Invalidar caché

# El resto de helpers se mantienen o se adaptan para no usar rutas de archivo local.
def hash_pin(pin):
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()

def validate_time_string(t):
    """Validate HH:MM format 00:00 - 23:59 (más estricto con re)"""
    if not isinstance(t, str) or t.strip() == "":
        return False
    t = t.strip()
    return re.match(r'^([01]\d|2[0-3]):[0-5]\d$', t) is not None

def total_of_trips(rows):
    return sum(r.get("total_viaje", 0) for r in rows)

# Se modifica para retornar la imagen en BytesIO en lugar de guardarla en disco
def save_summary_and_image(alias, trips_rows, gastos_rows, combustible, km):
    today_str = date.today().isoformat()

    # 1. Calcular totales
    ingresos = total_of_trips(trips_rows)
    gastos_total = sum(g.get("monto", 0) for g in gastos_rows)
    neto = round(float(ingresos) - float(gastos_total) - float(combustible), 2)

    summary_row = {
        "alias": alias,
        "date": today_str,
        "total_viajes": len(trips_rows),
        "ingresos": ingresos,
        "gastos": gastos_total,
        "combustible": combustible,
        "kilometraje": km,
        "total_neto": neto,
        "image_id": f"{alias}_{today_str}" # ID de la imagen (temporal)
    }

    # 2. Guardar resumen en Google Sheet
    df_summaries = load_data_from_sheet(GSHEET_SUMMARIES_TITLE)
    # Eliminar resumen anterior si existe (para evitar duplicados al regenerar)
    df_summaries = df_summaries[~((df_summaries['alias'] == alias) & (df_summaries['date'] == today_str))]
    df_summaries = pd.concat([df_summaries, pd.DataFrame([summary_row])], ignore_index=True)
    conn.write(df_summaries, spreadsheet=GSHEET_SUMMARIES_TITLE)
    load_data_from_sheet.clear() # Invalidar caché

    # 3. Generar imagen (retorna BytesIO)
    img_buf = generate_balance_image(trips_rows, ingresos, gastos_total, combustible, neto, alias)

    # Retorna el resumen y el buffer de la imagen (no la ruta)
    return summary_row, img_buf

# Se adapta la función de imagen. NOTA: Las rutas a logos deben ser relativas al repositorio
# o cargados desde un URL si no se incluyen en el repositorio.
def generate_balance_image(rows, ingresos, gastos_total, combustible, neto, alias):
    """Crea una imagen de matplotlib. Se asume que los logos están en el repo si se usan."""
    # ... (cuerpo de la función genera la gráfica) ...
    labels = ["Ingresos (S/)", "Gastos (S/)", "Combustible (S/)"]
    values = [round(ingresos,2), round(gastos_total,2), round(combustible,2)]
    # Añadir Neto solo si es positivo/negativo (para que el color sea claro)
    if neto > 0:
        labels.append("Neto")
        values.append(round(neto, 2))
        colors = ["#4da6ff", "#ff7f50", "#ff9f43", "#2ecc71"]
    else:
        labels.append("Neto")
        values.append(round(neto, 2))
        colors = ["#4da6ff", "#ff7f50", "#ff9f43", "#ff4d4d"] # Rojo para negativo

    fig, ax = plt.subplots(figsize=(8,4.5))
    bars = ax.bar(labels, values, color=colors)
    # ... (código de estilos) ...

    # Convert fig to bytes
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)

    # Se omite el código de superposición de logos con PIL si las rutas de archivo no son accesibles.
    # Si 'logo_app.png' y 'logo_uber.png' están en el mismo directorio que app.py en el repositorio, se usa:
    
    # try:
    #     base_img = Image.open(buf).convert("RGBA")
    #     logo_path = "logo_app.png" # Ruta relativa al directorio de la app
    #     # ... (resto de lógica de PIL) ...
    # except Exception:
    #     buf.seek(0)
    #     return buf
    return buf # Retorna el buffer de la imagen.

# ----- Styling (se mantiene) -----
# Se asume que aquí va el código de estilos (ej. CSS, markdown style)
st.markdown(f"""
    <style>
        .stButton>button {{
            background-color: {BUTTON_COLOR};
            color: white;
            border-radius: 12px;
            border: 0;
            padding: 10px 24px;
        }}
        .stButton>button:hover {{
            background-color: #0d297d; /* Darker shade on hover */
        }}
    </style>
    """, unsafe_allow_html=True)
st.title(APP_NAME)


# ----- Sidebar: Login Actualizado -----
# Se asume que aquí va el código de sidebar
alias = st.session_state.get("user")
st.sidebar.title("Login / Registro")
if not alias:
    alias_input = st.sidebar.text_input("Alias", key="sidebar_alias")
    pin_input = st.sidebar.text_input("PIN (4 dígitos)", type="password", key="sidebar_pin", max_chars=4)
    col1, col2 = st.sidebar.columns(2)
    
if col1.button("Ingresar", key="sidebar_login"):
        if not alias_input or not pin_input:
            st.sidebar.error("Alias y PIN requeridos")
        else:
            u = load_users()
            # Se usa pin_input
            if alias_input in u and u[alias_input]["pin_hash"] == hash_pin(pin_input): 
                st.session_state["user"] = alias_input
                st.sidebar.success(f"Bienvenido, {alias_input}!")
                st.rerun()
            else:
                st.sidebar.error("Alias o PIN incorrectos")

    # La lógica de registro se mantiene, pero llama a las nuevas funciones de Sheets:
    
if col2.button("Registrar", key="sidebar_register"):
        if not alias_input or not pin_input:
            st.sidebar.error("Alias y PIN requeridos")
        else:
            u = load_users()
            # 1. CORREGIDO: Usamos alias_input en lugar de 'alias'
            if alias_input in u: 
                # 2. CORREGIDO: Eliminamos la lógica 'if lang=="Español"'
                st.sidebar.error("Alias ya existe. Elige otro.") 
            else:
                # 3. CORREGIDO: Usamos alias_input y pin_input
                u[alias_input] = {"pin_hash": hash_pin(pin_input)} 
                save_users(u)
                
                # Ojo: ensure_user_csv ya no se usa con Google Sheets. Lo he comentado/eliminado.
                # ensure_user_csv(alias_input) 

                st.session_state["user"] = alias_input
                # 4. CORREGIDO: Eliminamos la lógica 'if lang=="Español"'
                st.sidebar.success("Usuario creado ✅")

if "user" not in st.session_state:
    st.info("Ingresa tu alias y PIN en la barra lateral para empezar.")
    st.stop()

alias = st.session_state["user"]
st.markdown(f"**Usuario:** <span style='color:#cbd5e1'>{alias}</span>", unsafe_allow_html=True)

# Main form to register trips
st.markdown("### ➕ Registrar viajes del día")
with st.form("trips_form"):
    cantidad = st.number_input("¿Cuántos viajes vas a registrar ahora?", min_value=1, step=1, value=1)
    rows = []
    for i in range(int(cantidad)):
        st.markdown(f"**Viaje {i+1}**")
        hi = st.time_input(f"Hora inicio #{i+1}", key=f"hi_{i}")
        hf = st.time_input(f"Hora fin #{i+1}", key=f"hf_{i}")
        gan = st.number_input(f"Ganancia base S/ (viaje #{i+1})", min_value=0.0, format="%.2f", key=f"g_{i}")
        aero = st.checkbox(f"¿Fue al aeropuerto? (+S/6.50) (viaje #{i+1})", key=f"a_{i}")
        prop = st.number_input(f"Propina S/ (viaje #{i+1})", min_value=0.0, format="%.2f", key=f"p_{i}")
        aeropuerto_val = 6.5 if aero else 0.0
        total_v = round(float(gan) + aeropuerto_val + float(prop),2)
        rows.append({
            "fecha": date.today().isoformat(),
            "viaje_num": i+1,
            "hora_inicio": hi.strftime("%H:%M"),
            "hora_fin": hf.strftime("%H:%M"),
            "ganancia_base": float(gan),
            "aeropuerto": aeropuerto_val,
            "propina": float(prop),
            "total_viaje": total_v
        })
    submitted = st.form_submit_button("Agregar viajes" if lang=="Español" else "Add trips")
    if submitted:
        # save rows to user's CSV
        ensure_user_csv(alias)
        csv_path = user_csv_path(alias)
        df_new = pd.DataFrame(rows)
        df_new.to_csv(csv_path, mode="a", header=False, index=False)
        st.success("Viajes guardados ✅" if lang=="Español" else "Trips saved ✅")
        st.rerun()

# Show today's trips for this user
st.markdown("### 📋 Registro actual")
csvp = ensure_user_csv(alias)
try:
    df_all = pd.read_csv(csvp)
    df_today = df_all[df_all["fecha"]==date.today().isoformat()]
    if df_today.empty:
        st.info("No hay viajes registrados hoy." if lang=="Español" else "No trips recorded today.")
    else:
        st.dataframe(df_today)
except Exception as e:
    st.error("Error leyendo registros: " + str(e))

import streamlit as st
import pandas as pd
import os, json, hashlib
from datetime import date, datetime
from io import BytesIO
import matplotlib.pyplot as plt

# --- Config ---
st.set_page_config(page_title="TrackerApp", layout="wide", initial_sidebar_state="collapsed")
APP_NAME = "TrackerApp"
BASE_DIR = os.path.join(os.path.expanduser("~"), "TrackerApp_V1_data")
os.makedirs(BASE_DIR, exist_ok=True)
USERS_FILE = os.path.join(BASE_DIR, "users.json")  # stores {"alias": {"pin_hash": "..."}}

BUTTON_COLOR = "#1034A6"  # azul rey

# --- Helpers ---
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(u):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False, indent=2)

def hash_pin(pin):
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()

def user_csv_path(alias):
    safe = "".join(c for c in alias if c.isalnum() or c in ("_", "-")).lower()
    return os.path.join(BASE_DIR, f"{safe}.csv")

def ensure_user_csv(alias):
    path = user_csv_path(alias)
    if not os.path.exists(path):
        df = pd.DataFrame(columns=["fecha","viaje_num","hora_inicio","hora_fin","ganancia_base","aeropuerto","propina","total_viaje"])
        df.to_csv(path, index=False)
    return path

def append_user_rows(alias, rows, summary):
    path = ensure_user_csv(alias)
    df = pd.DataFrame(rows)
    df.to_csv(path, mode="a", header=False, index=False)
    # also save summary json for quick reference
    summary_path = os.path.join(BASE_DIR, f"{alias}_latest_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return path

def generate_balance_image(rows, extras_total, gastos, combustible, bonos, alias):
    # rows: list of dicts with total_viaje etc.
    total_viajes = len(rows)
    ingresos = sum(r.get("total_viaje",0) for r in rows) + extras_total + bonos
    # hours count
    horas = []
    for r in rows:
        try:
            h = int(str(r.get("hora_inicio","")).split(":")[0])
            horas.append(h)
        except:
            pass
    from collections import Counter
    hora_counts = Counter(horas)
    hora_pico, count_pico = (None, 0)
    if hora_counts:
        hora_pico, count_pico = hora_counts.most_common(1)[0]

    labels = ["Balance (S/)", "Ganancias brutas (S/)", "Gastos totales (S/)", "Viajes total", "Viajes hora pico"]
    values = [round(ingresos - gastos - combustible,2), round(ingresos,2), round(gastos+combustible,2), total_viajes, count_pico]
    colors = ["#2ecc71","#4da6ff","#ff7f50","#2f6fdf","#ff9f43"]

    fig, ax = plt.subplots(figsize=(9,5))
    bars = ax.bar(labels, values, color=colors)
    ax.set_title(f"Balance del día - {date.today().strftime('%Y-%m-%d')} ({alias})", color="white")
    ax.set_ylabel("Valor", color="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("white")
    top = max(values) if values else 1
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, val + top*0.02, f"{val}", ha="center", fontsize=9, color="white")
    plt.tight_layout()
    # dark background
    fig.patch.set_facecolor('#0f1724')
    ax.set_facecolor('#0f1724')
    # save to buffer
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf

# --- UI ---
st.markdown(f"<h1 style='color: {BUTTON_COLOR};'>⚙️ {APP_NAME}</h1>", unsafe_allow_html=True)
st.markdown("<small style='color: #9CA3AF;'>Modo oscuro • Azul rey • Datos por usuario con PIN</small>", unsafe_allow_html=True)
st.write("")

# sidebar: login
with st.sidebar:
    st.markdown("### 🔐 Iniciar sesión / Registrar")
    lang = st.selectbox("Idioma / Language", options=["Español","English"])
    alias = st.text_input("Alias / Nombre", value="")
    pin = st.text_input("PIN (4-6 dígitos)", type="password")
    users = load_users()
    col1, col2 = st.columns(2)
    if col1.button("Entrar" if lang=="Español" else "Login"):
        if not alias or not pin:
            st.sidebar.error("Alias y PIN requeridos" if lang=="Español" else "Alias and PIN required")
        else:
            # check user exists
            u = load_users()
            if alias in u:
                if hash_pin(pin) == u[alias]["pin_hash"]:
                    st.session_state["user"] = alias
                    st.sidebar.success("Acceso correcto ✅" if lang=="Español" else "Login OK ✅")
                else:
                    st.sidebar.error("PIN incorrecto" if lang=="Español" else "Wrong PIN")
            else:
                st.sidebar.error("Usuario no existe, crea cuenta con 'Registrar'." if lang=="Español" else "User not found, register first.")
    if col2.button("Registrar" if lang=="Español" else "Register"):
        if not alias or not pin:
            st.sidebar.error("Alias y PIN requeridos" if lang=="Español" else "Alias and PIN required")
        else:
            u = load_users()
            if alias in u:
                st.sidebar.error("Alias ya existe. Elige otro." if lang=="Español" else "Alias exists. Choose another.")
            else:
                u[alias] = {"pin_hash": hash_pin(pin)}
                save_users(u)
                ensure_user_csv(alias)
                st.session_state["user"] = alias
                st.sidebar.success("Usuario creado ✅" if lang=="Español" else "User created ✅")

if "user" not in st.session_state:
    st.info("Ingresa tu alias y PIN en la barra lateral para empezar." if lang=="Español" else "Enter your alias and PIN in the sidebar to start.")
    st.stop()

alias = st.session_state["user"]
st.markdown(f"**Usuario:** <span style='color:#cbd5e1'>{alias}</span>", unsafe_allow_html=True)

# Main form to register trips
st.markdown("### ➕ Registrar viajes del día")
with st.form("trips_form"):
    cantidad = st.number_input("¿Cuántos viajes vas a registrar ahora?", min_value=1, step=1, value=1)
    rows = []
    for i in range(int(cantidad)):
        st.markdown(f"**Viaje {i+1}**")
        hi = st.time_input(f"Hora inicio #{i+1}", key=f"hi_{i}")
        hf = st.time_input(f"Hora fin #{i+1}", key=f"hf_{i}")
        gan = st.number_input(f"Ganancia base S/ (viaje #{i+1})", min_value=0.0, format="%.2f", key=f"g_{i}")
        aero = st.checkbox(f"¿Fue al aeropuerto? (+S/6.50) (viaje #{i+1})", key=f"a_{i}")
        prop = st.number_input(f"Propina S/ (viaje #{i+1})", min_value=0.0, format="%.2f", key=f"p_{i}")
        aeropuerto_val = 6.5 if aero else 0.0
        total_v = round(float(gan) + aeropuerto_val + float(prop),2)
        rows.append({
            "fecha": date.today().isoformat(),
            "viaje_num": i+1,
            "hora_inicio": hi.strftime("%H:%M"),
            "hora_fin": hf.strftime("%H:%M"),
            "ganancia_base": float(gan),
            "aeropuerto": aeropuerto_val,
            "propina": float(prop),
            "total_viaje": total_v
        })
    submitted = st.form_submit_button("Agregar viajes" if lang=="Español" else "Add trips")
    if submitted:
        # save rows to user's CSV
        ensure_user_csv(alias)
        csv_path = user_csv_path(alias)
        df_new = pd.DataFrame(rows)
        df_new.to_csv(csv_path, mode="a", header=False, index=False)
        st.success("Viajes guardados ✅" if lang=="Español" else "Trips saved ✅")
        st.rerun()

# Show today's trips for this user
st.markdown("### 📋 Registro actual")
csvp = ensure_user_csv(alias)
try:
    df_all = pd.read_csv(csvp)
    df_today = df_all[df_all["fecha"]==date.today().isoformat()]
    if df_today.empty:
        st.info("No hay viajes registrados hoy." if lang=="Español" else "No trips recorded today.")
    else:
        st.dataframe(df_today)
except Exception as e:
    st.error("Error leyendo registros: " + str(e))

# Extras, gastos, combustible, kilometraje
st.markdown("### 💵 Extras y gastos")
with st.form("extras_form"):
    extras_total = st.number_input("Total viajes extra (S/)", min_value=0.0, format="%.2f", value=0.0)
    gastos_varios = st.number_input("Gastos varios (S/)", min_value=0.0, format="%.2f", value=0.0)
    combustible = st.number_input("Combustible (S/)", min_value=0.0, format="%.2f", value=0.0)
    km = st.number_input("Kilometraje recorrido (km)", min_value=0.0, format="%.1f", value=0.0)
    submit_extras = st.form_submit_button("Guardar extras" if lang=="Español" else "Save extras")
    if submit_extras:
        # compute today's totals and save a summary JSON
        df_all = pd.read_csv(csvp)
        df_today = df_all[df_all["fecha"]==date.today().isoformat()]
        total_viajes = len(df_today)
        bonos = 0.0
        # calcular bonos simple local (thresholds same as before)
        weekday = datetime.today().weekday()
        if weekday <= 3:
            table = {13:16,17:9,21:12,25:16}
        elif weekday in (4,5):
            table = {13:15,17:10,21:13,25:15}
        else:
            table = {12:14,16:10,19:11,23:14}
        for thr, amt in table.items():
            if total_viajes >= thr:
                bonos += amt
        ingresos_brutos = df_today["total_viaje"].sum() + extras_total + bonos
        total_neto = round(float(ingresos_brutos) - float(gastos_varios) - float(combustible),2)
        summary = {"date": date.today().isoformat(), "total_viajes": int(total_viajes), "bonos": bonos, "extras_total": extras_total, "gastos": gastos_varios, "combustible": combustible, "total_neto": total_neto}
        # write summary to a file per user
        sum_path = os.path.join(BASE_DIR, f"{alias}_summary_{date.today().isoformat()}.json")
        with open(sum_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        st.success("Resumen guardado ✅" if lang=="Español" else "Summary saved ✅")
        # generate image and show
        # generate image and show
        buf = generate_balance_image(df_today.to_dict("records"), extras_total, gastos_varios, combustible, bonos, alias)
        st.image(buf, use_column_width=True)
        st.download_button(
            "Descargar imagen (PNG)" if lang == "Español" else "Download image (PNG)",
            data=buf,
            file_name=f"balance_{date.today().isoformat()}.png",
            mime="image/png"
        )

# download CSV button (moved outside of form)
if os.path.exists(csvp):
    with open(csvp, "rb") as f:
        st.download_button(
            "Descargar CSV (todos tus registros)" if lang == "Español" else "Download CSV (all your records)",
            data=f,
            file_name=os.path.basename(csvp),
            mime="text/csv"
        )
# logout option
if st.button("Cerrar sesión" if lang=="Español" else "Logout"):
    if "user" in st.session_state:
        del st.session_state["user"]
    st.experimental_rerun()