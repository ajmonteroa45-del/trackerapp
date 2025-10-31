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
try:
    conn = st.connection("gsheets", type=st.secrets.connections.gsheets.type)
except AttributeError:
    st.error("Error de configuración: Las credenciales de Google Sheets no están definidas en st.secrets.")
    st.stop()
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()


# ----- Helpers Actualizados (Google Sheets) -----

@st.cache_data(ttl=3600) # Cache para reducir llamadas a la API de Sheets
def load_data_from_sheet(sheet_title):
    try:
        # st.connection maneja la carga de datos como DataFrame
        df = conn.read(spreadsheet=sheet_title, usecols=list(range(20)), ttl=5)
        # Asegurarse de que las columnas vacías no se conviertan en objetos innecesarios
        return df.dropna(how='all', axis=1)
    except Exception as e:
        # En el primer despliegue, la hoja no existirá; crear un DataFrame vacío
        if "spreadsheet not found" in str(e).lower():
            if sheet_title == GSHEET_USERS_TITLE:
                return pd.DataFrame(columns=["alias", "pin_hash"])
            # MODIFICACIÓN 1: Añadir "ganancia_por_hora" a la hoja de Trips
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
    df = load_data_from_sheet(GSHEET_USERS_TITLE)
    return {row['alias']: {"pin_hash": row['pin_hash']} for index, row in df.iterrows()} if not df.empty else {}

def save_users(u):
    df = pd.DataFrame([{"alias": k, "pin_hash": v["pin_hash"]} for k, v in u.items()])
    # Sobreescribir toda la hoja.
    conn.write(df, spreadsheet=GSHEET_USERS_TITLE)
    # Invalidar caché para forzar la recarga
    load_data_from_sheet.clear()

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
            u = load_users() # Carga desde Sheets
            if alias_input in u:
                st.sidebar.error("Alias ya existe. Elige otro.")
            else:
                u[alias_input] = {"pin_hash": hash_pin(pin_input)}
                save_users(u) # Guarda en Sheets
                # Ya no es necesario 'ensure_user_csv/gastos', Sheets se maneja al leer/escribir.
                st.session_state["user"] = alias_input
                st.sidebar.success("Usuario creado ✅")

# Si el usuario no ha iniciado sesión, detenemos la ejecución del resto de la app
if not alias:
    st.info("Ingresa o regístrate para usar el Trip Counter.")
    st.stop()


# ----- Tabs (top menu) y Session State -----
# Se asume que aquí va el código de tabs y session state
tabs = st.tabs(["Registrar viajes", "Viajes extra", "Gastos", "Kilometraje y Generar resumen", "Resúmenes", "Imágenes", "Exportar / Descargar"])
tab_trips, tab_extras, tab_gastos, tab_km, tab_summaries, tab_images, tab_export = tabs

if "trips_temp" not in st.session_state:
    st.session_state["trips_temp"] = []
if "extras_temp" not in st.session_state:
    st.session_state["extras_temp"] = []
if "gastos_temp" not in st.session_state:
    st.session_state["gastos_temp"] = []


# ---- Tab: Registrar viajes (CON LÓGICA GPH) ----
with tab_trips:
    st.markdown("### ➕ Registrar viaje")
    col1, col2, col3, col4 = st.columns([2,2,2,1])
    with col1:
        hi = st.text_input("Hora inicio (HH:MM)", key="trip_hi")
    with col2:
        hf = st.text_input("Hora fin (HH:MM)", key="trip_hf")
    with col3:
        gan = st.number_input("Ganancia base S/ ", min_value=0.0, format="%.2f", key="trip_gan")
    with col4:
        aer = st.checkbox("Aeropuerto (+S/6.50)", key="trip_aer")
    prop = st.number_input("Propina S/ ", min_value=0.0, format="%.2f", key="trip_prop")

    # MODIFICACIÓN 2: Lógica de GPH para viajes normales
    if st.button("Agregar viaje", key="add_trip_btn"):
        # validations
        errors = []
        if not validate_time_string(hi):
            errors.append("Hora inicio inválida. Formato HH:MM")
        if not validate_time_string(hf):
            errors.append("Hora fin inválida. Formato HH:MM")
        if errors:
            st.error("; ".join(errors))
        else:
            # --- INICIA LÓGICA DE GPH ---
            hi_str = hi.strip()
            hf_str = hf.strip()
            
            fmt = "%H:%M"
            t_inicio = datetime.strptime(hi_str, fmt)
            t_fin = datetime.strptime(hf_str, fmt)

            # Manejo de cruce de medianoche
            if t_fin < t_inicio:
                duracion = (t_fin + timedelta(days=1)) - t_inicio
            else:
                duracion = t_fin - t_inicio
            
            duracion_en_horas = duracion.total_seconds() / 3600.0

            aeropuerto_val = 6.5 if aer else 0.0
            total_v = round(float(gan) + aeropuerto_val + float(prop), 2)
            gph = 0.0
            if duracion_en_horas > 0:
                gph = round(total_v / duracion_en_horas, 2)
            # --- FIN LÓGICA DE GPH ---

            existing_count = sum(1 for r in st.session_state["trips_temp"])
            trip = {
                "fecha": date.today().isoformat(),
                "tipo": "normal",
                "viaje_num": existing_count + 1,
                "hora_inicio": hi_str,
                "hora_fin": hf_str,
                "ganancia_base": float(gan),
                "aeropuerto": aeropuerto_val,
                "propina": float(prop),
                "total_viaje": total_v,
                "ganancia_por_hora": gph  # <-- CAMPO AÑADIDO
            }
            st.session_state["trips_temp"].append(trip)
            st.success(f"Viaje agregado (GPH: S/ {gph}) ✅") # <-- Feedback inmediato

    # Mostrar viajes temporales
    if st.session_state["trips_temp"]:
        st.markdown("#### Viajes agregados hoy (pendientes de guardar)")
        df_temp = pd.DataFrame(st.session_state["trips_temp"])
        st.dataframe(df_temp)

