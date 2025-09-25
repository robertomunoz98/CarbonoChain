import base64
from decimal import Decimal
import hashlib
import time
from datetime import datetime
from colorama import Fore, Style
from flask import json, jsonify, make_response
from Data.database import Database
import requests

class ContratoBasico:
    def __init__(self, nodo1, canal):
        self.canal = canal
        self.nombreCanal = canal.nombreCanal.lower()
        self.db = Database(db_name=f"{self.nombreCanal}_usuarios")  # Base de datos de usuarios en CouchDB
        self.nodo1 = nodo1

#__/__/__/__/__/__/FUNCIONES PRINCIPALES__/__/__/__/__/__/
    
    def crear_usuario(self, datos):
        id = datos.get("_id")
        creador = datos.get("nodo_creador_id") #lo trae de cliUsers
        if self.db.get_doc(id):
            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  La {id} ya está registrada.")
            return make_response(jsonify({"message": f" La ID {id} ya está registrada."}), 400)

        protocolo = getattr(self.canal.protocolo, "nombre_protocolo", "raft")
        if creador == self.nodo1.obtener_id_nodo_local(self.nombreCanal):
            palabra1, palabra2 = self.generar_palabras()
            clave_privada = f"{creador}{id}{palabra1}{palabra2}".encode("utf-8").hex()
        else: 
            clave_privada = datos.get("clave_privada")
            palabra1 = None
            palabra2 = None

        datos_privados = {
            "_id": id,
            "clave_sesion": datos.get("clave_sesion")
        }

        datos_publicos = {
            "_id": id,
            "nombre": datos.get("nombre"),
            "rol": datos.get("rol"),
            "saldo": str(Decimal(datos.get("saldo", 0))),
            "cant_bonos": str(0) if datos.get("rol") == "vendedor" or datos.get("rol") == "comprador" else None,
            "nodo_creador_id": creador,
            "clave_privada": clave_privada if datos.get("rol") == "vendedor" or datos.get("rol") == "comprador" else None
        }

        self.guardar_datos_en_usuario(creador, datos_publicos, datos_privados)
        
        transaccion = {
            "tipo": "registro_usuario",
            "_id": id,
            "nombre": datos.get("nombre"),
            "rol": datos.get("rol"),
            "saldo": str(Decimal(datos.get("saldo", 0)))
        }
        firma = self.nodo1.firma_cod([datos_publicos], self.nombreCanal)
        mensaje = " Usuario registrado con éxito."
        solicitud = "registrar_usuario"
        #Validar protocolo
        es_validador, _ = self.validar_protocolo(transaccion, protocolo, creador, solicitud, mensaje, firma, [datos_publicos], datos_privados, palabra1, palabra2)
        print(f"Validar {es_validador}")
        if es_validador:
            # Propagación
            print("Soy autoridad y voy a propagar")
            nodos_canal = self.canal.listar_nodos_canal(self.nombreCanal)
            for nodo in nodos_canal:
                if nodo["_id"] != self.nodo1.obtener_id_nodo_local(self.nombreCanal):
                    try:
                        response = requests.post(f"http://{nodo['direccion']}/sync_users", json={"usuarios": [datos_publicos], "firma": firma, "id_nodo_emisor": self.nodo1.obtener_id_nodo_local(self.nombreCanal)})
                        data = response.json()
                        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: ℹ️  {data['message']}" + Style.RESET_ALL)
                    except:
                        print(f" No se pudo sincronizar con {nodo['direccion']}")

            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Usuario {datos.get('nombre')} registrado correctamente.")
        return make_response(jsonify({"message": " Usuario registrado con éxito.", "palabras": [palabra1, palabra2]}), 200)

    def iniciar_sesion(self, datos):
        """Verifica la sesión del usuario solo si la clave_sesion está presente en la base local."""
        id_usuario = datos.get("_id")
        clave_ingresada = datos.get("clave_sesion")

        if not id_usuario or not clave_ingresada:
            return {"message": " Faltan datos para iniciar sesión"}, 400

        usuario = self.db.get_doc(id_usuario)
        if not usuario:
            return {"message": " Usuario no encontrado"}, 404

        creador = usuario.get("nodo_creador_id")
        if creador != self.nodo1.obtener_id_nodo_local(self.nombreCanal):
            return jsonify({"message": " No puedes iniciar sesión en este nodo. Usa el nodo donde te registraste."}), 403

        clave_correcta = usuario.get("clave_sesion")
        if clave_ingresada != clave_correcta:
            return jsonify({"message": " Clave incorrecta"}), 401

        return jsonify({
            "_id": usuario.get("_id"),
            "nombreCanal": self.nombreCanal,
            "nombre": usuario.get("nombre"),
            "rol": usuario.get("rol"),
            "saldo": usuario.get("saldo", 0),
            "cant_bonos": usuario.get("cant_bonos", 0),
            "protocolo": self.canal.protocolo.nombre_protocolo,
            "nodo_creador_id": usuario.get("nodo_creador_id")
        }), 200

    def registrar_bc(self, bono, id_usuario, serial):
        datos = {
            "serial": serial,
            "_id": id_usuario
        }
        db_bc = Database(db_name=f"{self.nombreCanal}_bonos")
        bono["cantidad_total"] = str(Decimal(bono.get("cantidad_total", 0)))
        bono["cantidad_disponible"] = bono["cantidad_total"]
        # Verificar que el bono tiene serial_origen
        if "serial_origen" not in bono:
            if "serial" in bono:
                bono["serial_origen"] = bono.pop("serial")
            else:
                return make_response(jsonify({"message": " Falta el campo 'serial' o 'serial_origen'"}), 400)

        # Generar ID único del bono
        parent = bono.get("parent", None)
        bono["_id"] = self.generar_id_bono(bono["serial_origen"], id_usuario, parent)

        # Asegurar campos esenciales
        bono["parent"] = parent
        bono["id_propietario"] = id_usuario
        bono["estado"] = "registrado"
        bono["origen"] = bono.get("origen", "ecoregistry")
        bono["precio"] = str(Decimal(bono.get("precio", 0)))
        bono["timestamp"] = datetime.utcnow().isoformat()
        bono["canal"] = self.nombreCanal

        try:
            # Guardar bono en la base de datos de bonos
            db_bc.save_doc(bono)

            # Actualizar datos del usuario
            usuario = self.db.get_doc(id_usuario)
            cant_actual = Decimal(str(usuario.get("cant_bonos", "0")))
            cant_nueva = cant_actual + Decimal(bono["cantidad_disponible"])
            usuario["cant_bonos"] = str(cant_nueva)
            self.db.save_doc(usuario)

            transaccion = {
                "tipo": "registro_bono",
                "id_propietario": id_usuario,
                "origen": bono.get("origen", "ecoregistry"),
                "cantidad_total": str(bono.get("cantidad_total", "0")),
                "proyecto_id": bono.get("proyecto_id"),
                "desarrollador": bono.get("desarrollador"),
                "pais": bono.get("pais"),
                "estado": "registrado",
                "canal": self.nombreCanal,
                "timestamp": datetime.utcnow().isoformat()
            }

            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Bono registrado y asignado a {id_usuario}, cant_bonos actualizada: {cant_nueva}.")
            protocolo = getattr(self.canal.protocolo, "nombre_protocolo", "raft")
            id_nodo_origen = self.nodo1.obtener_id_nodo_local(self.nombreCanal)
            solicitud = "consultar_bono_oraculo"
            mensaje = " Bonos de carbono registrados correctamente"
            firma = self.nodo1.firma_cod([datos], self.nombreCanal)
            es_validador, _ = self.validar_protocolo(transaccion, protocolo, id_nodo_origen, solicitud, mensaje, firma, [datos])
            if es_validador:
                self.propagar_bono_usuario(bono, usuario)
            else:
                print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: No soy validador, entonces no propagaré datos.")
            return make_response(jsonify({"message": " Bonos registrados con éxito."}), 200)

        except Exception as e:
            print(f" Error al registrar bono: {e}")
            return make_response(jsonify({"message": f" Error al registrar o actualizar: {str(e)}"}), 400)

