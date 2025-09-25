import hashlib
import time
import requests
from datetime import datetime
from decimal import Decimal
from colorama import Fore, Style
from flask import json, jsonify, make_response
from Data.database import Database
from RedBlockchain.protocolos.admin_protocolo import ProtocolManager
from oraculos.oraculoG import Oraculo

class ContratoBasico:
    def __init__(self, nodo, canal):
        self.canal = canal
        self.nodo = nodo
        self.nombreCanal = canal.nombreCanal.lower()
        self.protocol_manager = ProtocolManager(canal, nodo)
        self.usuario_manager = UsuarioManager(canal, nodo, self.protocol_manager)
        self.oraculo = Oraculo()
        self.bono_manager = BonoManager(canal, nodo, self.usuario_manager, self.protocol_manager, self.oraculo)

    def crear_usuario(self, datos): return self.usuario_manager.crear_usuario(datos)

    def iniciar_sesion(self, datos): return self.usuario_manager.iniciar_sesion(datos)

    def registrar_bc(self, bono, id_usuario, serial): return self.bono_manager.registrar_bc(bono, id_usuario, serial)

    def obtener_usuario(self, id_usuario): return self.usuario_manager.obtener_usuario(id_usuario)

    def obtener_clave_privada(self, usuario): return self.usuario_manager.obtener_clave_privada(usuario)

    def bonos_en_venta(self): return self.bono_manager.bonos_en_venta()

    def sync_bonos(self, data): return self.bono_manager.sync_bonos(data)

    def sync_users(self, lista_usuarios): return self.usuario_manager.sync_users(lista_usuarios)

    def cambiar_rol(self, datos): return self.usuario_manager.cambiar_rol(datos)
    
