from datetime import datetime
from decimal import Decimal, getcontext
from colorama import Fore, Style
import requests
from flask import jsonify, make_response
from oraculos.oraculoG import Oraculo

getcontext().prec = 28

class OraculoManager:
    def __init__(self):
        try:
            self.oraculo = Oraculo()
            self.is_available = True
        except Exception as e:
            print(f"{self.estilo(Fore.RED, 'oraculomanager')}:  Error al inicializar Oraculo: {e}")
            self.oraculo = None
            self.is_available = False

    def actualizar_estado(self, serial_origen, cantidad):
        if not self.is_available or self.oraculo is None:
            return {"message": f" Oráculo no disponible para serial {serial_origen}"}
        try:
            resultado = self.oraculo.actualizar_estado(serial_origen, cantidad)
            if isinstance(resultado, bool):
                if resultado:
                    return {"message": " Estado del bono actualizado en el oráculo."}
                else:
                    return {"message": f" Serial {serial_origen} no encontrado en el oráculo."}
            return resultado  # Propaga el make_response si se retorna
        except Exception as e:
            print(f"{self.estilo(Fore.RED, 'oraculomanager')}:  Error al actualizar estado: {e}")
            return {"message": f" Error al actualizar estado para serial {serial_origen}: {e}"}

    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"