# ---- Tab: Viajes extra (CON LÓGICA GPH y SIN AEROPUERTO) ----
with tab_extras:
    st.markdown("### ✚ Registrar viaje extra (fuera de la app)")
    # MODIFICACIÓN 3.1: Se eliminó la columna del checkbox de aeropuerto
    col1, col2, col3 = st.columns(3) 
    with col1:
        hi_e = st.text_input("Hora inicio (HH:MM)", key="extra_hi")
    with col2:
        hf_e = st.text_input("Hora fin (HH:MM)", key="extra_hf")
    with col3:
        gan_e = st.number_input("Ganancia S/ ", min_value=0.0, format="%.2f", key="extra_gan")
    
    prop_e = st.number_input("Propina S/ ", min_value=0.0, format="%.2f", key="extra_prop")
    
    # MODIFICACIÓN 3.2: Lógica de GPH para viajes extra (sin tarifa de aeropuerto)
    if st.button("Agregar viaje extra", key="add_extra_btn"):
        errors = []
        if not validate_time_string(hi_e):
            errors.append("Hora inicio inválida. Formato HH:MM")
        if not validate_time_string(hf_e):
            errors.append("Hora fin inválida. Formato HH:MM")
        if errors:
            st.error("; ".join(errors))
        else:
            # --- INICIA LÓGICA DE GPH ---
            hi_str = hi_e.strip()
            hf_str = hf_e.strip()
            fmt = "%H:%M"
            t_inicio = datetime.strptime(hi_str, fmt)
            t_fin = datetime.strptime(hf_str, fmt)

            if t_fin < t_inicio:
                duracion = (t_fin + timedelta(days=1)) - t_inicio
            else:
                duracion = t_fin - t_inicio
            
            duracion_en_horas = duracion.total_seconds() / 3600.0

            # CÁLCULO DE TOTAL (SIN AEROPUERTO)
            total_v = round(float(gan_e) + float(prop_e), 2)
            
            gph = 0.0
            if duracion_en_horas > 0:
                gph = round(total_v / duracion_en_horas, 2)
            # --- FIN LÓGICA DE GPH ---

            extra_trip = {
                "fecha": date.today().isoformat(),
                "tipo": "extra",
                "viaje_num": len(st.session_state["extras_temp"]) + 1,
                "hora_inicio": hi_str,
                "hora_fin": hf_str,
                "ganancia_base": float(gan_e),
                "aeropuerto": 0.0,  # Se mantiene en 0.0 para consistencia de la tabla
                "propina": float(prop_e),
                "total_viaje": total_v,
                "ganancia_por_hora": gph # <-- CAMPO AÑADIDO
            }
            st.session_state["extras_temp"].append(extra_trip)
            st.success(f"Viaje extra agregado (GPH: S/ {gph}) ✅")

    # Mostrar viajes temporales
    if st.session_state["extras_temp"]:
        st.markdown("#### Viajes extra agregados hoy (pendientes de guardar)")
        df_temp = pd.DataFrame(st.session_state["extras_temp"])
        st.dataframe(df_temp)

