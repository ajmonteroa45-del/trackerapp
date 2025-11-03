import streamlit as st
import pandas as pd
import os, re
from datetime import date, datetime
from io import BytesIO
import matplotlib.pyplot as plt
from PIL import Image

# Importamos las bibliotecas de OAuth
from streamlit_oauth import OAuth2Component
import jwt
import base64 
import json

# Importamos las utilidades actualizadas
import tracker_utils as tu 


# ----- CONFIGURACIÓN GENERAL Y ESTILOS -----
st.set_page_config(page_title="Trip Counter", layout="wide", initial_sidebar_state="auto")
APP_NAME = "Trip Counter"
BUTTON_COLOR = "#1034A6" # azul rey

# Lógica de estilos (Mantenida de tu código anterior)
st.markdown(f"""
    <style>
        .stButton>button {{
            background-color: {BUTTON_COLOR};
            color: white;
            border-radius: 12px;
            border: 0;
            padding: 10px 24px;
        }}
    </style>
""", unsafe_allow_html=True)


# ----- 🔑 CONFIGURACIÓN DE OAUTH -----

def decode_jwt_payload(encoded_jwt):
    """Decodifica el payload de un JWT (ID Token) con manejo de padding."""
    try:
        header, payload, signature = encoded_jwt.split('.')
        payload_decoded = base64.urlsafe_b64decode(payload + '==').decode('utf-8')
        return json.loads(payload_decoded)
    except Exception as e:
        st.error(f"Error al decodificar token JWT: {e}")
        return None

try:
    client_id = st.secrets.oauth.client_id
    client_secret = st.secrets.oauth.client_secret
    redirect_uri = st.secrets.oauth.redirect_uri

    AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
    scope = "openid email profile"

    oauth2 = OAuth2Component(client_id=client_id,
                             client_secret=client_secret,
                             authorize_endpoint=AUTHORIZE_ENDPOINT,
                             token_endpoint=TOKEN_ENDPOINT,
                             refresh_token_endpoint=TOKEN_ENDPOINT,
                             revoke_endpoint=REVOKE_ENDPOINT,
                             redirect_uri=redirect_uri,
                             scope=scope)
except AttributeError:
    # Este error se mostrará antes de que Streamlit detenga la app
    st.error("Error de configuración: Los secretos de OAuth no están definidos en st.secrets.")
    st.stop()


# ----- 🚪 LÓGICA DE LOGIN EN BARRA LATERAL (OAuth) -----

if 'auth_status' not in st.session_state:
    st.session_state.auth_status = None
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'trips_temp' not in st.session_state:
    st.session_state["trips_temp"] = []
if 'extras_temp' not in st.session_state:
    st.session_state["extras_temp"] = []
if 'gastos_temp' not in st.session_state:
    st.session_state["gastos_temp"] = []

st.sidebar.markdown(f"## 👤 {APP_NAME}")

# --- LOGIN ---
if st.session_state.auth_status != 'authenticated':
    # Muestra el botón de inicio de sesión
    result = oauth2.authorize_button(
        name="Iniciar Sesión con Google",
        icon="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg",
        key="oauth_login_button",
        extras_params={"prompt": "select_account"},
        use_container_width=True
    )

    if result:
        st.session_state.token = result
        user_info = decode_jwt_payload(st.session_state.token['id_token'])

        if user_info and 'email' in user_info:
            st.session_state.user_email = user_info['email'] 
            st.session_state.auth_status = 'authenticated'
            st.experimental_rerun()
        else:
            st.session_state.auth_status = 'failed'
            st.sidebar.error("Fallo al obtener el email de Google.")

elif st.session_state.auth_status == 'authenticated':
    st.sidebar.success(f"Bienvenido/a: **{st.session_state.user_email}**")
    
    if st.sidebar.button("Cerrar Sesión", key="logout_btn"):
        # Limpiar todos los estados de sesión
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.experimental_rerun()

else:
    st.sidebar.error("Error de autenticación. Por favor, inténtalo de nuevo.")
    if st.sidebar.button("Reintentar"):
        st.session_state.auth_status = None
        st.experimental_rerun()

# --- VALIDACIÓN DE AUTENTICACIÓN ---
if st.session_state.auth_status != 'authenticated':
    st.title("Inicia Sesión para Acceder a Trip Counter")
    st.info("Utiliza el botón en la barra lateral izquierda para iniciar sesión con Google.")
    st.stop()
    
# Definir el alias (el identificador único)
alias = st.session_state.user_email


# ----- TABS Y LÓGICA PRINCIPAL (ADAPTADA) -----

st.title(f"Registro de Viajes de {alias}")

