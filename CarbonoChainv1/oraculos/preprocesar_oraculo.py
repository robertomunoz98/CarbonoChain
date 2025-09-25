# preprocesar_oraculo.py
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def preprocesar_oraculo(sheet_id, hoja_entrada, hoja_salida, credenciales_json):
    # Autenticación con Google Sheets
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credenciales_json, scope)
    client = gspread.authorize(creds)

    # Descargar hoja de entrada como dataframe
    hoja = client.open_by_key(sheet_id).worksheet(hoja_entrada)
    datos = hoja.get_all_values()
    columnas = datos[17]  # fila 18 (header=17 en Excel)
    df = pd.DataFrame(datos[18:], columns=columnas)

    # Limpiar y filtrar
    df["Available credits"] = pd.to_numeric(df["Available credits"], errors="coerce").fillna(0)
    df_limpio = df[(df["Available credits"] > 0) & (df["Buffer"].str.upper() != "YES")]

    df_oraculo = df_limpio[["Serial number", "Project ID", "Project developer", "Available credits"]].copy()
    df_oraculo.columns = ["serial", "proyecto_id", "desarrollador", "cantidad_total"]
    df_oraculo["estado"] = "disponible"

    # Reemplazar hoja de salida con los datos procesados
    hoja_salida_ref = client.open_by_key(sheet_id).worksheet(hoja_salida)
    hoja_salida_ref.clear()
    hoja_salida_ref.update([df_oraculo.columns.values.tolist()] + df_oraculo.values.tolist())
    print(f"Datos procesados y cargados en hoja '{hoja_salida}' del documento.")

if __name__ == "__main__":
    # Configura según tu entorno
    SHEET_ID = "TU_SHEET_ID"
    HOJA_ENTRADA = "RawData"  # nombre de la hoja con los datos originales
    HOJA_SALIDA = "bonos_certificados"
    CREDENCIALES_JSON = "/ruta/a/ecoregistry_key.json"

    preprocesar_oraculo(SHEET_ID, HOJA_ENTRADA, HOJA_SALIDA, CREDENCIALES_JSON)
