import base64
from datetime import datetime
import uuid
import bcrypt
from flask import json
import requests
from Data.database import Database
from .bloques import Blockchain
from .protocolos.protocoloRAFT import ProtocoloRaft
from .protocolos.protocoloPoA import ProtocoloPoA

class Canal:
    def __init__(self, nodo, nombreCanal, protocolo):
        self.db_canales = Database(db_name="canales")
        self.nodo = nodo
        self.nombreCanal = nombreCanal.lower()
        self.clave_temporal = None
        self.nombre_protocolo = protocolo

        if protocolo == "raft":
            self.protocolo = ProtocoloRaft(self.nodo, self, self.nombreCanal)
        elif protocolo == "poa":
            self.protocolo = ProtocoloPoA(self.nodo, self, self.nombreCanal)
        else:
            raise ValueError(" Protocolo no soportado.")
        self.blockchain = Blockchain(self.nodo, self.nombreCanal, self)

    def generar_id_unico(self):
        """ Genera un ID único y verifica que no exista en la BD. """
        while True:
            nuevo_id = uuid.uuid4().hex[:12]  # ID alfanumérico único
            if not self.db_canales.get_doc(nuevo_id):
                return nuevo_id

    def crear_canal(self, nombre, nodo_address, clave, protocolo):
        idCanal = self.generar_id_unico()
        nodo_id = self.generar_id_unico_nodo()
        alias = self.generar_alias_automatico(nombre)
        #  Encriptar la clave antes de guardarla
        clave_hash = bcrypt.hashpw(clave.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        canal_data = {
            "_id": idCanal,
            "nombre": nombre,
            "fecha_creacion": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "id_nodo_creador": nodo_id,
            "protocolo": protocolo,
            "estado": "activo",
            "clave": clave_hash 
        }

        self.db_canales.save_doc(canal_data)

        #  Registrar la creación del canal en la blockchain
        transaccion = {
            "tipo": "creacion_canal",
            "id_canal": idCanal,
            "nombre": nombre,
            "alias": alias,
            "protocolo": protocolo,
            "nodo_creador_ip": self.nodo.my_address,
            "mensaje": f"Canal '{nombre}' creado por {self.nodo.my_address}"
        }
        self.nodo.guardar_id_nodo_local(nombre, nodo_id)
        self.blockchain.bloque_genesis(nombre.lower())
        self.blockchain.agregar_transaccion(transaccion)
        self.manejar_registro_y_bloque(nodo_address, nombre, nodo_id, alias, desde_validar=False)
        self.nodo.generar_y_guardar_claves(nombre)
        return {"message": f"Canal '{nombre}' creado exitosamente.", "id_canal": idCanal}
    
    def validar_ingreso(self, clave_ingresada, nombreCanal, nodo_address, protocolo):
        canal_data = self.buscar_canal_por_nombre(nombreCanal)

        if not canal_data: return {"error": "El canal no existe."}

        clave_hash = canal_data.get("clave")

        #  Comparar la clave ingresada con la encriptada
        if not bcrypt.checkpw(clave_ingresada.encode('utf-8'), clave_hash.encode('utf-8')):
            return {"error": "Clave incorrecta."}
        
        self.propagar_info_canal(nodo_address, nombreCanal)
        
        nodo_id = self.generar_id_unico_nodo()
        return {"message": f" Credenciales del canal {self.nombreCanal} validas", "_id": nodo_id, "protocolo": protocolo}

    def sync_nuevo_nodo(self, nodo_address, nodo_id, nombreCanal, protocolo, clave_publica):
        """Valida si un nodo puede unirse al canal verificando la clave encriptada."""
        canal_data = self.buscar_canal_por_nombre(nombreCanal)

        if not canal_data: return {"error": "El canal no existe."}
        
        alias = self.generar_alias_automatico(nombreCanal)

        #  Crear una transacción en la blockchain del canal
        transaccion = {
            "tipo": "union_nodo",
            "nodo": nodo_address,
            "alias": alias,
            "mensaje": f"El nodo {nodo_address} se unió al canal {nombreCanal}"
        }
        #  Propagar la actualización del nodo a los demás nodos del canal
        self.blockchain.agregar_transaccion(transaccion)
        self.manejar_registro_y_bloque(nodo_address, nombreCanal, nodo_id, alias, clave_publica, desde_validar=True)
        self.propagar_nuevo_nodo(nodo_address, nombreCanal)

        protocolo = canal_data.get("protocolo", "raft").lower()
        return {"message": f" Nodo {nodo_address} unido al canal {self.nombreCanal}", "protocolo": protocolo, "_id": nodo_id}

    def propagar_info_canal(self, nodo_address, nombreCanal):
        """Propaga la información del canal al nuevo nodo."""
        try:
            #  Propagar la información del canal
            canal_data = self.buscar_canal_por_nombre(nombreCanal)
            requests.post(f"http://{nodo_address}/sync_canal", json={"canal_data": canal_data})

            print(f" Información del canal sincronizada con el nodo: {nodo_address}")
        except requests.RequestException:
            print(f" No se pudo propagar la información del canal con {nodo_address}")

    def propagar_a_nodos(self, nodo_address, nombreCanal, nuevo_nodo, id):
        """Propaga la unión de un nuevo nodo a todos los nodos del canal."""
        nodos_canal = self.listar_nodos_canal(nombreCanal)
        id_nodo_local = self.nodo.obtener_id_nodo_local(nombreCanal)
        for nodo in nodos_canal:
            if nodo["_id"] != id_nodo_local and nodo["_id"] != id:
                try:
                    mensaje = json.dumps(nuevo_nodo, sort_keys=True).encode("utf-8")
                    firma_bytes = self.nodo.firmar_mensaje(nombreCanal, mensaje)

                    #  Codificar la firma en base64 para enviarla por JSON
                    firma = base64.b64encode(firma_bytes).decode("utf-8")
                    requests.post(f"http://{nodo['direccion']}/sync_nodos", json={"nodos": [nuevo_nodo], "firma": firma,"nombreCanal": nombreCanal, "id_nodo_emisor": self.nodo.obtener_id_nodo_local(nombreCanal)})

                    print(f" Nodo {nodo_address} propagado y sincronizado")
                except requests.RequestException:
                    print(f" No se pudo sincronizar con {nodo['direccion']}")

    def propagar_nuevo_nodo(self, nodo_address, nombreCanal):
        """Propaga las bases de datos del canal al nuevo nodo."""
        nodos_canal = self.listar_nodos_canal(nombreCanal)
        usuarios_canal = self.obtener_usuarios_canal(nombreCanal)
        bonos = self.obtener_bonos()
        id_nodo_emisor = self.nodo.obtener_id_nodo_local(nombreCanal)

        try:
            #  Enviar la lista de nodos actualizada
            requests.post(f"http://{nodo_address}/sync_nodos", json={"nodos": nodos_canal, "nombreCanal": nombreCanal})

            #  Propagar la blockchain completa
            blockchain_data = self.blockchain.get_chain_from_db()
            firma_block = self.nodo.firma_cod(blockchain_data, nombreCanal)
            requests.post(f"http://{nodo_address}/sync_chain", json={"chain": blockchain_data, "nombreCanal": nombreCanal, "protocolo": self.protocolo.nombre_protocolo, "firma":firma_block, "id_nodo_emisor": id_nodo_emisor})
            
            #  Propagar la información de usuarios
            firma_usuarios = self.nodo.firma_cod(usuarios_canal, nombreCanal)
            requests.post(f"http://{nodo_address}/sync_users", json={"usuarios": usuarios_canal, "nombreCanal": nombreCanal, "firma":firma_usuarios, "id_nodo_emisor": id_nodo_emisor})
            
            #  Propagar los bonos
            firma_bonos = self.nodo.firma_cod(bonos, nombreCanal)
            requests.post(f"http://{nodo_address}/sync_bonos", json={"bonos": bonos, "nombreCanal": nombreCanal, "protocolo": self.protocolo.nombre_protocolo, "firma":firma_bonos, "id_nodo_emisor": id_nodo_emisor})

            print(f" Nodo {nodo_address} propagado y sincronizado")
        except requests.RequestException:
            print(f" No se pudo sincronizar con {nodo_address}")
        
    def actualizar_nodo(self, nombreCanal, nodoAutoridad, idNuevaAutoridad):
        """Actualiza todos los nodos del canal."""
        nodos_canal = self.listar_nodos_canal(nombreCanal)

        for nodo in nodos_canal:
            try:
                #  Enviar la lista de nodos actualizada
                requests.post(f"http://{nodo['direccion']}//sync_nodo_autoridad", json={"_id": idNuevaAutoridad, "nombreCanal": nombreCanal, "nodoAutoridad": nodoAutoridad, "propagar": False})
            except requests.RequestException:
                print(f" No se pudo sincronizar con {nodo['direccion']}")

    #__/__/__/__/__/__/__/__/__/__/ REGISTROS __/__/__/__/__/__/__/__/__/__/
    def registrar_nodo_en_raft(self, nodo_address, canal_nombre, nodo_id, alias, clave_publica,):
        db = Database(db_name=f"{canal_nombre.lower()}_nodos")
        nodo_data = {
            "_id": nodo_id,
            "alias": alias,
            "direccion": nodo_address,
            "fecha_union": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "estado": "activo",
            "clave_publica": clave_publica
        }
        db.save_doc(nodo_data)
        self.propagar_a_nodos(nodo_address, canal_nombre, nodo_data, nodo_id)
        print(f" Nodo {nodo_address} registrado en el canal {canal_nombre} con ID {nodo_id}")

    def registrar_nodo_en_poa(self, nodo_address, canal_nombre, nodo_id, alias, clave_publica, es_autoridad=True):
        db = Database(db_name=f"{canal_nombre.lower()}_nodos")
        nodo_data = {
            "_id": nodo_id,
            "alias": alias,
            "direccion": nodo_address,
            "fecha_union": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "estado": "activo",
            "rol": "autoridad" if es_autoridad else "observador",
            "es_autoridad": es_autoridad,
            "clave_publica": clave_publica
        }
        db.save_doc(nodo_data)
        self.propagar_a_nodos(nodo_address, canal_nombre, nodo_data, nodo_id)
        print(f" Nodo {nodo_address} registrado en el canal {canal_nombre} con ID {nodo_id}")

    def manejar_registro_y_bloque(self, nodo_address, nombre_canal, nodo_id, alias, clave_publica=None, desde_validar=False):
        protocolo_nombre = getattr(self.protocolo, "nombre_protocolo", "")

        if protocolo_nombre == "raft":
            self.registrar_nodo_en_raft(nodo_address, nombre_canal, nodo_id, alias, clave_publica)
            if self.protocolo.get_lider() is None:
                self.protocolo.lider = self.nodo.obtener_id_nodo_local(nombre_canal)
                print(f" {nodo_address} | Id: {self.nodo.obtener_id_nodo_local(nombre_canal)} se proclama líder del canal.")
            if self.protocolo.puede_crear_bloque(): self.blockchain.crear_bloque()
            else: print(" No tienes permisos para crear un bloque.")

        elif protocolo_nombre == "poa":
            transacciones_pendientes = self.blockchain.transactions
            es_autoridad = not desde_validar  # True si estamos creando el canal
            if not desde_validar or self.protocolo.puede_crear_bloque(transacciones_pendientes):
                self.blockchain.crear_bloque()
                self.registrar_nodo_en_poa(nodo_address, nombre_canal, nodo_id, alias, clave_publica, es_autoridad)
            else: print(" No tienes permisos para crear un bloque.")
            

    def agregar_nodos_al_canal(self, lista_nodos, canal_nombre):
        """Agrega la lista de nodos recibida al canal sin modificar sus valores."""
        db_nodos_canal = Database(db_name=f"{canal_nombre.lower()}_nodos")
            
        for nodo in lista_nodos:
            nodo["_id"] = nodo.pop("_id", None)  #  Asegurar que `_id` se mantenga correctamente
            if not nodo["_id"]:
                print(f" Nodo sin ID válido: {nodo}")  # Depuración si falta `_id`
                continue  # Si no tiene un ID, no lo guarda

            print(f" Guardando nodo: {nodo}")  #  Verifica la estructura final del nodo
            db_nodos_canal.save_doc(nodo)
    
    #__/__/__/__/__/__/__/__/__/__/ BUSQUEDAS Y LISTAS __/__/__/__/__/__/__/__/__/__/
    def buscar_canal_por_nombre(self, nombre):
        """ Busca si un canal ya existe con el mismo nombre. """
        canales = self.db_canales.get_all_docs()
        for canal in canales:
            if canal.get("nombre") == nombre:
                return canal  # Devuelve el canal si lo encuentra
        return None
    
    def cargar_canales_del_nodo(self):
        """Recupera los canales en los que está registrado este nodo."""
        canales = self.db_canales.get_all_docs()
        canales_del_nodo = [canal for canal in canales if self.nodo.my_address in canal.get("nodos", [])]

        if canales_del_nodo:
            print(f" Se han recuperado {len(canales_del_nodo)} canal(es) para el nodo {self.nodo.my_address} | Id: {self.nodo.obtener_id_nodo_local(self.nombreCanal)}:")
            for canal in canales_del_nodo: print(f"   - Canal: {canal['nombre']} (ID: {canal['_id']})")
        else: print(" No se encontraron canales registrados para este nodo.")

        return canales_del_nodo

    def obtener_usuarios_canal(self, nombreCanal):
        """Obtiene los usuarios del canal con los datos requeridos."""
        db_usuarios = Database(db_name=f"{nombreCanal.lower()}_usuarios")
        usuarios = db_usuarios.get_all_docs()

        # Filtrar solo la información necesaria
        usuarios_filtrados = [
            {
                "_id": usuario["_id"],
                "nombre": usuario["nombre"],
                "rol": usuario["rol"],
                "saldo": usuario["saldo"],
                "cant_bonos": usuario["cant_bonos"],
                "nodo_creador_id": usuario["nodo_creador_id"],
                "clave_privada": usuario["clave_privada"]
            }
            for usuario in usuarios
        ]
        return usuarios_filtrados
    
    def obtener_bonos(self):
        db_bc = Database(db_name=f"{self.nombreCanal}_bonos")
        bonos = db_bc.get_all_docs()
        return bonos

    def listar_nodos_canal(self, canal_nombre):
        """Lista los nodos registrados en la base de datos del canal específico."""

        db_nodos_canal = Database(db_name=f"{canal_nombre.lower()}_nodos")
        nodos = db_nodos_canal.get_all_docs()
        if self.protocolo.nombre_protocolo == "raft":
            lista_nodos = [{"_id": nodo["_id"], "alias": nodo["alias"], "direccion": nodo["direccion"], "fecha_union": nodo.get("fecha_union"), "estado": nodo.get("estado"), "clave_publica": nodo.get("clave_publica")} for nodo in nodos]
        elif self.protocolo.nombre_protocolo == "poa":
            lista_nodos = [{"_id": nodo["_id"], "alias": nodo["alias"], "direccion": nodo["direccion"], "fecha_union": nodo.get("fecha_union"), "estado": nodo.get("estado"), "rol": nodo.get("rol"), "es_autoridad": nodo.get("es_autoridad"), "clave_publica": nodo.get("clave_publica")} for nodo in nodos]
        if lista_nodos: return lista_nodos
        else: return []
    
    #__/__/__/__/__/__/__/__/__/__/ IDENTIFICADORES __/__/__/__/__/__/__/__/__/__/
    def generar_id_unico_nodo(self):
        """Genera un ID único para un nodo dentro del canal."""
        unique_id = f"{uuid.uuid4().hex[:8]}"
        return unique_id

    def generar_alias_automatico(self, canal_nombre):
        print(f"{canal_nombre.lower()}_nodos")
        db_nodos_canal = Database(db_name=f"{canal_nombre.lower()}_nodos")
        nodos = db_nodos_canal.get_all_docs()
        
        # Buscar los alias existentes tipo nodoX
        numeros = []
        for nodo in nodos:
            alias = nodo.get("alias", "")
            if alias.startswith("nodo"):
                try:
                    numero = int(alias.replace("nodo", ""))
                    numeros.append(numero)
                except ValueError:
                    continue

        # Calcular el siguiente número disponible
        siguiente = max(numeros, default=0) + 1
        return f"nodo{siguiente}"

    def actualizar_clave(self,nombreCanal, nueva_clave):
        """Permite al líder del canal actualizar la clave de acceso."""
        if self.protocolo.get_lider() != self.nodo.my_address:
            return {"error": "Solo el líder puede cambiar la clave del canal."}

        canal_data = self.self.buscar_canal_por_nombre(nombreCanal)

        if not canal_data:
            return {"error": "El canal no existe."}

        canal_data["clave"] = nueva_clave
        clave_hash = bcrypt.hashpw(nueva_clave.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        self.db_canales.save_doc(clave_hash)

        return {"message": " Clave del canal actualizada correctamente."}