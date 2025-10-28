import os
import pandas as pd

def calculate_bonuses(viajes):
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

def save_daily_data(fecha, df, extras, gastos, combustible, km, bono, balance):
    os.makedirs("data", exist_ok=True)
    resumen = {
        "Fecha": [fecha],
        "Viajes": [len(df)],
        "Ganancia total": [df["Ganancia"].sum()],
        "Propinas": [df["Propina"].sum()],
        "Extras": [extras],
        "Gastos": [gastos],
        "Combustible": [combustible],
        "Kilometraje": [km],
        "Bono": [bono],
        "Balance final": [balance]
    }
    resumen_df = pd.DataFrame(resumen)
    resumen_df.to_csv("data/resumen.csv", mode="a", header=not os.path.exists("data/resumen.csv"), index=False)