#__/__/__/__/__/__/Otras funciones__/__/__/__/__/__/ 

    def guardar_datos_en_usuario(self, creador, datos_publicos, datos_privados):
        if creador == self.nodo1.obtener_id_nodo_local(self.nombreCanal): 
            self.db.save_doc({**datos_publicos, **datos_privados})
        else: self.db.save_doc(datos_publicos)
        return

    def generar_palabras(self):
        """Genera dos palabras aleatorias para la clave privada."""
        import random
        palabras = ["sol", "luna", "estrella", "rayo", "mar", "roca", "viento", "fuego", "nube", "rio"]
        return random.choice(palabras), random.choice(palabras)
        
    def _obtener_usuario_dict(self, id_usuario):
        try:
            usuario = self.db.get_doc(id_usuario)
            return usuario  # Retorna el dict
        except Exception:
            return None

    def obtener_usuario(self, id_usuario):
        usuario = self._obtener_usuario_dict(id_usuario)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404
        return jsonify(usuario), 200

    def generar_id_bono(self, serial_real: str, usuario: str, parent: str = None) -> str:
        """ Crea un hash único para identificar un grupo de bonos, puede derivarse de otro con el campo `parent`. """
        base = f"{serial_real}_{usuario}_{parent or 'root'}_{int(time.time()*1000)}"
        hash_completo = hashlib.sha256(base.encode("utf-8")).hexdigest()
        return hash_completo[:16]
    
    '''def obtener_saldo(self, usuario):
        """Obtiene el saldo de un usuario desde CouchDB."""
        user_data = self.db.get_doc(usuario)
        if user_data:
            return user_data.get("saldo", 0)
        return "Usuario no encontrado."'''
    
    def obtener_clave_privada(self, usuario):
        """Obtiene el saldo de un usuario desde CouchDB."""
        user_data = self.db.get_doc(usuario)
        if user_data:
            return jsonify({
                "message": " Clave privada obtenida correctamente.",
                "clave_privada": user_data.get("clave_privada", "")
            }), 200
        return jsonify({"message": f" Usuario {usuario} no encontrado"}), 404
    
    def bonos_en_venta(self):
        db = Database(db_name=f"{self.nombreCanal}_bonos")
        bonos = db.find_by_fields({"estado": "en_venta"})
        return bonos
    
    def sync_bonos(self, data):
        db_bc = Database(db_name=f"{self.nombreCanal}_bonos")
        for bono in data:
            bono_id = bono.get("_id")
            if not bono_id:
                print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: Bono sin _id: {bono}")
                continue  # O podrías generar un ID si lo prefieres

            bono_existente = db_bc.get_doc(bono_id)

            if bono_existente:
                # Actualizar el documento
                bono["_rev"] = bono_existente["_rev"]
                db_bc.save_doc(bono)
                print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Bono actualizado: {bono_id}")
            else:
                # Guardar nuevo bono
                db_bc.save_doc(bono)
                print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: Bono nuevo guardado: {bono_id}")

        return make_response(jsonify({"message": " Bonos sincronizados con éxito."}), 200)

