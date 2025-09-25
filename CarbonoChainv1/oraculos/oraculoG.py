import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import jsonify, make_response
from decimal import Decimal, getcontext, InvalidOperation
import re

getcontext().prec = 10

class Oraculo:
    def __init__(self):
        self.sheet_id = "1JHnKjl2CE6fhGBE55gJ5xvvsWLIBqwWJQ9qPcfOHwAk"
        self.hoja_entrada = "Issuances Report"
        self.credenciales_json = os.path.join(os.path.dirname(__file__), "credenciales.json")
        self.client = self.conectar()
        self.worksheet = self.client.open_by_key(self.sheet_id).worksheet(self.hoja_entrada)

    def conectar(self):
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.credenciales_json, scope)
        return gspread.authorize(creds)

    def buscar_bono_por_serial(self, serial):
        try:
            datos = self.worksheet.get_all_values()
            columnas = datos[17]  # Fila 18 como encabezado
            df = pd.DataFrame(datos[18:], columns=columnas)

            # Agregamos columna W para estados
            estados = [fila[22] if len(fila) > 22 else "" for fila in datos[18:]]
            df["Estado_oraculo"] = estados

            # Filtrar bonos disponibles
            df["Available credits"] = pd.to_numeric(df["Available credits"], errors="coerce").fillna(0)
            df_filtrado = df[
                (df["Available credits"] > 0) &
                (df["Buffer"].str.upper() != "YES") &
                (~df["Estado_oraculo"].str.startswith("Totalmente vendido")) &
                (~df["Estado_oraculo"].str.startswith("Retirado")) &
                (~df["Estado_oraculo"].str.startswith("Registrado"))
            ]

            resultado = df_filtrado[df_filtrado["Serial number"] == serial]

            if not resultado.empty:
                fila = resultado.iloc[0]
                return {
                    "serial": fila["Serial number"],
                    "proyecto_id": fila["Project ID"],
                    "desarrollador": fila["Project developer"],
                    "pais": fila["Country"],
                    "cantidad_total": fila["Available credits"],
                    "fecha_emision": fila["Issuance date"],
                    "vintage": fila["Vintage"],
                    "estado": fila["Estado_oraculo"] or "sin estado"
                }
            else:
                return make_response(jsonify({
                    "message": f" Bono no disponible o no válido: {serial}"
                }), 403)

        except Exception as e:
            return make_response(jsonify({
                "message": f" Error al consultar el oráculo: {e}"
            }), 503)

    def marcar_bono_registrado(self, serial):
        try:
            datos = self.worksheet.get_all_values()
            for idx, fila in enumerate(datos[17:], start=18):
                if len(fila) < 17:
                    continue
                serial_en_fila = fila[16]
                if serial_en_fila == serial:
                    self.worksheet.update_cell(idx, 23, "Registrado")
                    print("Oráculo:  Estado del bono cambiado a 'Registrado'")
                    return True
            return False
        except Exception as e:
            return make_response(jsonify({
                "message": f" Error al escribir: {e}"
            }), 503)

    def actualizar_estado(self, serial, nuevos_vendidos=Decimal("0")):
        try:
            datos = self.worksheet.get_all_values()
            print(" Iniciando actualización de estado...")

            for idx, fila in enumerate(datos[17:], start=18):
                if len(fila) < 23:
                    continue
                serial_en_fila = fila[16].strip()
                estado_actual = fila[22].strip()

                if serial_en_fila == serial.strip():
                    print(f"Oráculo:  Coincidencia encontrada en la fila {idx}")
                    columnas = datos[17]
                    df = pd.DataFrame(datos[18:], columns=columnas)
                    df["Available credits"] = pd.to_numeric(df["Available credits"], errors="coerce").fillna(0)
                    fila_df = df[df["Serial number"] == serial].iloc[0]
                    total = Decimal(str(fila_df["Available credits"]))
                    vendidos_previos = Decimal("0")

                    if "Parcialmente vendido" in estado_actual:
                        match = re.search(r"Parcialmente vendido\s*\(([\d.]+)/([\d.]+)/([\d.]+)\)", estado_actual)
                        if match:
                            vendidos_previos = Decimal(match.group(1))
                            total_original = Decimal(match.group(3))
                            total = total_original

                    vendidos_actualizados = vendidos_previos + Decimal(nuevos_vendidos)
                    disponibles_actualizados = total - vendidos_actualizados

                    if vendidos_actualizados >= total:
                        nuevo_estado = "Totalmente vendido"
                    else:
                        nuevo_estado = f"Parcialmente vendido ({vendidos_actualizados}/{disponibles_actualizados}/{total})"

                    print(f"Oráculo:  Escribiendo nuevo estado en fila {idx}: {nuevo_estado}")
                    self.worksheet.update_cell(idx, 23, nuevo_estado)
                    return True

            print(" No se encontró el serial en ninguna fila.")
            return False

        except (InvalidOperation, Exception) as e:
            print(f" Error inesperado: {e}")
            return make_response(jsonify({
                "message": f" Error al actualizar estado: {e}"
            }), 503)