# ---- Tab: Gastos ----
with tab_gastos:
    st.markdown("### 💸 Registrar gastos")
    
    concepto_in = st.text_input("Concepto (ej: almuerzo, peaje, lavado)", key="gasto_concepto")
    monto_in = st.number_input("Monto (S/)", min_value=0.0, format="%.2f", key="gasto_monto")
    
    if st.button("Agregar gasto", key="add_gasto_btn"):
        if not concepto_in or monto_in <= 0:
            st.error("Concepto y monto válidos requeridos.")
        else:
            gasto = {
                "fecha": date.today().isoformat(),
                "concepto": concepto_in.strip(),
                "monto": float(monto_in)
            }
            st.session_state["gastos_temp"].append(gasto)
            st.success("Gasto agregado ✅")

    # Mostrar gastos temporales
    if st.session_state["gastos_temp"]:
        st.markdown("#### Gastos agregados hoy (pendientes de guardar)")
        df_temp = pd.DataFrame(st.session_state["gastos_temp"])
        st.dataframe(df_temp)


# ---- Tab: Kilometraje y generar resumen (Lógica de guardado en Sheets) ----
with tab_km:
    st.markdown("### 🧭 Kilometraje final y generar resumen")
    combustible_in = st.number_input("Combustible gastado (S/)", min_value=0.0, format="%.2f", key="comb_final")
    km_final = st.number_input("Kilometraje final del día (km)", min_value=0.0, format="%.1f", key="km_final")
    if st.button("Generar resumen final y guardar (se requiere kilometraje)", key="generate_summary_btn"):
        if km_final <= 0:
            st.error("Debes ingresar el kilometraje final para generar el resumen.")
        else:
            # 1. Preparar datos unificados para guardar
            all_new = st.session_state["trips_temp"] + st.session_state["extras_temp"]
            if all_new:
                # Añadir columna 'alias' a los nuevos viajes
                df_new = pd.DataFrame(all_new)
                df_new["alias"] = alias
                
                # Cargar, concatenar y guardar TODOS los viajes en el sheet
                df_existing = load_data_from_sheet(GSHEET_TRIPS_TITLE)
                df_all = pd.concat([df_existing, df_new], ignore_index=True)
                conn.write(df_all, spreadsheet=GSHEET_TRIPS_TITLE)
                load_data_from_sheet.clear() # Invalidar caché
            
            # 2. Guardar gastos en el sheet
            if st.session_state["gastos_temp"]:
                # Añadir columna 'alias' a los nuevos gastos
                df_gastos_new = pd.DataFrame(st.session_state["gastos_temp"])
                df_gastos_new["alias"] = alias

                # Cargar, concatenar y guardar TODOS los gastos en el sheet
                df_gastos_existing = load_data_from_sheet(GSHEET_GASTOS_TITLE)
                df_gastos_all = pd.concat([df_gastos_existing, df_gastos_new], ignore_index=True)
                conn.write(df_gastos_all, spreadsheet=GSHEET_GASTOS_TITLE)
                load_data_from_sheet.clear() # Invalidar caché

            # 3. Recargar y crear resumen
            df_all_trips = load_data_from_sheet(GSHEET_TRIPS_TITLE)
            df_all_gastos = load_data_from_sheet(GSHEET_GASTOS_TITLE)

            # Filtrar solo viajes/gastos del usuario y de hoy
            today_str = date.today().isoformat()
            trips_rows = df_all_trips[(df_all_trips["alias"] == alias) & (df_all_trips["fecha"] == today_str)].to_dict("records")
            gastos_rows = df_all_gastos[(df_all_gastos["alias"] == alias) & (df_all_gastos["fecha"] == today_str)].to_dict("records")

            # Crea el resumen y genera la imagen en memoria (BytesIO)
            summary, image_buffer = save_summary_and_image(alias, trips_rows, gastos_rows, combustible_in, km_final)

            # Limpiar temporales de sesión
            st.session_state["trips_temp"] = []
            st.session_state["extras_temp"] = []
            st.session_state["gastos_temp"] = []

            st.success("Resumen generado y guardado ✅ (en Google Sheets)")
            st.write("**Resumen:**")
            st.json(summary)
            
            # Mostrar la imagen desde el buffer (ya no hay path local)
            st.image(image_buffer, use_column_width=True, caption=f"Balance {today_str}")
            
            # Ofrecer descargas (CSV de todos los viajes del usuario y la imagen actual)
            # 1. Descarga del CSV (filtrando solo los del usuario)
            df_user_trips = df_all_trips[df_all_trips["alias"] == alias]
            csv_trips_buffer = BytesIO()
            df_user_trips.to_csv(csv_trips_buffer, index=False)
            csv_trips_buffer.seek(0)
            st.download_button("📁 Descargar CSV de todos los viajes", data=csv_trips_buffer, file_name=f"{alias}_viajes_totales.csv", mime="text/csv")
            
            # 2. Descarga de la imagen (desde el buffer generado)
            st.download_button("🖼️ Descargar imagen del balance", data=image_buffer, file_name=f"{alias}_balance_{today_str}.png", mime="image/png")

