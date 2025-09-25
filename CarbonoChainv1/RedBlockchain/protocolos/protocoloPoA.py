import threading
import time

from colorama import Fore, Style
from flask import jsonify, make_response
import requests
from Data.database import Database

class ProtocoloPoA:
    def __init__(self, nodo, canal, nombre_canal):
        self.nodo = nodo
        self.canal = canal
        self.nombre_canal = nombre_canal.lower()
        self.db_nodos = None  # Se inicializa luego en obtener_validadores()
        self.validadores = []
        self.indice_validador_actual = 0
        self.ultimo_bloque_timestamp = time.time()
        self.tiempo_minimo = 10  # segundos
        self.transacciones_maximas = 10
        self.nombre_protocolo = "poa"
        self.db_nodos = Database(db_name=f"{self.nombre_canal}_nodos")
        
    def iniciar_poa(self):
        self.obtener_validadores()
        # Mostrar autoridades conocidas en este canal
        if self.validadores:
            print(f"{self.estilo(Fore.CYAN, self.nombre_canal)}:  Autoridades registradas en el canal '{self.nombre_canal}':")
            _, _, validador_actual = self.get_validador_actual_info()
            print(f"           Alias: |     Direccion:     |      ID")
            for v in self.validadores:
                alias = v["alias"]
                id = v["_id"]
                direccion = v["direccion"]
                marcador = "  (Validador actual)" if id == validador_actual else ""
                print(f"       🅰  '{alias}' | '{direccion}' | ' {id} '{marcador}")
        else: print(f"{self.estilo(Fore.RED, self.nombre_canal)}: No hay autoridades registradas en este canal todavía.")

        # Mostrar si este nodo es autoridad
        if self.es_autoridad_activa():
            print(f"{self.estilo(Fore.CYAN, self.nombre_canal)}:   Este nodo está registrado como: 🅰  AUTORIDAD y puede ✅ crear bloques.")
            threading.Thread(target=self.ejecutar_ciclo_rotativo, daemon=True).start()
        else: print(f"{self.estilo(Fore.RED, self.nombre_canal)}:  Este nodo NO es autoridad. Solo puede participar como observador.")

    def obtener_validadores(self):
        db_nodos = Database(db_name=f"{self.nombre_canal}_nodos")
        nodos = db_nodos.get_all_docs()
        # Solo incluir nodos que sean autoridades
        self.validadores = sorted([{
            "alias": nodo.get("alias", "sin_alias"), "_id": nodo.get("_id"), "direccion": nodo["direccion"]}
            for nodo in nodos
            if nodo.get('estado') == 'activo' and (nodo.get('rol') == 'autoridad' or nodo.get('es_autoridad') == True)
        ], key=lambda x: x["alias"])
    
    def get_validador_actual_info(self):
        if not self.validadores:
            return None, None
        validador = self.validadores[self.indice_validador_actual]
        return validador["direccion"], validador["alias"], validador["_id"]

    def ejecutar_ciclo_rotativo(self):
        print(f"{self.estilo(Fore.MAGENTA, self.nombre_canal)}:  Iniciando ciclo rotativo de autoridades...")

        self.ultimo_bloque_timestamp = time.time()
        
        direccion, alias, id = self.get_validador_actual_info()
        print(f"{self.estilo(Fore.MAGENTA, self.nombre_canal)}:  El Validador con el turno es: '{self.estilo(Fore.CYAN, alias)}' Id: {id} | ({direccion})")

        while True:
            time.sleep(1)
            transacciones_pendientes = self.canal.blockchain.transactions

            if self.puede_crear_bloque(transacciones_pendientes):
                if transacciones_pendientes:
                    print(f"{self.estilo(Fore.GREEN, self.nombre_canal)}:  Condiciones para crear bloque cumplidas.")

                    self.canal.blockchain.crear_bloque()
                    self.ultimo_bloque_timestamp = time.time()

                    self.siguiente_validador()
                else:
                    print(f"{self.estilo(Fore.YELLOW, self.nombre_canal)}:  Se cumplió el tiempo, pero no hay transacciones para crear un bloque.")

    def siguiente_validador(self):
        if not self.validadores:
            return

        self.indice_validador_actual = (self.indice_validador_actual + 1) % len(self.validadores)
        direccion, alias, id = self.get_validador_actual_info()
        print(f"{self.estilo(Fore.MAGENTA, self.nombre_canal)}:  Turno cambiado al nodo '{self.estilo(Fore.CYAN, alias)}' Id: {id} | ({direccion})")

        #  Propagar el nuevo turno
        self.propagar_turno(direccion, alias, id)

    def propagar_turno(self, direccion_validador, alias_validador, id_validador):
        nodos_canal = self.canal.listar_nodos_canal(self.nombre_canal)
        for nodo in nodos_canal:
            if nodo["_id"] != self.nodo.obtener_id_nodo_local(self.nombre_canal):
                try:
                    response = requests.post(f"http://{nodo['direccion']}/sync_turno", json={
                        "direccion": direccion_validador,
                        "_id": id_validador,
                        "alias": alias_validador,
                        "nombre_canal": self.nombre_canal
                    })
                    data = response.json()
                    if response.status_code == 200:
                        print(f"{self.estilo(Fore.MAGENTA, self.nombre_canal)}:  {data['message']}")
                        direccion, alias, id = self.get_validador_actual_info()
                        print(f"{self.estilo(Fore.MAGENTA, self.nombre_canal)}:  El Validador con el turno es: '{self.estilo(Fore.CYAN, alias)}' Id: {id} | ({direccion})")
                except requests.RequestException:
                    print(f" No se pudo propagar el turno a {nodo['direccion']}")

    def actualizar_turno(self, data):
        nuevo_turno = data.get("direccion")
        nuevo_alias = data.get("alias")
        for idx, validador in enumerate(self.validadores):
            if validador["direccion"] == nuevo_turno:
                self.indice_validador_actual = idx
                print(f"{self.estilo(Fore.MAGENTA, self.nombre_canal)}: 🔁 Turno sincronizado. Ahora es: '{self.estilo(Fore.MAGENTA, nuevo_alias)}' ({nuevo_turno}).")
                print(f"{self.estilo(Fore.MAGENTA, self.nombre_canal)}: 🎯 El Validador con el turno es: '{self.estilo(Fore.CYAN,nuevo_alias)}' ({nuevo_turno})")
                return
        print(f"{self.estilo(Fore.YELLOW, self.nombre_canal)}:  No se pudo sincronizar el turno: el nodo {nuevo_turno} no se encuentra entre los validadores.")
    
    def puede_crear_bloque(self, transacciones_pendientes):
        ahora = time.time()
        _, _, id = self.get_validador_actual_info()
        if self.nodo.obtener_id_nodo_local(self.nombre_canal) != id: return False  #  No es el turno de este nodo

        tiempo_pasado = ahora - self.ultimo_bloque_timestamp

        #  Esperar al menos una transacción
        if len(transacciones_pendientes) < 1: return False

        #  Crear el bloque si ya pasó el tiempo o se alcanzó el máximo
        if tiempo_pasado >= self.tiempo_minimo or len(transacciones_pendientes) >= self.transacciones_maximas:
            return True

        return False

    def actualizar_bloque_creado(self):
        self.ultimo_bloque_timestamp = time.time()
        self.indice_validador_actual = (self.indice_validador_actual + 1) % len(self.validadores)
    
    def es_autoridad_activa(self):
        for validador in self.validadores:
            if validador["direccion"] == self.nodo.my_address:
                return True
        return False

    def nueva_autoridad(self, datos, propagar=True):
        nombre_canal = datos.get("nombreCanal")
        id = datos.get("_id")

        if not nombre_canal or not id:
            return make_response(jsonify({"message": "Datos incompletos"}), 400)

        db = Database(db_name=f"{nombre_canal.lower()}_nodos")
        nodos = db.get_all_docs()
        nodoAutoridad = self.nodo.obtener_alias_nodo(nombre_canal)

        for nodo in nodos:
            if nodo.get("_id") == id:
                nodo["rol"] = "autoridad"
                nodo["es_autoridad"] = True
                db.save_doc(nodo)
                
                alias = nodo["alias"]
                ip_nueva = nodo["direccion"]
                if not propagar:
                    print(f"{self.estilo(Fore.CYAN, 'Protocolo PoA:')}:  Nodo {alias} actualizado localmente como autoridad")

                    if self.nodo.my_address == ip_nueva:
                        print(f"{self.estilo(Fore.CYAN, self.nombre_canal)}:  ¡Este nodo ha sido asignado como NUEVA AUTORIDAD en el canal!")
                        print(f"{self.estilo(Fore.CYAN, self.nombre_canal)}:  El nodo '{self.estilo(Fore.MAGENTA, nodoAutoridad)}' te convirtió 🅰  {self.estilo(Fore.MAGENTA, 'AUTORIDAD')}")
                    return make_response(jsonify({"message": "Nodo actualizado localmente"}), 200)
                # Solo si debe propagar
                transaccion = {
                    "tipo": "nueva_autoridad",
                    "alias": alias,
                    "direccion_nueva_autoridad": ip_nueva,
                    "mensaje": f"Nodo '{alias}' establecido nueva autoridad por {nodoAutoridad}"
                }

                self.canal.blockchain.agregar_transaccion(transaccion)
                transacciones_pendientes = self.canal.blockchain.transactions
                if self.puede_crear_bloque(transacciones_pendientes): self.canal.blockchain.crear_bloque()
                else: return make_response(jsonify({"message": f"No tienes permiso para crear un bloque"}), 400)

                self.canal.actualizar_nodo(nombre_canal, nodoAutoridad, id)
                return make_response(jsonify({"message": f" Nodo {alias} ahora es AUTORIDAD en el canal {nombre_canal}"}), 200)

        return make_response(jsonify({"message": "Nodo no encontrado"}), 404)

    #============================== Estilo para imprimir =========================
    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"