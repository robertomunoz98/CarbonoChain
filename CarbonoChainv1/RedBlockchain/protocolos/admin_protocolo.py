import requests
from flask import jsonify, make_response
from colorama import Fore, Style

class ProtocolManager:
    def __init__(self, canal, nodo):
        self.canal = canal
        self.nodo = nodo
        self.nombreCanal = canal.nombreCanal.lower()

    def validar_protocolo(self, transaccion, protocolo, id_nodo_origen, solicitud, mensaje, mensaje_firmado, datos_publicos=None, datos_privados=None, palabra1=None, palabra2=None):
        if protocolo == "raft":
            lider = self.canal.protocolo.get_lider()
            if self.nodo.obtener_id_nodo_local(self.nombreCanal) != lider:
                try:
                    print(f" Nodo {id_nodo_origen} enviando solicitud de registro al líder {lider}|{self.canal.protocolo.get_lider_ip(lider)}...")
                    response = requests.post(f"http://{self.canal.protocolo.get_lider_ip(lider)}/{solicitud}", json={"datos": datos_publicos, "firma": mensaje_firmado, "id_nodo_emisor": id_nodo_origen})
                    data = response.json()
                    if response.status_code == 200:
                        print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  {data['message']}" + Style.RESET_ALL)
                        return False, make_response(jsonify({"message": f"{mensaje}"}), 200)
                    else:
                        print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  {data['message']}" + Style.RESET_ALL)
                        return False, make_response(jsonify({"message": " Fallo al enviar la transacción al validador."}), 403)
                except requests.ConnectionError:
                    return False, make_response(jsonify({"message": " No se pudo conectar con el líder."}), 503)

        #  Primero agrega la transacción al mempool (temporal)
        try:
            import json
            json.dumps(transaccion, sort_keys=True)
        except TypeError as e:
            print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  Error al serializar la transacción: {e}")
            print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  Transacción problemática: {transaccion}")
            return False, make_response(jsonify({"message": " Error al serializar la transacción."}), 400)

        self.canal.blockchain.agregar_transaccion(transaccion)
        # Para RAFT (si es el líder) o POA (si es autoridad actual y puede crear bloque)
        puede_crear = True
        if protocolo == "poa":
            dir_validador_actual, alias, id = self.canal.protocolo.get_validador_actual_info()
            if self.nodo.obtener_id_nodo_local(self.nombreCanal) != id:
                print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  Enviando transacción al validador actual: '{alias}' ({id})")
                try:
                    response = requests.post(f"http://{dir_validador_actual}/{solicitud}", json={"datos": datos_publicos, "firma": mensaje_firmado, "id_nodo_emisor": id_nodo_origen})
                    data = response.json()
                    if response.status_code == 200:
                        print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  {data['message']}" + Style.RESET_ALL)
                        return False, make_response(jsonify({"message": f"{mensaje}"}), 200)
                    else:
                        print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  {data['message']}" + Style.RESET_ALL)
                        return False, make_response(jsonify({"message": " Fallo al enviar la transacción al validador."}), 403)
                except requests.RequestException:
                    return False, make_response(jsonify({"message": " No se pudo contactar al validador."}), 503)
            puede_crear = self.canal.protocolo.puede_crear_bloque(self.canal.blockchain.transactions)

        if protocolo == "raft":
            self.canal.blockchain.crear_bloque()
            return True, make_response(jsonify({"message": " Bloque creado exitosamente."}), 200)
        if not puede_crear:
            print(f"{self.estilo(Fore.MAGENTA, 'protocolmanager')}:  No tienes permiso para crear el bloque.")
            return False, make_response(jsonify({"message": " No tienes permisos para crear un bloque."}), 403)
        return True, make_response(jsonify({"message": " El bloque se puede crear."}), 200)

    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"