# ---- Tab: Resúmenes (Carga desde Sheets) ----
with tab_summaries:
    st.markdown("### 📋 Resúmenes guardados")
    df_summaries = load_data_from_sheet(GSHEET_SUMMARIES_TITLE)
    df_user_summaries = df_summaries[df_summaries["alias"] == alias]
    
    if df_user_summaries.empty:
        st.info("No hay resúmenes guardados.")
    else:
        # Sort by date
        df_user_summaries = df_user_summaries.sort_values(by="date", ascending=False)
        files_sorted = df_user_summaries["date"].tolist()
        
        sel_date = st.selectbox("Selecciona un resumen por fecha", options=files_sorted, key="sel_summary")
        if sel_date:
            data = df_user_summaries[df_user_summaries["date"] == sel_date].iloc[0].to_dict()
            st.json(data)
            
            # Se omite la carga de imagen por su ID ya que no tenemos un sistema de almacenamiento de imágenes.

# ---- Tab: Imágenes (Ahora solo muestra la tabla de resúmenes) ----
with tab_images:
    st.markdown("### 🖼️ Imágenes de balances (Histórico en resúmenes)")
    st.info("Dado el entorno de nube, las imágenes no se almacenan permanentemente. Consulta la pestaña 'Resúmenes' para ver los datos del balance.")
    # Si quieres una lista de todos los resúmenes (que tienen el ID de la imagen)
    if not df_user_summaries.empty:
        st.dataframe(df_user_summaries[["date", "ingresos", "gastos", "total_neto"]].head(10), use_container_width=True)

# ---- Tab: Exportar / Descargar (Actualizado) ----
with tab_export:
    st.markdown("### 📁 Exportar datos")
    
    # Descargar todos los viajes
    df_all_trips = load_data_from_sheet(GSHEET_TRIPS_TITLE)
    df_user_trips = df_all_trips[df_all_trips["alias"] == alias]
    if not df_user_trips.empty:
        csv_trips_buffer = BytesIO()
        df_user_trips.to_csv(csv_trips_buffer, index=False)
        csv_trips_buffer.seek(0)
        st.download_button("📥 Descargar CSV (todos tus viajes)", data=csv_trips_buffer, file_name=f"{alias}_viajes_totales.csv", mime="text/csv")
    else:
        st.info("Aún no hay registro de viajes.")

    # Descargar todos los gastos
    df_all_gastos = load_data_from_sheet(GSHEET_GASTOS_TITLE)
    df_user_gastos = df_all_gastos[df_all_gastos["alias"] == alias]
    if not df_user_gastos.empty:
        csv_gastos_buffer = BytesIO()
        df_user_gastos.to_csv(csv_gastos_buffer, index=False)
        csv_gastos_buffer.seek(0)
        st.download_button("📥 Descargar CSV (gastos)", data=csv_gastos_buffer, file_name=f"{alias}_gastos_totales.csv", mime="text/csv")
    else:
        st.info("Aún no hay registro de gastos.")
        
    st.write("")
    
    # Vaciar todos los registros (¡cuidado!) - Se requiere lógica para eliminar filas
    if st.button("Vaciar todos los registros (¡cuidado!)"):
        # Se necesita la lógica para filtrar y eliminar solo las filas del alias
        try:
            # 1. Trips
            df_trips = load_data_from_sheet(GSHEET_TRIPS_TITLE)
            df_trips_cleaned = df_trips[df_trips["alias"] != alias]
            conn.write(df_trips_cleaned, spreadsheet=GSHEET_TRIPS_TITLE)

            # 2. Gastos
            df_gastos = load_data_from_sheet(GSHEET_GASTOS_TITLE)
            df_gastos_cleaned = df_gastos[df_gastos["alias"] != alias]
            conn.write(df_gastos_cleaned, spreadsheet=GSHEET_GASTOS_TITLE)
            
            # 3. Summaries
            df_summaries = load_data_from_sheet(GSHEET_SUMMARIES_TITLE)
            df_summaries_cleaned = df_summaries[df_summaries["alias"] != alias]
            conn.write(df_summaries_cleaned, spreadsheet=GSHEET_SUMMARIES_TITLE)
            
            load_data_from_sheet.clear() # Invalidar todo el caché
            st.success("Registros eliminados de Google Sheets para el usuario.")
        except Exception as e:
            st.error("Error al eliminar archivos: " + str(e))

# ---- Logout button at bottom ----
if alias and st.sidebar.button(f"Cerrar sesión ({alias})"):
    st.session_state["user"] = None
    st.rerun()