class UsuarioManager:
    def __init__(self, canal, nodo, protocol_manager):
        self.canal = canal
        self.nodo = nodo
        self.nombreCanal = canal.nombreCanal.lower()
        self.db = Database(db_name=f"{self.nombreCanal}_usuarios")
        self.protocol_manager = protocol_manager

    def crear_usuario(self, datos):
        id = datos.get("_id")
        creador = datos.get("nodo_creador_id")
        if self.db.get_doc(id):
            print(f"{self.estilo(Fore.MAGENTA, 'usuariomanager')}:  La {id} ya está registrada.")
            return make_response(jsonify({"message": f" La ID {id} ya está registrada."}), 400)

        protocolo = getattr(self.canal.protocolo, "nombre_protocolo", "raft")
        if creador == self.nodo.obtener_id_nodo_local(self.nombreCanal):
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
            "cant_bonos": str(0) if datos.get("rol") in ["vendedor", "comprador"] else None,
            "nodo_creador_id": creador,
            "clave_privada": clave_privada if datos.get("rol") in ["vendedor", "comprador"] else None
        }

        self.guardar_datos_en_usuario(creador, datos_publicos, datos_privados)

        transaccion = {
            "tipo": "registro_usuario",
            "_id": id,
            "nombre": datos.get("nombre"),
            "rol": datos.get("rol"),
            "saldo": str(Decimal(datos.get("saldo", 0)))
        }
        firma = self.nodo.firma_cod([datos_publicos], self.nombreCanal)
        mensaje = " Usuario registrado con éxito."
        solicitud = "registrar_usuario"
        es_validador, _ = self.protocol_manager.validar_protocolo(
            transaccion, protocolo, creador, solicitud, mensaje, firma, [datos_publicos], datos_privados, palabra1, palabra2
        )
        if es_validador:
            nodos_canal = self.canal.listar_nodos_canal(self.nombreCanal)
            for nodo in nodos_canal:
                if nodo["_id"] != self.nodo.obtener_id_nodo_local(self.nombreCanal):
                    try:
                        response1 = requests.post(
                            f"http://{nodo['direccion']}/sync_users",
                            json={"usuarios": [datos_publicos], "firma": firma, "id_nodo_emisor": self.nodo.obtener_id_nodo_local(self.nombreCanal)}
                        )
                        data = response1.json()
                        print(f"{self.estilo(Fore.MAGENTA, 'usuariomanager')}:  {data['message']}" + Style.RESET_ALL)
                    except:
                        print(f"⚠️ No se pudo sincronizar con {nodo['direccion']}")
            print(f"{self.estilo(Fore.MAGENTA, 'usuariomanager')}:  Usuario {datos.get('nombre')} registrado correctamente.")
        return make_response(jsonify({"message": " Usuario registrado con éxito.", "palabras": [palabra1, palabra2]}), 200)

    def iniciar_sesion(self, datos):
        id_usuario = datos.get("_id")
        clave_ingresada = datos.get("clave_sesion")
        if not id_usuario or not clave_ingresada:
            return {"message": " Faltan datos para iniciar sesión"}, 400

        usuario = self.db.get_doc(id_usuario)
        if not usuario:
            return {"message": " Usuario no encontrado"}, 404

        creador = usuario.get("nodo_creador_id")
        if creador != self.nodo.obtener_id_nodo_local(self.nombreCanal):
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
        id_nodo_origen = self.nodo.obtener_id_nodo_local(self.nombreCanal)
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

    def sync_users(self, lista_usuarios):
        for usuario in lista_usuarios:
            usuario_existente = self.db.get_doc(usuario["_id"])
            if usuario_existente:
                usuario["clave_sesion"] = usuario_existente.get("clave_sesion")
            self.db.save_doc(usuario)
            print(f"{self.estilo(Fore.MAGENTA, 'usuariomanager')}:  Base de datos de usuarios sincronizada con {len(lista_usuarios)} usuarios.")
        return make_response(jsonify({"message": " Usuarios sincronizados con éxito."}), 200)

    def _obtener_usuario_dict(self, id_usuario):
        try:
            usuario = self.db.get_doc(id_usuario)
            return usuario
        except Exception:
            return None

    def obtener_usuario(self, id_usuario):
        usuario = self._obtener_usuario_dict(id_usuario)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404
        return jsonify(usuario), 200

    def obtener_clave_privada(self, usuario):
        user_data = self._obtener_usuario_dict(usuario)
        if user_data:
            return jsonify({
                "message": " Clave privada obtenida correctamente.",
                "clave_privada": user_data.get("clave_privada", "")
            }), 200
        return jsonify({"message": f" Usuario {usuario} no encontrado"}), 404

    def actualizar_cant_bonos(self, id_usuario, cantidad):
        usuario = self._obtener_usuario_dict(id_usuario)
        if not usuario:
            return {"message": " Usuario no encontrado"}, 404
        cant_actual = Decimal(str(usuario.get("cant_bonos", "0")))
        usuario["cant_bonos"] = str(cant_actual + Decimal(cantidad))
        self.db.save_doc(usuario)
        return {"message": " Cantidad de bonos actualizada."}

    def generar_palabras(self):
        import random
        palabras = ["sol", "luna", "estrella", "rayo", "mar", "roca", "viento", "fuego", "nube", "rio"]
        return random.choice(palabras), random.choice(palabras)

    def guardar_datos_en_usuario(self, creador, datos_publicos, datos_privados):
        if creador == self.nodo.obtener_id_nodo_local(self.nombreCanal):
            self.db.save_doc({**datos_publicos, **datos_privados})
        else:
            self.db.save_doc(datos_publicos)
        return

    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"

