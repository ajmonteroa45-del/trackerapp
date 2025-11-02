# ================================================
# TripCounter v7.1 - Presupuestos + Alertas + Tema Oscuro
# Autor: Alexy Montero (desarrollo junto a ChatGPT)
# ================================================

import streamlit as st
import pandas as pd
import os, json, hashlib, re
from datetime import date, datetime, timedelta
from io import BytesIO
import matplotlib.pyplot as plt
from PIL import Image
import gspread
import google.oauth2.service_account

# ---------- CONFIGURACIÓN GLOBAL ----------
st.set_page_config(page_title="Trip Counter", layout="wide", initial_sidebar_state="auto")

APP_NAME = "Trip Counter"
BUTTON_COLOR = "#1034A6"  # Azul rey principal
BG_COLOR = "#1e1e1e"      # Fondo gris oscuro general
TEXT_COLOR = "#f0f0f0"    # Texto claro

# ---------- HOJAS DE GOOGLE SHEETS ----------
GSHEET_USERS_TITLE = "TripCounter_Users"
GSHEET_TRIPS_TITLE = "TripCounter_Trips"
GSHEET_GASTOS_TITLE = "TripCounter_Gastos"
GSHEET_SUMMARIES_TITLE = "TripCounter_Summaries"
GSHEET_PRESUPUESTO_TITLE = "TripCounter_Presupuesto"

SHEET_IDS = {
    GSHEET_USERS_TITLE: "1MxRbEz2ACwwZOPRZx_BEqLW74M7ZFh5j_CVovqaLi0o",
    GSHEET_TRIPS_TITLE: "1xoXm5gN1n_5rqLP2dd51OzXdW0LkhvrUwvAvrqcMWhY",
    GSHEET_GASTOS_TITLE: "1nQljTD3iywDoG4cCY8MBNi5WWXrECP7OXz3OJM2B1wo",
    GSHEET_SUMMARIES_TITLE: "1DR0dEfCHw6keqqYDXOj2N0tbX4osaKxRJdrMAAyBcy4",
    GSHEET_PRESUPUESTO_TITLE: "1zdqW0613MFNfhaJkNfvRy9VjgFvb_qHxD3Id3aQNR2Y",
}

# ---------- CONEXIÓN GSPREAD ----------
@st.cache_resource(ttl=3600)
def get_gspread_client():
    try:
        gspread_info = st.secrets["connections"]["gsheets"]
        creds_dict = {
            "type": gspread_info["type"],
            "project_id": gspread_info["project_id"],
            "private_key_id": gspread_info["private_key_id"],
            "private_key": gspread_info["private_key"].replace("\\n", "\n"),
            "client_email": gspread_info["client_email"],
            "client_id": gspread_info["client_id"],
            "auth_uri": gspread_info["auth_uri"],
            "token_uri": gspread_info["token_uri"],
            "auth_provider_x509_cert_url": gspread_info["auth_provider_x509_cert_url"],
            "client_x509_cert_url": gspread_info["client_x509_cert_url"]
        }
        credentials = google.oauth2.service_account.Credentials.from_service_account_info(creds_dict)
        client = gspread.Client(auth=credentials)
        return client
    except Exception as e:
        st.error(f"Error de autenticación: {e}")
        st.stop()

# ---------- FUNCIONES AUXILIARES ----------
def hash_pin(pin):
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()

def load_users():
    client = get_gspread_client()
    ws = client.open_by_key(SHEET_IDS[GSHEET_USERS_TITLE]).get_worksheet(0)
    data = ws.get_all_records()
    return {row['alias']: {"pin_hash": row['pin_hash']} for row in data}

def save_users(users):
    df = pd.DataFrame([{"alias": k, "pin_hash": v["pin_hash"]} for k, v in users.items()])
    client = get_gspread_client()
    ws = client.open_by_key(SHEET_IDS[GSHEET_USERS_TITLE]).get_worksheet(0)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

def load_presupuesto():
    client = get_gspread_client()
    ws = client.open_by_key(SHEET_IDS[GSHEET_PRESUPUESTO_TITLE]).get_worksheet(0)
    data = ws.get_all_records()
    return pd.DataFrame(data)

def save_presupuesto(df):
    client = get_gspread_client()
    ws = client.open_by_key(SHEET_IDS[GSHEET_PRESUPUESTO_TITLE]).get_worksheet(0)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

# ---------- ESTILO GLOBAL OSCURO ----------
st.markdown(
    f"""
    <style>
    body {{
        background-color: {BG_COLOR};
        color: {TEXT_COLOR};
    }}
    .stApp {{
        background-color: {BG_COLOR};
        color: {TEXT_COLOR};
    }}
    .stButton>button {{
        background-color: {BUTTON_COLOR};
        color: white;
        border-radius: 10px;
        padding: 8px 20px;
    }}
    .stButton>button:hover {{
        background-color: #0d297d;
    }}
    </style>
    """, unsafe_allow_html=True
)

# ---------- LOGIN ----------
st.sidebar.markdown(f"## 🔐 {APP_NAME}")
alias_input = st.sidebar.text_input("Alias / Nombre")
pin_input = st.sidebar.text_input("PIN (4-6 dígitos)", type="password", max_chars=6)
col1, col2 = st.sidebar.columns(2)