#CREO que esta funcion no se está utilizando
    def actualizar_saldo(self, usuario, monto):
        """Actualiza el saldo del usuario en CouchDB y lo registra en la blockchain usando Raft."""
        user_data = self.db.get_doc(usuario)
        if not user_data:
            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: El usuario {usuario} no está registrado.")
            return {"message": " Usuario no encontrado."}

        # Actualizar saldo en CouchDB
        user_data["saldo"] = str(Decimal(user_data["saldo"]) + Decimal(monto))
        self.db.save_doc(user_data)

        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: Saldo actualizado en CouchDB para {usuario}: {user_data['saldo']}")

        # Registrar transacción en la blockchain
        transaccion = {
            "tipo": "actualizar_saldo",
            "usuario": usuario,
            "nuevo_saldo": user_data["saldo"]
        }
        self.canal.blockchain.agregar_transaccion(transaccion)

        # Confirmar transacción en la red Raft
        self.canal.blockchain.confirmar_transaccion_raft(self.nodo1.my_address, self.nodo1.get_nodes())

        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: Saldo actualizado en blockchain para {usuario}: {user_data['saldo']}")
        return {"message": " Saldo actualizado."}

    def validar_protocolo(self, transaccion, protocolo, id_nodo_origen, solicitud, mensaje, mensaje_firmado, datos_publicos=None, datos_privados = None, palabra1 =None, palabra2=None):
        if protocolo == "raft":
            lider = self.canal.protocolo.get_lider()
            if id_nodo_origen != lider:
                # Guardar privado antes de enviar
                if datos_privados:
                    db_local = Database(db_name=f"{self.nombreCanal}_usuarios")
                    db_local.save_doc(datos_privados)
                try:
                    print(f" Nodo {id_nodo_origen} enviando solicitud de registro al líder {lider}...")
                    response = requests.post(f"http://{lider}/{solicitud}", json={"datos": datos_publicos, "firma": mensaje_firmado, "id_nodo_emisor": id_nodo_origen})
                    if response.status_code == 200: 
                        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:   {data['message']}" + Style.RESET_ALL) 
                        return False, make_response(jsonify({"message": f"{mensaje}"}), 200)
                    else: 
                        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:   {data['message']}" + Style.RESET_ALL) 
                        return False, make_response(jsonify({"message": " Fallo al enviar la transacción al validador."}), 403)
                except requests.ConnectionError: return False, make_response(jsonify({"message": " No se pudo conectar con el líder."}), 503)
        
        #  Primero agrega la transacción al mempool (temporal)
        try:
            json.dumps(transaccion, sort_keys=True)
        except TypeError as e:
            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Error al serializar la transacción:", e)
            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Transacción problemática:", transaccion)

        self.canal.blockchain.agregar_transaccion(transaccion)
        # Para RAFT (si es el líder) o POA (si es autoridad actual y puede crear bloque)
        puede_crear = True
        if protocolo == "poa":
            dir_validador_actual, alias, id = self.canal.protocolo.get_validador_actual_info()
    
            #  Si este nodo no es el validador actual, se reenvía la transacción
            if self.nodo1.obtener_id_nodo_local(self.nombreCanal) != id:
                print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Enviando transacción al validador actual: '{alias}' ({id})")
                try:
                    response = requests.post(f"http://{dir_validador_actual}/{solicitud}", json={"datos": datos_publicos, "firma": mensaje_firmado, "id_nodo_emisor": id_nodo_origen})
                    data = response.json()
                    if response.status_code == 200:
                        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:   {data['message']}" + Style.RESET_ALL) 
                        return False, make_response(jsonify({"message": f"{mensaje}"}), 200)
                    else: 
                        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:   {data['message']}" + Style.RESET_ALL) 
                        return False, make_response(jsonify({"message": " Fallo al enviar la transacción al validador."}), 403)
                except requests.RequestException:
                    return False, make_response(jsonify({"message": " No se pudo contactar al validador."}), 503)
            #  Este nodo es el validador actual → puede intentar crear bloque
            puede_crear = self.canal.protocolo.puede_crear_bloque(self.canal.blockchain.transactions)

        if not puede_crear:
            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  No tienes permiso para crear el bloque.")
            return False, make_response(jsonify({"message": " No tienes permisos para crear un bloque."}), 403)
        elif puede_crear: return True, make_response(jsonify({"message": "El bloque se puede crear."}), 403)
        # Crear bloque, para poa se crea en la ejecución del ciclo rotativo
        if protocolo == "raft": 
            self.canal.blockchain.crear_bloque()
            return True, make_response(jsonify({"message": " No tienes permisos para crear un bloque."}), 200)
    
    def cambiar_rol(self, datos):
        usuario_id = datos.get("_id")
        nuevo_rol = datos.get("nuevo_rol")
        saldo_inicial = datos.get("saldo_inicial")
        usuario = self._obtener_usuario_dict(usuario_id)
        
        if not usuario:
            return make_response(jsonify({"message": f" Usuario no encontrado"}), 400)

        if usuario["rol"] != "observador":
            return make_response(jsonify({"message": f" El usuario no es observador, no puede cambiar el rol"}), 409)

        if nuevo_rol not in ["comprador", "vendedor"]:
            return make_response(jsonify({"message": f" Rol no válido"}), 409)
        
        palabra1, palabra2 = self.generar_palabras()
        id_nodo_origen = self.nodo1.get_id(self.nombreCanal)
        clave_privada = f"{id_nodo_origen}{usuario_id}{palabra1}{palabra2}".encode("utf-8").hex()
        
        try:
            usuario["rol"] = nuevo_rol
            usuario["saldo"] = saldo_inicial
            usuario["cant_bonos"] = str(0)
            usuario["clave_privada"] = clave_privada
            self.db.save_doc(usuario)
            return make_response(jsonify({"message": f" Rol actualizado exitosamente", "palabras": [palabra1, palabra2]}), 200)
        except Exception as e:
            return make_response(jsonify({"message": f" Error al guardar: {str(e)}"}), 400)

    def propagar_bono_usuario(self, bono, usuario = None):
        protocolo = getattr(self.canal.protocolo, "nombre_protocolo", "raft")
        nodos_canal = self.canal.listar_nodos_canal(self.nombreCanal)
        id_nodo_emisor = self.nodo1.obtener_id_nodo_local(self.nombreCanal)
        for nodo in nodos_canal:
            if nodo["_id"] != id_nodo_emisor:
                try:
                    print(f"Voy a enviarle a esta direccion {nodo['direccion']}")
                    firma_bono = self.nodo1.firma_cod([bono], self.nombreCanal)
                    response = requests.post(f"http://{nodo['direccion']}/sync_bonos", json={"bonos":[bono], "nombreCanal": self.nombreCanal, "protocolo":protocolo, "firma": firma_bono, "id_nodo_emisor": id_nodo_emisor})
                    if response.status_code == 200:
                        print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Registro de bono sincronizada con nodo {nodo['_id']}")
                    else:
                        print(f" Nodo {nodo['_id']} respondió con error: {response.status_code}")
                    if usuario != None:
                        firma_usuario = self.nodo1.firma_cod([usuario], self.nombreCanal)
                        response1 = requests.post(f"http://{nodo['direccion']}/sync_users", json={"usuarios": [usuario], "firma": firma_usuario, "id_nodo_emisor": id_nodo_emisor})
                        if response1.status_code == 200:
                            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Registro del bono por el usuario sincronizado.")
                        else:
                            print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}: Nodo {nodo['_id']} respondió con error: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"{self.estilo(Fore.MAGENTA, 'contratobasico')}:  Error de red con nodo {nodo['_id']}: {e}")
        return

    def sync_users(self, lista_usuarios):
        for usuario in lista_usuarios:
            #  Si el usuario ya existe en la base de datos, conservamos la clave privada y clave de usuario
            usuario_existente = self.db.get_doc(usuario["_id"])
            if usuario_existente:
                usuario["clave_sesion"] = usuario_existente.get("clave_sesion")

            self.db.save_doc(usuario)
            print(f" Base de datos de usuarios sincronizada con {len(lista_usuarios)} usuarios.")
        return

    #============================== Estilo para imprimir =========================
    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"
