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
# Asegúrate de que este archivo 'tracker_utils.py' esté disponible.
import tracker_utils as tu 


# ----- CONFIGURACIÓN GENERAL Y ESTILOS -----
# Revisión: Se mantiene solo una vez y se recomienda el layout "wide"
st.set_page_config(page_title="Trip Counter", layout="wide", initial_sidebar_state="auto")
APP_NAME = "Trip Counter"
BUTTON_COLOR = "#1034A6" # Color de tu marca (azul rey)

# Lógica de inyección de estilos (Solución FINAL para la imagen de fondo)
# Nota: La URL de la imagen (postimages) DEBE ser pública y estable.
st.markdown(f"""
    <style>
        /* 0. FUERZA LA TRANSPARENCIA EN EL CUERPO (Good Practice) */
        body {{
            background-color: transparent !important;
        }}

        /* 1. ESTILO PARA LOS BOTONES */
        .stButton>button {{
            background-color: {BUTTON_COLOR};
            color: white;
            border-radius: 12px;
            border: 0;
            padding: 10px 24px;
        }}

        /* 2. BACKGROUND CON IMAGEN (Nivel 1: El cuerpo principal de la App) */
        /* Forzamos la imagen y transparencia al contenedor de la aplicación */
        [data-testid="stAppViewContainer"] {{
            /* URL DIRECTA DE POSTIMAGES */
            background-image: url("https://i.postimg.cc/Zvp9CHdC/background.jpg") !important; 
            background-size: cover !important; /* Asegura que la imagen cubra todo el espacio */
            background-attachment: fixed !important; /* Fija la imagen para que no se mueva al hacer scroll */
            background-position: center center !important; /* Centra la imagen */
            background-color: transparent !important;
        }}
        
        /* 3. FONDO TRANSPARENTE EN EL CONTENIDO PRINCIPAL */
        /* Hacemos que el contenedor principal de contenido sea transparente */
        [data-testid="stAppViewContainer"] > .main {{
            background-image: none !important; 
            background-color: transparent !important; 
        }}
        
        /* 4. HACER QUE LOS HEADERS Y TEXTO SE VEAN BIEN SOBRE EL FONDO */
        h1, h2, h3, h4, .stMarkdown, .stInfo, .stSuccess, .stError {{
            color: white !important; /* Color blanco para el texto sobre el fondo oscuro */
            /* Agregamos una sombra de texto ligera para mejorar la legibilidad */
            text-shadow: 2px 2px 4px #000000; 
        }}

        /* 5. HACER QUE EL SIDEBAR RESALTE */
        [data-testid="stHeader"] {{
            background-color: rgba(12, 21, 42, 0.7) !important; 
        }}
        [data-testid="stSidebar"] {{
            background-color: rgba(26, 43, 66, 0.8) !important; 
            color: white;
        }}
        
        /* Hacemos que los widgets dentro del sidebar también sean más legibles */
        [data-testid="stSidebar"] .stMarkdown {{
            color: white !important; 
            text-shadow: none;
        }}
        
    </style>
""", unsafe_allow_html=True)


# ----- 🔑 CONFIGURACIÓN DE OAUTH -----

def decode_jwt_payload(encoded_jwt):
    """Decodifica el payload de un JWT (ID Token) con manejo de padding.)"""
    try:
        header, payload, signature = encoded_jwt.split('.')
        # Agrega padding si es necesario
        payload_decoded = base64.urlsafe_b64decode(payload + '==').decode('utf-8')
        return json.loads(payload_decoded)
    except Exception as e:
        # En caso de error, no muestra el token
        # st.error(f"Error al decodificar JWT: {e}") # Se comenta para evitar mostrar errores al usuario
        return None

try:
    client_id = st.secrets.oauth.client_id
    client_secret = st.secrets.oauth.client_secret
    redirect_uri = st.secrets.oauth.redirect_uri 

    AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    REFRESH_TOKEN_ENDPOINT = TOKEN_ENDPOINT
    scope = "openid email profile"

    # --- INICIALIZACIÓN DE OAUTH2COMPONENT (Compatible con 0.1.14) ---
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
            st.rerun() # Revisión: Usar st.rerun() en lugar de st.experimental_rerun()
        else:
            st.session_state.auth_status = 'failed'
            st.sidebar.error("Fallo al obtener el email de Google.")

elif st.session_state.auth_status == 'authenticated':
    st.sidebar.success(f"Bienvenido/a: **{st.session_state.user_email}**")
    
    if st.sidebar.button("Cerrar Sesión", key="logout_btn"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun() # Revisión: Usar st.rerun() en lugar de st.experimental_rerun()

else:
    st.sidebar.error("Error de autenticación. Por favor, inténtalo de nuevo.")
    if st.sidebar.button("Reintentar"):
        st.session_state.auth_status = None
        st.rerun() # Revisión: Usar st.rerun() en lugar de st.experimental_rerun()

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

# Aquí iría el contenido de cada pestaña (tu lógica original de la aplicación)
# Ejemplo:
with tab_trips:
    st.header("Registro de Viajes de Plataforma")
    # ... tu código para registrar viajes aquí ...