if col1.button("Entrar"):
    users = load_users()
    if alias_input in users and hash_pin(pin_input) == users[alias_input]["pin_hash"]:
        st.session_state["user"] = alias_input
        st.rerun()
    else:
        st.sidebar.error("Credenciales inválidas.")

if col2.button("Registrar"):
    users = load_users()
    if alias_input in users:
        st.sidebar.error("Alias ya existe.")
    else:
        users[alias_input] = {"pin_hash": hash_pin(pin_input)}
        save_users(users)
        st.session_state["user"] = alias_input
        st.rerun()

alias = st.session_state.get("user")
if not alias:
    st.stop()

# ---------- ALERTAS PRESUPUESTO ----------
def mostrar_alertas_presupuesto(df_pres):
    """Muestra alertas de pagos próximos o vencidos"""
    hoy = date.today()
    for _, row in df_pres.iterrows():
        if row['alias'] != alias or row.get("pagado") == "True":
            continue
        try:
            fecha_pago = datetime.strptime(row["fecha_pago"], "%Y-%m-%d").date()
        except Exception:
            continue

        dias_restantes = (fecha_pago - hoy).days

        if dias_restantes == 3:
            st.warning(f"🔔 En 3 días debes pagar **{row['categoria']} ({row['monto']} USD)**")
        elif dias_restantes == 0:
            st.error(f"⚠️ Hoy debes pagar **{row['categoria']} ({row['monto']} USD)**")

# ---------- INTERFAZ PRINCIPAL ----------
st.title(f"🚗 {APP_NAME}")
st.markdown(f"**Usuario:** <span style='color:#a3c4f3'>{alias}</span>", unsafe_allow_html=True)

# Cargar presupuesto
try:
    df_pres = load_presupuesto()
except Exception:
    df_pres = pd.DataFrame(columns=["alias", "categoria", "monto", "fecha_pago", "pagado"])

# Mostrar alertas
mostrar_alertas_presupuesto(df_pres)

tabs = st.tabs(["Crear y Editar Presupuestos", "Registrar viajes", "Otras opciones"])
tab_presupuesto, tab_viajes, tab_otras = tabs

# ---------- TAB 1: CREAR Y EDITAR PRESUPUESTOS ----------
with tab_presupuesto:
    st.subheader("💰 Crear nueva categoría de presupuesto")

    cat = st.text_input("Nombre de la categoría (ej: Alquiler, Luz, Internet)")
    monto = st.number_input("Monto mensual ($)", min_value=0.0, step=10.0)
    fecha_pago = st.date_input("Fecha de pago mensual")

    if st.button("Agregar categoría"):
        if cat.strip() == "":
            st.warning("Debe ingresar un nombre de categoría.")
        elif not df_pres.empty and ((df_pres["alias"] == alias) & (df_pres["categoria"].str.lower() == cat.lower())).any():
            st.error("⚠️ Ya existe una categoría con ese nombre.")
        else:
            nueva = pd.DataFrame([{
                "alias": alias,
                "categoria": cat,
                "monto": monto,
                "fecha_pago": fecha_pago.strftime("%Y-%m-%d"),
                "pagado": "False"
            }])
            df_pres = pd.concat([df_pres, nueva], ignore_index=True)
            save_presupuesto(df_pres)
            st.success("Categoría agregada correctamente ✅")
            st.rerun()

    st.markdown("---")
    st.subheader("🧾 Tus categorías registradas")

    df_user = df_pres[df_pres["alias"] == alias]

    if df_user.empty:
        st.info("No tienes categorías aún.")
    else:
        for idx, row in df_user.iterrows():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
            col1.markdown(f"**{row['categoria']}**")
            col2.markdown(f"${row['monto']}")
            col3.markdown(f"📅 {row['fecha_pago']}")
            if col4.button("Eliminar", key=f"del_{idx}"):
                if st.confirm("¿Seguro que deseas eliminar esta categoría?"):
                    df_pres = df_pres.drop(idx)
                    save_presupuesto(df_pres)
                    st.success("Categoría eliminada.")
                    st.rerun()

    st.markdown("---")
    st.subheader("✅ Marcar pagos completados")

    pendientes = df_user[df_user["pagado"] == "False"]
    if pendientes.empty:
        st.info("Todos tus pagos están al día 🎉")
    else:
        for idx, row in pendientes.iterrows():
            if st.button(f"Marcar '{row['categoria']}' como pagado ✅", key=f"pay_{idx}"):
                df_pres.loc[idx, "pagado"] = "True"
                save_presupuesto(df_pres)
                st.success(f"Pago de {row['categoria']} marcado como completado.")
                st.rerun()

# ---------- TAB 2: VIAJES ----------
with tab_viajes:
    st.info("Aquí continuará la lógica de registro de viajes (versión anterior).")

# ---------- TAB 3: OTROS ----------
with tab_otras:
    st.write("Opciones adicionales o futuras integraciones aquí.")

# ---------- LOGOUT ----------
if st.sidebar.button(f"🔒 Cerrar sesión ({alias})"):
    st.session_state["user"] = None
    st.rerun()