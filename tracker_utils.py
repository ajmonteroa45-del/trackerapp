import pandas as pd
import streamlit as st 
import json
from datetime import date 

# --- NOMBRES DE HOJAS DE CÁLCULO (DEBEN COINCIDIR CON TU CONFIGURACIÓN) ---
GSHEET_USERS_TITLE = "TripCounter_Users"  # Se mantiene por si se usa alguna lógica antigua (Aunque la autenticación PIN se eliminó)
GSHEET_TRIPS_TITLE = "TripCounter_Trips"
GSHEET_GASTOS_TITLE = "TripCounter_Gastos"
GSHEET_SUMMARIES_TITLE = "TripCounter_Summaries"

# --- FUNCIÓN 1: LÓGICA DE NEGOCIO ---

def calculate_bonuses(viajes):
    """Calcula el bono basado en el número de viajes realizados."""
    if viajes >= 25:
        return 16 + 12 + 9 + 16
    elif viajes >= 21:
        return 12 + 9 + 16
    elif viajes >= 17:
        return 9 + 16
    elif viajes >= 13:
        return 16
    else:
        return 0

# --- FUNCIÓN 2: CARGAR DATOS DESDE SHEETS ---
@st.cache_data(ttl=3600)
def load_data_from_sheet(sheet_title):
    """Carga un DataFrame desde la Hoja de Cálculo especificada."""
    try:
        # Asume st.connection('gsheets') está configurado en secrets.toml
        conn = st.connection("gsheets", type="experimental_connection") 
        df = conn.read(spreadsheet=sheet_title, usecols=list(range(20)), ttl=5)
        return df.dropna(how='all', axis=1)
    except Exception as e:
        # En el primer despliegue, la hoja puede no existir. Retorna un DF vacío.
        st.warning(f"Error al leer hoja {sheet_title}: {e}. Usando DataFrame vacío.")
        if sheet_title == GSHEET_USERS_TITLE:
            return pd.DataFrame(columns=["alias", "pin_hash"])
        return pd.DataFrame(columns=["alias", "Fecha"]) 


# --- FUNCIÓN 3: GUARDAR RESUMEN (ADAPTADO A SHEETS Y EMAIL) ---

def save_daily_data(user_email, df_trips, extras, gastos, combustible, km, bono, balance):
    """
    Guarda el resumen diario en el Google Sheet de Summaries.
    
    :param user_email: El nuevo identificador único del usuario (tomado de OAuth).
    :param df_trips: DataFrame de los viajes del día.
    """
    
    fecha_actual = date.today().isoformat()
    
    resumen = {
        "alias": user_email, # ¡CRUCIAL! Email de OAuth
        "Fecha": fecha_actual,
        "Viajes": len(df_trips),
        "Ganancia total": df_trips["Ganancia"].sum() if not df_trips.empty else 0,
        "Propinas": df_trips["Propina"].sum() if not df_trips.empty else 0,
        "Extras": extras,
        "Gastos": gastos,
        "Combustible": combustible,
        "Kilometraje": km,
        "Bono": bono,
        "Balance final": balance
    }
    
    df_summaries = load_data_from_sheet(GSHEET_SUMMARIES_TITLE)
    
    # Eliminar cualquier registro anterior del mismo usuario y misma fecha
    df_summaries = df_summaries[~((df_summaries['alias'] == user_email) & (df_summaries['Fecha'] == fecha_actual))]
    
    resumen_df = pd.DataFrame([resumen])
    df_all = pd.concat([df_summaries, resumen_df], ignore_index=True)
    
    try:
        conn = st.connection("gsheets", type="experimental_connection")
        conn.write(df_all, spreadsheet=GSHEET_SUMMARIES_TITLE)
        load_data_from_sheet.clear() 
        return True
    except Exception as e:
        st.error(f"Error al guardar resumen en Google Sheets: {e}")
        return False # <-- Única llamada a return False