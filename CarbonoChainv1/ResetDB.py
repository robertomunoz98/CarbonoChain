import requests
import json
import os
import shutil

COUCHDB_URL = "http://127.0.0.1:5984"
USERNAME = "admin"
PASSWORD = "admin"

CLAVES_DIR = os.path.expanduser("~/.carbonochain_claves")

print("\n Eliminando todas las bases de datos de CouchDB...")
# Obtener la lista de bases de datos
response = requests.get(f"{COUCHDB_URL}/_all_dbs", auth=(USERNAME, PASSWORD))

if response.status_code == 200:
    dbs = json.loads(response.text)
    for db in dbs:
        delete_response = requests.delete(f"{COUCHDB_URL}/{db}", auth=(USERNAME, PASSWORD))
        if delete_response.status_code == 200:
            print(f" Base de datos '{db}' eliminada.")
        else:
            print(f" Error al eliminar '{db}': {delete_response.text}")
else:
    print(" Error al obtener la lista de bases de datos.")

print("\n  Eliminando claves privadas por canal...")

if os.path.exists(CLAVES_DIR):
    try:
        shutil.rmtree(CLAVES_DIR)
        print(f"Directorio de claves '{CLAVES_DIR}' eliminado correctamente.")
    except Exception as e:
        print(f" Error al eliminar claves: {e}")
else:
    print(f"ℹ No existe el directorio de claves: {CLAVES_DIR}")

print("\n Reset completado.")
