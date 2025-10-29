
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
        buf = generate_balance_image(df_today.to_dict("records"), extras_total, gastos_varios, combustible, bonos, alias)
        st.image(buf, use_column_width=True)
        # offer download of CSV and image
        with open(csvp, "rb") as f:
            st.download_button("Descargar CSV (todos tus registros)" if lang=="Español" else "Download CSV (all your records)", data=f, file_name=os.path.basename(csvp), mime="text/csv")
        # image download
        st.download_button("Descargar imagen (PNG)" if lang=="Español" else "Download image (PNG)", data=buf, file_name=f"balance_{date.today().isoformat()}.png", mime="image/png")

# logout option
if st.button("Cerrar sesión" if lang=="Español" else "Logout"):
    if "user" in st.session_state:
        del st.session_state["user"]
    st.experimental_rerun()
