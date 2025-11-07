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
# Asegúrate de que este archivo esté limpio de conflictos.
import tracker_utils as tu 


# ----- CONFIGURACIÓN GENERAL Y ESTILOS -----
st.set_page_config(page_title="Trip Counter", layout="wide", initial_sidebar_state="auto")
APP_NAME = "Trip Counter"
BUTTON_COLOR = "#1034A6" # Color de tu marca (azul rey)


# Lógica de inyección de estilos (Corrige los errores y añade el fondo y opacidad)
st.markdown(f"""
    <style>
        /* 1. ESTILO PARA LOS BOTONES */
        .stButton>button {{
            background-color: {BUTTON_COLOR};
            color: white;
            border-radius: 12px;
            border: 0;
            padding: 10px 24px;
        }}

        /* 2. BACKGROUND CON IMAGEN (Mejora Visual) */
        [data-testid="stAppViewContainer"] > .main {{
            /* 🛑 REEMPLAZA ESTA URL con la URL RAW de tu imagen en GitHub 🛑 */
            background-image: url("https://github.com/ajmonteroa45-del/trackerapp/blob/main/assets/background.jpg?raw=true"); 
            background-size: cover;
            background-position: center;
            background-attachment: fixed; 
        }}

        /* 3. HACER QUE EL TEXTO Y SIDEBAR RESALTEN (USANDO COLORES DE TU TEMA OSCURO) */
        /* Hacemos el sidebar y header semi-transparentes para que se vea la imagen, pero el texto se lea */
        [data-testid="stHeader"] {{
            background-color: rgba(12, 21, 42, 0.7); 
        }}
        [data-testid="stSidebar"] {{
            background-color: rgba(26, 43, 66, 0.8); 
            color: white;
        }}
    </style>
""", unsafe_allow_html=True)


# ----- 🔑 CONFIGURACIÓN DE OAUTH -----

def decode_jwt_payload(encoded_jwt):
    """Decodifica el payload de un JWT (ID Token) con manejo de padding.)"""
    try:
        header, payload, signature = encoded_jwt.split('.')
        payload_decoded = base64.urlsafe_b64decode(payload + '==').decode('utf-8')
        return json.loads(payload_decoded)
    except Exception as e:
        # En caso de error, no muestra el token
        return None

try:
    client_id = st.secrets.oauth.client_id
    client_secret = st.secrets.oauth.client_secret
    redirect_uri = st.secrets.oauth.redirect_uri 

    AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    REFRESH_TOKEN_ENDPOINT = TOKEN_ENDPOINT
    scope = "openid email profile"

    # --- INICIALIZACIÓN DE OAUTH2COMPONENT ---
    oauth2 = OAuth2Component(client_id=client_id,
                             client_secret=client_secret,
                             authorize_endpoint=AUTHORIZE_ENDPOINT,
                             token_endpoint=TOKEN_ENDPOINT,
                             refresh_token_endpoint=REFRESH_TOKEN_ENDPOINT,
    )
except AttributeError:
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


# -----------------------------------
# LÓGICA DE INTERFAZ VISUAL: LOGO y CABECERA
# -----------------------------------
st.sidebar.markdown(f"## 👤 {APP_NAME}")

try:
    # Coloca tu logo en la parte superior de la barra lateral
    # Asegúrate de que tu logo se llama 'logo.png' y está en la carpeta 'assets'.
    st.sidebar.image("assets/logo.png", use_container_width=True) 
    st.sidebar.markdown("---")
except FileNotFoundError:
    st.sidebar.warning("Logo no encontrado. Verifica la ruta 'assets/logo.png'.")

# --- LOGIN ---
if st.session_state.auth_status != 'authenticated':
    # ENLACE A POLÍTICA DE PRIVACIDAD (USANDO EL SUBDOMINIO DE GO DADDY)
    st.markdown(
        f'<div style="text-align: center; margin-bottom: 1rem; font-size: small;">'
        f'Esta aplicación requiere iniciar sesión con Google.<br>'
        f'Lee nuestra <a href="https://policy.tripcounter.online" target="_blank">Política de Privacidad</a>.'
        f'</div>',
        unsafe_allow_html=True
    )

    result = oauth2.authorize_button(
        name="Iniciar Sesión con Google",
        icon="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg",
        key="oauth_login_button",
        extras_params={"prompt": "select_account"},
        use_container_width=True,
        redirect_uri=redirect_uri, 
        scope=scope,
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
    
alias = st.session_state.user_email


# ----- TABS Y LÓGICA PRINCIPAL -----

st.title(f"Registro de Viajes de {alias}")

tab_trips, tab_extra, tab_gastos, tab_km, tab_summaries, tab_export = st.tabs([
    "Uber/Didi", "Viajes Extra", "Gastos", "Kilometraje y Resumen", "Histórico", "Exportar"
])

# Lógica de las pestañas aquí (Asumiendo que esta lógica ya estaba en tu código original)
# ...