class BonoManager:
    def __init__(self, canal, nodo, usuario_manager, protocol_manager, oraculo):
        self.canal = canal
        self.nodo = nodo
        self.nombreCanal = canal.nombreCanal.lower()
        self.db = Database(db_name=f"{self.nombreCanal}_bonos")
        self.usuario_manager = usuario_manager
        self.protocol_manager = protocol_manager
        self.oraculo = oraculo

    def registrar_bc(self, bono, id_usuario, serial):
        datos = {
            "serial": serial,
            "_id": id_usuario
        }
        bono["cantidad_total"] = str(Decimal(bono.get("cantidad_total", 0)))
        bono["cantidad_disponible"] = bono["cantidad_total"]
        if "serial_origen" not in bono:
            if "serial" in bono:
                bono["serial_origen"] = bono.pop("serial")
            else:
                return make_response(jsonify({"message": "❌ Falta el campo 'serial' o 'serial_origen'"}), 400)

        bono["_id"] = self.generar_id_bono(bono["serial_origen"], id_usuario, bono.get("parent", None))
        bono["parent"] = bono.get("parent", None)
        bono["id_propietario"] = id_usuario
        bono["estado"] = "registrado"
        bono["origen"] = bono.get("origen", "ecoregistry")
        bono["precio"] = str(Decimal(bono.get("precio", 0)))
        bono["timestamp"] = datetime.utcnow().isoformat()
        bono["canal"] = self.nombreCanal

        try:
            self.db.save_doc(bono)
            self.usuario_manager.actualizar_cant_bonos(id_usuario, bono["cantidad_disponible"])
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
            
            protocolo = getattr(self.canal.protocolo, "nombre_protocolo", "raft")
            id_nodo_origen = self.nodo.obtener_id_nodo_local(self.nombreCanal)
            solicitud = "consultar_bono_oraculo"
            mensaje = " Bonos de Carbono registrados correctamente"
            firma = self.nodo.firma_cod([datos], self.nombreCanal)
            es_validador, _ = self.protocol_manager.validar_protocolo(transaccion, protocolo, id_nodo_origen, solicitud, mensaje, firma, [datos])
            if es_validador:
                self.oraculo.marcar_bono_registrado(serial)
                self.propagar_bono_usuario(bono)
                print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}:  Bono registrado y asignado a {id_usuario}.")
            else:
                print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}: No soy validador, entonces no propagaré datos.")
            return make_response(jsonify({"message": " Bonos registrados con éxito."}), 200)
        except Exception as e:
            print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}:  Error al registrar bono: {e}")
            return make_response(jsonify({"message": f" Error al registrar o actualizar: {str(e)}"}), 400)

    def bonos_en_venta(self):
        bonos = self.db.find_by_fields({"estado": "en_venta"})
        return bonos

    def sync_bonos(self, data):
        for bono in data:
            bono_id = bono.get("_id")
            if not bono_id:
                print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}: Bono sin _id: {bono}")
                continue
            bono_existente = self.db.get_doc(bono_id)
            if bono_existente:
                bono["_rev"] = bono_existente["_rev"]
                self.db.save_doc(bono)
                print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}:  Bono actualizado: {bono_id}")
            else:
                self.db.save_doc(bono)
                print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}: Bono nuevo guardado: {bono_id}")
        return make_response(jsonify({"message": " Bonos sincronizados con éxito."}), 200)

    def propagar_bono_usuario(self, bono, usuario=None):
        protocolo = getattr(self.canal.protocolo, "nombre_protocolo", "raft")
        nodos_canal = self.canal.listar_nodos_canal(self.nombreCanal)
        id_nodo_emisor = self.nodo.obtener_id_nodo_local(self.nombreCanal)
        for nodo in nodos_canal:
            if nodo["_id"] != id_nodo_emisor:
                try:
                    print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}: Voy a enviarle a esta direccion {nodo['direccion']}")
                    firma_bono = self.nodo.firma_cod([bono], self.nombreCanal)
                    response = requests.post(
                        f"http://{nodo['direccion']}/sync_bonos",
                        json={"bonos": [bono], "nombreCanal": self.nombreCanal, "protocolo": protocolo, "firma": firma_bono, "id_nodo_emisor": id_nodo_emisor}
                    )
                    if response.status_code == 200:
                        print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}:  Registro de bono sincronizada con nodo {nodo['_id']}")
                    else:
                        print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}:  Nodo {nodo['_id']} respondió con error: {response.status_code}")
                    if usuario:
                        firma_usuario = self.nodo.firma_cod([usuario], self.nombreCanal)
                        response = requests.post(
                            f"http://{nodo['direccion']}/sync_users",
                            json={"usuarios": [usuario], "firma": firma_usuario, "id_nodo_emisor": id_nodo_emisor}
                        )
                        if response.status_code == 200:
                            print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}:  Registro del bono por el usuario sincronizado.")
                        else:
                            print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}: Nodo {nodo['_id']} respondió con error: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"{self.estilo(Fore.MAGENTA, 'bonomanager')}:  Error de red con nodo {nodo['_id']}: {e}")
        return

    def generar_id_bono(self, serial_real: str, usuario: str, parent: str = None) -> str:
        base = f"{serial_real}_{usuario}_{parent or 'root'}_{int(time.time()*1000)}"
        hash_completo = hashlib.sha256(base.encode("utf-8")).hexdigest()
        return hash_completo[:16]

    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"
