# app.py - Trip Counter (TrackerApp v3.0 - Cloud Ready)
import streamlit as st
import pandas as pd
import os, json, hashlib, re
from datetime import date, datetime
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
            if sheet_title == GSHEET_TRIPS_TITLE:
                return pd.DataFrame(columns=["alias", "fecha","tipo","viaje_num","hora_inicio","hora_fin","ganancia_base","aeropuerto","propina","total_viaje"])
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
# ... (código de estilos) ...


# ----- Sidebar: Login Actualizado -----
# ... (código de sidebar) ...
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

# ... (código para alias y st.stop()) ...


# ----- Tabs (top menu) y Session State (se mantiene) -----
# ... (código de tabs y session state) ...


# ---- Tab: Registrar viajes (se mantiene) ----
# ... (código de registro de viajes) ...


# ---- Tab: Viajes extra (se mantiene) ----
# ... (código de registro de viajes extra) ...


# ---- Tab: Gastos (se mantiene) ----
# ... (código de registro de gastos) ...


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

# ---- Logout button at bottom (se mantiene) ----
# ... (código de logout) ...