tab_trips, tab_extra, tab_gastos, tab_km, tab_summaries, tab_export = st.tabs([
    "Uber/Didi", "Viajes Extra", "Gastos", "Kilometraje y Resumen", "Histórico", "Exportar"
])


# --- TAB: REGISTRAR VIAJES ---
with tab_trips:
    # ... (El código de registro de viajes se mantiene, pero usará 'alias' para guardar)
    st.markdown("### 🚗 Registrar Viajes (Uber/Didi)")
    # ... (Tu código de interfaz para registrar viajes) ...
    
    # Ejemplo de cómo se guardaría un viaje en trips_temp:
    if st.button("Guardar Viaje"):
        # ... (Tu lógica de validación) ...
        # (Asegúrate de que 'alias' se añada a los datos al guardarlos en Google Sheets)
        pass # Mantener tu lógica de interfaz aquí

    if st.session_state["trips_temp"]:
        st.dataframe(pd.DataFrame(st.session_state["trips_temp"]), use_container_width=True)


# --- TAB: GASTOS ---
with tab_gastos:
    # ... (El código de registro de gastos se mantiene) ...
    pass # Mantener tu lógica de interfaz aquí


# --- TAB: KILOMETRAJE Y GENERAR RESUMEN (El Bloque Crucial) ---
with tab_km:
    st.markdown("### 🧭 Kilometraje final y generar resumen")
    combustible_in = st.number_input("Combustible gastado (S/)", min_value=0.0, format="%.2f", key="comb_final")
    km_final = st.number_input("Kilometraje final del día (km)", min_value=0.0, format="%.1f", key="km_final")
    
    if st.button("Generar resumen final y guardar", key="generate_summary_btn"):
        if km_final <= 0:
            st.error("Debes ingresar el kilometraje final para generar el resumen.")
        else:
            # 1. Preparar y guardar TODOS los viajes/gastos del día en Sheets
            all_new_trips = st.session_state["trips_temp"] + st.session_state["extras_temp"]
            
            # (Aquí iría la lógica completa de cargar, concatenar y guardar en GSHEET_TRIPS_TITLE 
            # y GSHEET_GASTOS_TITLE, asegurando que se añade la columna 'alias' = user_email)
            
            # 2. Recargar y calcular resumen del día (cargando desde Sheets)
            df_all_trips = tu.load_data_from_sheet(tu.GSHEET_TRIPS_TITLE)
            df_all_gastos = tu.load_data_from_sheet(tu.GSHEET_GASTOS_TITLE)

            today_str = date.today().isoformat()
            trips_rows = df_all_trips[(df_all_trips["alias"] == alias) & (df_all_trips["fecha"] == today_str)].to_dict("records")
            gastos_rows = df_all_gastos[(df_all_gastos["alias"] == alias) & (df_all_gastos["fecha"] == today_str)].to_dict("records")
            
            # Cálculos de totales (debes adaptar estas funciones si no están en utilidades)
            ingresos = sum(float(r.get("total_viaje", 0)) for r in trips_rows)
            gastos_total = sum(float(g.get("monto", 0)) for g in gastos_rows)
            neto = round(ingresos - gastos_total - combustible_in, 2)
            viajes_num = len(trips_rows)
            bono = tu.calculate_bonuses(viajes_num) # Uso de la función de utilidades

            # 3. Guardar el resumen en la hoja GSHEET_SUMMARIES_TITLE
            success = tu.save_daily_data(
                alias, 
                pd.DataFrame(trips_rows), # Pasar los viajes de hoy
                0, # Extras
                gastos_total, 
                combustible_in, 
                km_final, 
                bono, 
                neto
            )

            if success:
                st.success("Resumen generado y guardado ✅ (en Google Sheets)")
                # Limpiar temporales de sesión
                st.session_state["trips_temp"] = []
                st.session_state["extras_temp"] = []
                st.session_state["gastos_temp"] = []
                st.write(f"**Balance Neto:** S/ {neto}")
            else:
                st.error("Fallo al guardar el resumen en Google Sheets.")


# --- TAB: HISTÓRICO ---
with tab_summaries:
    st.markdown("### 📋 Resúmenes guardados")
    df_summaries = tu.load_data_from_sheet(tu.GSHEET_SUMMARIES_TITLE)
    df_user_summaries = df_summaries[df_summaries["alias"] == alias]
    
    if df_user_summaries.empty:
        st.info("No hay resúmenes guardados para este usuario.")
    else:
        st.dataframe(df_user_summaries, use_container_width=True)

# --- TAB: EXPORTAR ---
with tab_export:
    st.markdown("### 📁 Exportar datos")
    # ... (El código de exportación se mantiene, filtrando siempre por 'alias' = user_email) ...
    pass # Mantener tu lógica de interfaz aquí