class SincronizadorCompraventa:
    def __init__(self, canal, nodo):
        self.canal = canal
        self.nodo = nodo
        self.nombreCanal = canal.nombreCanal.lower()

    def sincronizar_compra(self, comprador, vendedor, bono, bono_resultante, id_nodo_origen):
        nodos_canal = self.canal.listar_nodos_canal(self.nombreCanal)
        payload = {
            "comprador": comprador,
            "vendedor": vendedor,
            "bono": bono,
            "bono_resultante": bono_resultante,
        }
        firma = self.nodo.firma_cod([payload], self.nombreCanal)
        for nodo in nodos_canal:
            if nodo["_id"] != id_nodo_origen:
                try:
                    response = requests.post(
                        f"http://{nodo['direccion']}/sync_compra",
                        json={"datos": [payload], "firma": firma, "id_nodo_emisor": id_nodo_origen}
                    )
                    if response.status_code == 200:
                        print(f"{self.estilo(Fore.YELLOW, 'sincronizadorcompraventa')}:  Compra sincronizada con nodo {nodo['_id']}")
                    else:
                        print(f"{self.estilo(Fore.YELLOW, 'sincronizadorcompraventa')}:  Nodo {nodo['_id']} respondió con error: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"{self.estilo(Fore.YELLOW, 'sincronizadorcompraventa')}:  Error de red con nodo {nodo['_id']}: {e}")
        return {"message": " Sincronización de compra completada."}

    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"

class ContratoCompraventa:
    def __init__(self, canal, nodo, contrato_basico):
        self.canal = canal
        self.nodo = nodo
        self.nombreCanal = canal.nombreCanal.lower()
        self.contrato_basico = contrato_basico
        self.usuario_manager = contrato_basico.usuario_manager
        self.bono_manager = contrato_basico.bono_manager
        self.protocol_manager = contrato_basico.protocol_manager
        self.oraculo_manager = OraculoManager()
        self.sincronizador = SincronizadorCompraventa(canal, nodo)

    def marcar_en_venta(self, data):
        id = data.get("_id")
        precio = data.get("precio")
        id_usuario = data.get("id_usuario")
        cantidad_enVenta = data.get("cantidad_enVenta")

        bono = self.bono_manager.db.get_doc(id)
        if not bono:
            return make_response(jsonify({"message": " Bono no encontrado"}), 404)
        if bono["id_propietario"] != id_usuario:
            return make_response(jsonify({"message": " No eres el propietario de este bono"}), 403)

        cantidad_enVenta = Decimal(str(cantidad_enVenta))
        if cantidad_enVenta <= 0:
            return make_response(jsonify({"message": " La cantidad en venta debe ser mayor que cero"}), 400)
        cantidad_disponible = Decimal(str(bono.get("cantidad_disponible", 0)))
        cantidad_enventa_actual = Decimal(str(bono.get("cantidad_enventa", 0)))

        if cantidad_enVenta > cantidad_disponible:
            return make_response(jsonify({"message": f" No puedes vender más de los disponibles ({cantidad_disponible})"}), 400)

        bono["cantidad_enventa"] = str(cantidad_enventa_actual + cantidad_enVenta)
        bono["cantidad_disponible"] = str(cantidad_disponible - cantidad_enVenta)
        bono["precio"] = precio
        bono["estado"] = "en_venta"

        self.bono_manager.propagar_bono_usuario(bono)
        self.bono_manager.db.save_doc(bono)
        return make_response(jsonify({"message": " Bono puesto en venta exitosamente"}), 200)

    def verificar_fondos(self, comprador, precio_total):
        return Decimal(comprador["saldo"]) >= precio_total

    def actualizar_saldos(self, comprador, vendedor, precio_total):
        comprador["saldo"] = str(Decimal(comprador["saldo"]) - precio_total)
        vendedor["saldo"] = str(Decimal(vendedor["saldo"]) + precio_total)
        return comprador, vendedor

    def actualizar_bonos_usuarios(self, comprador, vendedor, cantidad):
        comprador["cant_bonos"] = str(Decimal(comprador.get("cant_bonos", 0)) + cantidad)
        vendedor["cant_bonos"] = str(Decimal(vendedor.get("cant_bonos", 0)) - cantidad)
        return comprador, vendedor

    def manejar_bono_comprador(self, bono, id_comprador, cantidad):
        bonos_existentes = self.bono_manager.db.find_by_fields({
            "parent": bono["_id"],
            "id_propietario": id_comprador
        })
        if bonos_existentes:
            bono_existente = bonos_existentes[0]
            bono_existente["cantidad_total"] = str(Decimal(bono_existente["cantidad_total"]) + cantidad)
            bono_existente["cantidad_disponible"] = str(Decimal(bono_existente["cantidad_disponible"]) + cantidad)
            return bono_existente, bono_existente["_id"]
        else:
            id_bono_nuevo = self.bono_manager.generar_id_bono(bono["serial_origen"], id_comprador, bono["_id"])
            nuevo_bono = {
                "_id": id_bono_nuevo,
                "serial_origen": bono["serial_origen"],
                "proyecto_id": bono["proyecto_id"],
                "desarrollador": bono["desarrollador"],
                "cantidad_total": str(cantidad),
                "cantidad_disponible": str(cantidad),
                "estado": "registrado",
                "parent": bono["_id"],
                "id_propietario": id_comprador,
                "origen": bono.get("origen", "ecoregistry"),
                "canal": bono["canal"],
                "precio": str(0),
                "precio_de_compra": bono["precio"],
                "timestamp": datetime.utcnow().isoformat()
            }
            return nuevo_bono, id_bono_nuevo

    def actualizar_bono_original(self, bono, cantidad):
        bono["cantidad_enventa"] = str(Decimal(bono["cantidad_enventa"]) - cantidad)
        bono["cantidad_total"] = str(Decimal(bono["cantidad_total"]) - cantidad)
        if Decimal(bono["cantidad_enventa"]) <= 0:
            bono["estado"] = "registrado"
        return bono

    def guardar_informacion_usuarios(self, comprador, vendedor, bono, bono_resultante):
        if comprador:
            self.usuario_manager.db.save_doc(comprador)
            print(f"{self.estilo(Fore.YELLOW, 'contratocompraventa')}:  Comprador sincronizado: {comprador['_id']}")
        if vendedor:
            self.usuario_manager.db.save_doc(vendedor)
            print(f"{self.estilo(Fore.YELLOW, 'contratocompraventa')}:  Vendedor sincronizado: {vendedor['_id']}")
        if bono:
            self.bono_manager.db.save_doc(bono)
            print(f"{self.estilo(Fore.YELLOW, 'contratocompraventa')}:  Bono actualizado: {bono['_id']}")
        if bono_resultante:
            self.bono_manager.db.save_doc(bono_resultante)
            print(f"{self.estilo(Fore.YELLOW, 'contratocompraventa')}:  Bono resultante creado: {bono_resultante['_id']}")

    def realizar_compra(self, datos):
        id_bono = datos["_id"]
        id_comprador = datos["id_propietario"]
        cantidad = Decimal(str(datos["cantidad"]))
        bono = self.bono_manager.db.get_doc(id_bono)
        comprador = self.usuario_manager.db.get_doc(id_comprador)
        vendedor = self.usuario_manager.db.get_doc(bono["id_propietario"])

        if not bono or not comprador or not vendedor:
            return make_response(jsonify({"message": " Bono o usuario no encontrado"}), 404)

        precio_total = Decimal(str(bono["precio"])) * cantidad
        if not self.verificar_fondos(comprador, precio_total):
            return make_response(jsonify({"message": " Fondos insuficientes"}), 400)

        if Decimal(str(bono.get("cantidad_enventa", 0))) < cantidad:
            return make_response(jsonify({"message": " Cantidad no disponible"}), 400)

        comprador, vendedor = self.actualizar_saldos(comprador, vendedor, precio_total)
        comprador, vendedor = self.actualizar_bonos_usuarios(comprador, vendedor, cantidad)
        bono_resultante, id_bono_nuevo = self.manejar_bono_comprador(bono, id_comprador, cantidad)
        bono = self.actualizar_bono_original(bono, cantidad)

        transaccion = {
            "tipo": "Compraventa",
            "comprador": id_comprador,
            "vendedor": bono["id_propietario"],
            "bono_original": bono["_id"],
            "bono_nuevo": id_bono_nuevo,
            "cantidad": str(cantidad),
            "precio_unitario": bono["precio"],
            "total_pagado": str(precio_total),
            "timestamp": datetime.utcnow().isoformat()
        }
        mensaje = " Transacción exitosa."
        protocolo = getattr(self.canal.protocolo, "nombre_protocolo", "raft")
        id_nodo_origen = self.nodo.obtener_id_nodo_local(self.nombreCanal)
        solicitud = "comprar_bono"
        firma = self.nodo.firma_cod([datos], self.nombreCanal)
        es_validador, response = self.protocol_manager.validar_protocolo(
            transaccion, protocolo, id_nodo_origen, solicitud, mensaje, firma, [datos]
        )

        if es_validador:
            print(f"{self.estilo(Fore.YELLOW, 'contratocompraventa')}: 📢 Soy el nodo encargado de subir y propagar la información")
            self.guardar_informacion_usuarios(comprador, vendedor, bono, bono_resultante)
            if not bono["parent"]:
                resultado_oraculo = self.oraculo_manager.actualizar_estado(bono["serial_origen"], cantidad)
                if isinstance(resultado_oraculo, dict) and "message" in resultado_oraculo:
                    if "❌" in resultado_oraculo["message"]:
                        print(f"{self.estilo(Fore.YELLOW, 'contratocompraventa')}: ⚠️ Oráculo no actualizado, continuando transacción: {resultado_oraculo['message']}")
                elif isinstance(resultado_oraculo, tuple):  # Maneja el caso de make_response
                    print(f"{self.estilo(Fore.YELLOW, 'contratocompraventa')}: ⚠️ Oráculo retornó error, continuando transacción")
            self.sincronizador.sincronizar_compra(comprador, vendedor, bono, bono_resultante, id_nodo_origen)
            return make_response(jsonify({"message": " Compra realizada exitosamente", "saldo": comprador["saldo"]}), 200)
        return response

    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"