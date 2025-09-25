import base64
from flask import json, jsonify, make_response
from Data.database import Database
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
import os

CLAVES_DIR = os.path.expanduser("~/.carbonochain_claves")

class Nodo:
    def __init__(self, my_address):
        self.my_address = my_address
    
    def my_ip(self, nombre_canal):
        db = Database(db_name=f"{nombre_canal}_nodos")  # Conexión a la DB
        id_nodo = self.obtener_id_nodo_local(nombre_canal)  # ID del nodo local

        nodo_encontrado = False  # Para saber si el nodo fue hallado en la DB
        nodos = db.get_all_docs()

        for nodo in nodos:
            if nodo["_id"] == id_nodo:
                nodo_encontrado = True
                if nodo.get("direccion") != self.my_address:
                    nodo["direccion"] = self.my_address
                    db.save_doc(nodo)  # ← importante guardar el cambio
                    print(f" Dirección actualizada a {self.my_address}")
                break  # No hace falta seguir iterando

        if not nodo_encontrado:
            print(" El nodo no existe en la base de datos")

    def guardar_id_nodo_local(self, canal_nombre, id_nodo):
        db = Database(db_name="identidad_local")
        doc = db.get_doc("identidad_local") or {"_id": "identidad_local", "canales": {}}
        doc["canales"][canal_nombre.lower()] = id_nodo
        db.save_doc(doc)

    def obtener_id_nodo_local(self, canal_nombre):
        db = Database(db_name="identidad_local")
        doc = db.get_doc("identidad_local")
        if doc and canal_nombre in doc.get("canales", {}):
            return doc["canales"][canal_nombre]
        print(f" No se encontró el ID del nodo para el canal '{canal_nombre}'")
        return None

    def get_address(self):
            """Retorna la dirección del nodo."""
            return self.my_address 

    def obtener_alias_nodo(self, canal_nombre):
        """Busca el alias del nodo en la base de datos de nodos del canal, usando la dirección del nodo."""
        db_nodos = Database(db_name=f"{canal_nombre.lower()}_nodos")
        nodos = db_nodos.get_all_docs()

        for nodo in nodos:
            if nodo.get("direccion") == self.my_address:
                return nodo.get("alias", "Sin alias")  # Devuelve alias o valor por defecto

        print(f" No se encontró alias para el nodo {self.my_address} en el canal '{canal_nombre}'.")
        return None
    
    def obtener_ip_cualquier_nodo(self, canal_nombre, id):
        """Busca la ip de un nodo con el en la base de datos de nodos del canal, usando la dirección del nodo."""
        db_nodos = Database(db_name=f"{canal_nombre.lower()}_nodos")
        nodos = db_nodos.get_all_docs()

        for nodo in nodos:
            if nodo.get("_id") == id:
                return nodo.get("direccion", "Sin alias")  # Devuelve la dirección IP

        print(f" No se encontró la ip para el nodo id {id} en el canal '{canal_nombre}'.")
        return None

    def get_id(self, canalNombre):
        """Devuelve el ID del nodo almacenado en la instancia."""
        id_nodo = self.obtener_id_nodo_local(canalNombre)
        return id_nodo

    def cargar_clave_privada(self, canal_nombre):
        """Carga la clave privada desde el archivo asociado al canal."""
        clave_privada_path = os.path.join(CLAVES_DIR, f"{canal_nombre}_privada.pem")

        if not os.path.exists(clave_privada_path):
            print(f" No se encontró clave privada para canal '{canal_nombre}'. Genera una con 'generar_y_guardar_claves()'.")
            return None

        with open(clave_privada_path, "rb") as f:
            clave_serializada = f.read()
            clave = serialization.load_pem_private_key(
                clave_serializada,
                password=None,
                backend=default_backend()
            )
            return clave

    def firmar_mensaje(self, nombreCanal, mensaje: bytes) -> bytes:
        """Firma un mensaje con la clave privada del nodo."""
        clave = self.cargar_clave_privada(nombreCanal)
        if clave is None:
            raise Exception(" No hay clave privada disponible para firmar")

        firma = clave.sign(mensaje, ec.ECDSA(hashes.SHA256()))
        return firma

    def verificar_firma(self, mensaje: bytes, firma: bytes, clave_publica_bytes: bytes) -> bool:
        """Verifica una firma dada una clave pública en bytes."""
        clave_publica = serialization.load_pem_public_key(clave_publica_bytes, backend=default_backend())
        try:
            clave_publica.verify(firma, mensaje, ec.ECDSA(hashes.SHA256()))
            return True
        except InvalidSignature:
            return False

    def obtener_clave_publica(self) -> str:
        """Devuelve la clave pública en formato PEM."""
        clave = self.cargar_clave_privada()
        if clave is None:
            raise Exception(" No hay clave privada disponible para extraer la pública")

        clave_publica = clave.public_key()
        clave_pem = clave_publica.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return clave_pem.decode()
    
    CLAVES_DIR = os.path.expanduser("~/.carbonochain_claves")

    def generar_y_guardar_claves(self, canal_nombre):
        os.makedirs(CLAVES_DIR, exist_ok=True)
        clave_privada_path = os.path.join(CLAVES_DIR, f"{canal_nombre}_privada.pem")

        db_nodos = Database(db_name=f"{canal_nombre.lower()}_nodos")
        id_nodo = self.obtener_id_nodo_local(canal_nombre)

        # Si ya existe la clave, no la regeneres
        if not os.path.exists(clave_privada_path):
            clave_privada = ec.generate_private_key(ec.SECP256R1(), default_backend())
            with open(clave_privada_path, "wb") as f:
                f.write(clave_privada.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            print(f" Clave privada generada para canal '{canal_nombre}'.")

        # Cargar la clave privada
        with open(clave_privada_path, "rb") as f:
            clave_privada = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )

        # Clave pública
        clave_publica = clave_privada.public_key()
        clave_publica_pem = clave_publica.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

        # Guardar en DB
        nodo_doc = db_nodos.get_doc(id_nodo)
        if nodo_doc:
            nodo_doc["clave_publica"] = clave_publica_pem
            db_nodos.save_doc(nodo_doc)
            print(f" Clave pública guardada en nodo '{id_nodo}' del canal '{canal_nombre}'.")
        else:
            print(f"No se encontró el nodo '{id_nodo}' para guardar la clave pública.")

        return clave_publica_pem

    def verificar_datos_propagados(self, firma, id, nombre_canal, canal_data_json, doc):
        db_nodos = Database(db_name=f"{nombre_canal}_nodos")
        nodo_emisor = next((n for n in db_nodos.get_all_docs() if n.get("_id") == id), None)

        if not nodo_emisor or "clave_publica" not in nodo_emisor:
            print(f" Nodo desconocido o sin clave pública.")
            return make_response(jsonify({"message": " Nodo desconocido o sin clave pública."}), 400)
        
        clave_publica_pem = nodo_emisor["clave_publica"].encode("utf-8")
        mensaje = json.dumps(canal_data_json, sort_keys=True).encode("utf-8")
        
        if not self.verificar_firma(mensaje, firma, clave_publica_pem):
            print(f" Firma inválida detectada en nodo receptor al recibir {doc}.")
            return make_response(jsonify({"message": " Firma inválida detectada en nodo receptor al recibir {doc}."}), 400)
        else:
            print(f" Firma valida al recibir {doc}. Se sincronizara la información.")
        #  Si pasa la verificación, guardas canal_data
        return make_response(jsonify({"message": " Canal sincronizado con firma válida."}), 200)
    
    def firma_cod(self, informacion, nombreCanal):
        mensaje = json.dumps(informacion, sort_keys=True).encode("utf-8")
        firma_bytes = self.firmar_mensaje(nombreCanal, mensaje)

        #  Codificar la firma en base64 para enviarla por JSON
        firma = base64.b64encode(firma_bytes).decode("utf-8")
        return firma