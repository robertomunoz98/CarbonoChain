import base64
from decimal import Decimal
import os
import signal
import socket
import threading
import time
import requests
from flask import Flask, Response, request, jsonify
from Data.database import Database
from RedBlockchain.nodos import Nodo
from RedBlockchain.canal import Canal
from RedBlockchain.bloques import Blockchain
from RedBlockchain.contratos.contratobasico import ContratoBasico
from RedBlockchain.contratos.contratocompraventa import ContratoCompraventa
from oraculos.oraculoG import Oraculo

app = Flask(__name__)
"""Funciones"""
#Inicio el servidor para que pueda escuchar el CLI
def iniciar_servidor():
    app.run(host="0.0.0.0", port=5001, debug=False)

def obtener_ip_local():
    try:
        # Se conecta a un servidor externo para obtener la IP local correcta
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Usa el DNS de Google como referencia
        ip_local = s.getsockname()[0]
        s.close()
        return ip_local
    except Exception as e:
        print(f" Error al obtener la IP local: {e}")
        return "127.0.0.1"  # En caso de fallo, usa localhost como respaldo

address = obtener_ip_local() + ":5001" # Obtén la IP de la máquina local automáticamente
nodo = Nodo(address)  # Inicialización del nodo
# Verificar si el nodo ya tiene canales guardados en su base de datos
canal_db = Database(db_name="canales")
canales_guardados = canal_db.get_all_docs()
canal = None
contratobasico = None
contratocompraventa = None

oraculo_instance = Oraculo()

#oraculo_instance = oraculo()

def instancia(nombreCanal):
    global canal
    canal_info = buscar_canal_por_nombre(nombreCanal)

    if not canal_info:
        return None, "El canal no existe not1"

    protocolo = canal_info.get("protocolo", "raft").lower()
    if not canal:
        canal = Canal(nodo, nombreCanal, protocolo)
    return canal, None

def buscar_canal_por_nombre(nombre):
    db_canales = Database(db_name="canales")
    canales = db_canales.get_all_docs()
    nombre_normalizado = nombre.strip().lower()
    for canal in canales:
        if canal.get("nombre", "").strip().lower() == nombre_normalizado:
            return canal
    return None

def seleccion_de_canal():
    global canal, contratobasico, contratocompraventa
    time.sleep(0.5)
    if canales_guardados:
        print(" Se encontraron los siguientes canales registrados en este nodo:")
        for idx, canal_data in enumerate(canales_guardados, start=1):
            nombre = canal_data["nombre"]
            protocolo = canal_data.get("protocolo", "raft").upper()
            print(f"{idx}. {nombre} [Protocolo: {protocolo}]")

        seleccion = input("\n Ingrese el número del canal con el que desea trabajar: ")
        try:
            seleccion = int(seleccion)
            if 1 <= seleccion <= len(canales_guardados):
                canal_data = canales_guardados[seleccion - 1]
                nombre_canal = canal_data["nombre"]
                protocolo = canal_data.get("protocolo", "raft").lower()

                # Crear canal según el protocolo correspondiente
                if protocolo == "raft":
                    from RedBlockchain.protocolos.protocoloRAFT import ProtocoloRaft
                    canal = Canal(nodo, nombre_canal, "raft")
                    contratobasico = ContratoBasico(nodo, canal)
                    contratocompraventa = ContratoCompraventa(canal, nodo, contratobasico)
                    print(f"\n Nodo reconocido en el canal '{nombre_canal}' con Raft. Reiniciando protocolo...")
                    canal.protocolo.iniciar_raft()

                elif protocolo == "poa":
                    from RedBlockchain.protocolos.protocoloPoA import ProtocoloPoA
                    canal = Canal(nodo, nombre_canal, "poa")
                    contratobasico = ContratoBasico(nodo, canal)
                    contratocompraventa = ContratoCompraventa(canal, nodo, contratobasico)
                    print(f"\n Nodo reconocido en el canal '{nombre_canal}'.\n🔐 Iniciando Protocolo Proof of Authority (PoA)....")
                    
                    canal.protocolo.iniciar_poa()
                else:
                    print(" Protocolo desconocido para este canal.")
                    exit()
                nodo.my_ip(canal.nombreCanal)
            else:
                print(" Selección inválida.")
                exit()
        except ValueError:
            print(" Entrada inválida. Debe ser un número.")
            exit()
    else:
        print("⚠ Este nodo no estaba registrado en ningún canal. Puede crear o unirse a uno.")

@app.route('/nodo_id', methods=['POST'])
def nodo_id():
    global canal, nodo
    id = nodo.obtener_id_nodo_local(canal.nombreCanal)
    print(f"Imprimiendo el ide a enviar: {id}")
    return jsonify({"nodo_id": id}), 200

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok"}), 200

@app.route('/canal_activo', methods=['GET'])
def obtener_canal_activo():
    if canal:
        nombre = canal.nombreCanal
        protocolo = getattr(canal.protocolo, "nombre_protocolo", "desconocido").upper()
        return jsonify({"canal": nombre, "protocolo": protocolo}), 200
    else:
        return jsonify({"error": "No hay canal activo en este nodo"}), 404

@app.route('/crear_canal', methods=['POST'])
def crear_canal():
    """Crea un nuevo canal y lo guarda en la base de datos 'canales'."""
    global canal, contratobasico, contratocompraventa, nodo
    data = request.get_json()
    nombre = data.get("nombre").lower()
    protocolo = data.get("protocolo")
    clave = data.get("clave")

    if not nombre:
        return jsonify({"message": "El nombre del canal es obligatorio"}), 400

    canal = Canal(nodo, nombre, protocolo)

    if canal.buscar_canal_por_nombre(nombre):
        return jsonify({"error": "Ya existe un canal con este nombre."}), 400
    #  Asegurar que el nodo se autoproclame líder al crear el canal
    if protocolo == "raft":
        #  Iniciar Raft antes de crear el canal
        canal.crear_canal(nombre, address, clave, protocolo)
        if canal.protocolo.get_lider() is None:
            canal.protocolo.lider = canal.nodo.obtener_ip_local(nombre)
            print(f" {canal.nodo.my_address} se proclama líder del canal.")
        threading.Thread(target=canal.protocolo.iniciar_raft, daemon=True).start()
        #  Verificar si el nodo tiene permisos ANTES de registrar el canal en CouchDB
        if not canal.protocolo.puede_crear_bloque():
            print(" No tienes permisos para registrar la creación del canal en la blockchain.")
            return jsonify({"error": "No eres el líder, no puedes registrar la transacción en la blockchain."}), 403
    elif protocolo == "poa":
        canal.crear_canal(nombre, address, clave, protocolo)
        threading.Thread(target=canal.protocolo.iniciar_poa, daemon=True).start()
    contratobasico = ContratoBasico(nodo, canal)
    contratocompraventa = ContratoCompraventa(canal, nodo, contratobasico)
    prot= protocolo.upper()
    print(f" Canal '{nombre}' con '{prot}' creado correctamente")
    return jsonify({"message": f" Canal '{nombre}' con protocolo '{prot}' creado correctamente"}), 200

@app.route('/listar_nodos', methods=['GET'])
def listar_nodos():
    """Lista los nodos que están en el canal actual."""
    if not canal:
        return jsonify({"message": "No estás en ningún canal"}), 400
    
    resultado = canal.listar_nodos()
    return jsonify(resultado), 200

@app.route('/datos_canal', methods=['GET'])
def datos_canal():
    global canal
    resultado = {
        "nombre_canal": canal.nombreCanal,
        "protocolo": canal.protocolo.nombre_protocolo,
        "id_nodo": canal.nodo.get_id(canal.nombreCanal)  # o canal.tipo_consenso, según cómo lo hayas nombrado
    }
    return jsonify(resultado), 200

#__/__/__/__/__/__/__/__/ Del protocolo RAFT __/__/__/__/__/__/__/__/
@app.route('/get_lider', methods=['GET'])
def obtener_lider():
    """Devuelve el líder actual del canal."""
    if canal and canal.protocolo:
        if hasattr(canal.protocolo, "get_lider"):
            return jsonify({"leader": canal.protocolo.get_lider()}), 200
        else:
            return jsonify({"message": " El protocolo actual no utiliza líder."}), 200
    return jsonify({"error": "No hay un canal activo o protocolo definido"}), 400

@app.route('/latido', methods=['POST'])
def recibir_latido():
    global canal
    """Recibe un latido de otro nodo y actualiza su estado en el protocolo Raft."""
    if not canal or not hasattr(canal, "protocolo") or not canal.protocolo:
        return jsonify({"error": " El nodo aún no ha inicializado su canal o protocolo."}), 400
    
    data = request.get_json()
    sender = data.get("sender")

    if not sender:
        return jsonify({"error": "Latido sin remitente"}), 400

    if canal and canal.protocolo:
        canal.protocolo.recibir_latido(sender)  #  Aquí se actualiza `ultimo_latido_recibido`
        return jsonify({"message": "Latido recibido"}), 200
    else:
        return jsonify({"error": "Protocolo no inicializado"}), 500
    
#__/__/__/__/__/__/__/__/ Del protocolo PoA __/__/__/__/__/__/__/__/
@app.route('/asignar_autoridad', methods=['POST'])
def asignar_autoridad():
    data = request.get_json()
    resultado = canal.protocolo.nueva_autoridad(data)
    if isinstance(resultado, tuple) or isinstance(resultado, Response):  # Si se devuelve un make_response, lo regresamos directamente
        return resultado
    return jsonify(resultado), 200

@app.route('/sync_nodo_autoridad', methods=['POST'])
def sync_nodo_autoridad():
    data = request.get_json()
    resultado = canal.protocolo.nueva_autoridad(data, propagar = False)
    
    if isinstance(resultado, tuple) or isinstance(resultado, Response):  # Si se devuelve un make_response, lo regresamos directamente
        return resultado
    return jsonify(resultado), 200

@app.route('/sync_turno', methods=['POST'])
def sync_turno():
    data = request.get_json()
    if canal and hasattr(canal.protocolo, 'actualizar_turno'):
        canal.protocolo.actualizar_turno(data)
        return jsonify({"message": "Turno actualizado"}), 200
    return jsonify({"message": "No se pudo actualizar el turno"}), 400

#__/__/__/__/__/__/__/__/ Para que un nodo se una al canal__/__/__/__/__/__/__/__/__/__/
@app.route('/solicitar_union', methods=['POST'])
def solicitar_union():
    """Verifica que la clave es correcta y devuelve información del canal."""
    data = request.get_json()
    clave_ingresada = data.get("clave")
    nombreCanal = data.get("nombreCanal")
    nuevo_nodo = data.get("nuevo_nodo")

    if not nuevo_nodo or not clave_ingresada or not nombreCanal:
        return jsonify({"message": "Faltan datos"}), 400
    
    canal, error = instancia(nombreCanal)
    if error:
        return jsonify({"error": error}), 404

    protocolo_actual = canal.nombre_protocolo
    print(f"El protocolo actual es: {protocolo_actual}")
    resultado = canal.validar_ingreso(clave_ingresada, nombreCanal, nuevo_nodo, protocolo_actual)

    if "error" in resultado:
        return jsonify(resultado), 403  # Retorna error si la validación falla
    
    return jsonify(resultado), 200


@app.route('/sync_nuevo_nodo', methods=['POST'])
def sync_nuevo_nodo():
    """Permite sincroniza la información de un canal a un nuevo nodo."""
    data = request.get_json()
    nuevo_nodo = data.get("nuevo_nodo")
    nombreCanal = data.get("nombreCanal")
    nodo_id = data.get("_id")
    clave_publica = data.get("clave_publica")

    if not nuevo_nodo or not nombreCanal:
        return jsonify({"message": "Faltan datos"}), 400
    
    canal, error = instancia(nombreCanal)
    if error:
        return jsonify({"error": error}), 404
    protocoloactual = canal.nombre_protocolo
    print(f"El protocolo actual es: {protocoloactual}")
    resultado = canal.sync_nuevo_nodo(nuevo_nodo, nodo_id, nombreCanal, protocoloactual, clave_publica)

    if "error" in resultado:
        return jsonify(resultado), 403  # Retorna error si la validación falla
    
    return jsonify(resultado), 200

@app.route('/unirse_canal', methods=['POST'])
def unirse_canal():
    """Permite a un nodo unirse a un canal existente contactando a un nodo conocido."""
    global canal, contratobasico

    data = request.get_json()
    nombre_canal = data.get("nombreCanal")
    clave_ingresada = data.get("clave")
    nodo_conocido = data.get("nodo_conocido")  # 🔹 IP:puerto de un nodo ya en el canal

    if not nombre_canal or not clave_ingresada or not nodo_conocido:
        return jsonify({"message": "Faltan datos. Debes proporcionar el nombre del canal, la clave y un nodo conocido."}), 400

    nodo_address = nodo.my_address  # Dirección de este nodo (el que se quiere unir)

    # 🔹 Hacer una solicitud al nodo conocido para unirse
    try:

        response = requests.post(
            f"http://{nodo_conocido}/solicitar_union",
            json={"nuevo_nodo": nodo_address, "clave": clave_ingresada, "nombreCanal": nombre_canal}
        )
        
        if response.status_code == 200:
            # 🔹 Ahora que se aceptaron las credenciales se generan las claves
            response_data = response.json()  # ← aquí obtienes el diccionario completo
            nodo_id = response_data.get("_id")
            nodo.guardar_id_nodo_local(nombre_canal, nodo_id)
            protocolo = response_data.get("protocolo", "raft").lower()
            print(f"\nEl protocolo recibido es: {protocolo}")
            canal = Canal(nodo, nombre_canal, protocolo)
            contratobasico = ContratoBasico(nodo, canal)
            # iniciar protocolo dependiendo del tipo
            clave_publica = nodo.generar_y_guardar_claves(nombre_canal)
            response1 = requests.post(
                f"http://{nodo_conocido}/sync_nuevo_nodo",
                json={"nuevo_nodo": nodo_address, "_id": nodo_id , "nombreCanal": nombre_canal, "clave_publica": clave_publica}
            )
            if response1.status_code == 200: 
                print("entre a iniciar el protocolo")
                if protocolo == "raft":
                    threading.Thread(target=canal.protocolo.iniciar_raft, daemon=True).start()
                elif protocolo == "poa":
                    threading.Thread(target=canal.protocolo.iniciar_poa, daemon=True).start()
                return jsonify({"message": f" Nodo unido al canal '{nombre_canal}'"}), 200
        else: return jsonify(response.json()), response.status_code
    except requests.RequestException:
        return jsonify({"error": f"No se pudo contactar con el nodo {nodo_conocido}"}), 500
    
@app.route('/actualizar_clave', methods=['POST'])
def actualizar_clave():
    """Permite que el líder del canal actualice la clave de acceso."""
    data = request.get_json()
    nueva_clave = data.get("clave")
    nombreCanal = data.get("nombreCanal")

    if not nueva_clave:
        return jsonify({"error": "Debes proporcionar una nueva clave."}), 400

    resultado = canal.actualizar_clave(nombreCanal,nueva_clave)
    return jsonify(resultado), 200

# __/__/__/__/__/__/__/__/__/__/ SINCRONIZACIONES __/__/__/__/__/__/__/__/__/__/

@app.route('/sync_nodos', methods=['POST'])
def sync_nodos():
    """Recibe y almacena la lista de nodos del canal propagada por otro nodo."""
    data = request.get_json()
    nodos_recibidos = data.get("nodos", [])  #  Recibir la lista de nodos
    nombreCanal = data.get("nombreCanal")
    canal, error = instancia(nombreCanal)

    if error:
        return jsonify({"error": error}), 404
    print(f"🔄 Recibiendo {len(nodos_recibidos)} nodos para el canal {nombreCanal}...")
    
    #  Agregar los nodos exactamente como fueron recibidos
    canal.agregar_nodos_al_canal(nodos_recibidos, nombreCanal)
    
    return jsonify({"message": "Lista de nodos sincronizada correctamente"}), 200

@app.route('/sync_canal', methods=['POST'])
def sync_canal():
    """Recibe y almacena la información del canal propagada por otro nodo."""
    global canal, nodo
    data = request.get_json()
    canal_data = data.get("canal_data")

    if not canal_data:
        return jsonify({"error": "No se recibió información del canal"}), 400
    
    if canal is None:
        canal = Canal(nodo, canal_data["nombre"], canal_data["protocolo"])

    canal.db_canales.save_doc(canal_data)  # Guardar la info del canal
    print(f" Información del canal '{canal_data['nombre']}' sincronizada.")

    return jsonify({"message": "Información del canal sincronizada"}), 200

@app.route('/sync_chain', methods=['POST'])
def sync_chain():
    """Recibe y almacena la blockchain propagada por otro nodo."""
    global canal
    data = request.get_json()
    nueva_chain = data.get("chain", [])
    nombreCanal = data.get("nombreCanal")
    protocolo = data.get("protocolo")
    firma_b64 = request.json.get("firma")
    firma = base64.b64decode(firma_b64)
    id_nodo_emisor = data.get("id_nodo_emisor")

    if not protocolo:
        canal_info = buscar_canal_por_nombre(nombreCanal)
        if canal_info:
            protocolo = canal_info.get("protocolo", "raft").lower()
        else:
            return jsonify({"error": "No se pudo determinar el protocolo"}), 400

    if not canal or canal.nombreCanal != nombreCanal:
        print(f"El protocolo recibido es: {protocolo}")
        canal = Canal(nodo, nombreCanal, protocolo)  #  Si no hay canal, créalo

    if not canal.blockchain:
        canal.blockchain = Blockchain(nodo, canal.nombreCanal, canal)
    doc = "blockchain"
    verificacion = nodo.verificar_datos_propagados(firma, id_nodo_emisor, canal.nombreCanal, nueva_chain, doc)
    if verificacion.status_code != 200:
        return verificacion  # devuelve el error de verificación directamente
    else:
        for block in nueva_chain:
            if not canal.blockchain.db.get_doc(block["_id"]):  #  Evita duplicados
                canal.blockchain.db.save_doc(block)
                canal.blockchain.transactions = []
        print(" Blockchain sincronizada con éxito.")
    return jsonify({"message": "Blockchain sincronizada con éxito"}), 200

@app.route('/sync_bonos', methods=['POST'])
def sync_bonos():
    global canal, contratobasico
    data = request.get_json()
    bonos_recibidos = data.get("bonos", [])
    nombreCanal = data.get("nombreCanal")
    protocolo = data.get("protocolo")
    firma_b64 = request.json.get("firma")
    firma = base64.b64decode(firma_b64)
    id_nodo_emisor = data.get("id_nodo_emisor")

    if not canal:
        canal = Canal(nodo, nombreCanal, protocolo)
    if not contratobasico:
        contratobasico = ContratoBasico(nodo, canal)
    doc = "bonos de carbono"
    verificacion = nodo.verificar_datos_propagados(firma, id_nodo_emisor, canal.nombreCanal, bonos_recibidos, doc)
    if verificacion.status_code != 200:
        return verificacion  # devuelve el error de verificación directamente
    contratobasico.sync_bonos(bonos_recibidos)
    return jsonify({"message": "Bonos sincronizados con éxito"}), 200

#__/__/__/__/__/__/__/__/ Usuarios__/__/__/__/__/__/__/__/__/__/
@app.route('/registrar_usuario', methods=['POST'])
def registrar_usuario():
    """Registra uno o más usuarios en la red blockchain."""
    global contratobasico, nodo, canal
    data = request.get_json()
    print(f" Datos recibidos en /registrar_usuario: {data}")

    if not data:
        return jsonify({"error": " No se recibió ningún dato."}), 400

    #  Detectar si viene desde otro nodo (con firma)
    if "datos" in data and "firma" in data and "id_nodo_emisor" in data:
        datos_usuario = data["datos"]
        firma_b64 = data["firma"]
        id_nodo_emisor = data["id_nodo_emisor"]
        print(f" Usuario(s) extraído(s): {datos_usuario}")
        print(f" Firma base64: {firma_b64}")
        print(f" Nodo emisor: {id_nodo_emisor}")
    else:
        datos_usuario = data
        firma_b64 = None
        id_nodo_emisor = None

    lista_usuarios = datos_usuario
    for usuario in lista_usuarios:
        id_usuario = usuario.get("_id")
        creador = usuario.get("nodo_creador_id")

        if not id_usuario or not creador:
            return jsonify({"message": " Falta _id o nodo_creador_id en uno de los usuarios"}), 400

        #  Verificar si este nodo es el creador
        if creador == nodo.obtener_id_nodo_local(canal.nombreCanal):
            resultado = contratobasico.crear_usuario(usuario)
        else:
            try:
                firma = base64.b64decode(firma_b64)
            except Exception:
                return jsonify({"message": " Firma invalida."}), 400

            doc = "registro de usuario"
            verificacion = nodo.verificar_datos_propagados(
                firma, id_nodo_emisor, canal.nombreCanal, lista_usuarios, doc
            )
            if verificacion.status_code != 200:
                return verificacion

            resultado = contratobasico.crear_usuario(usuario)
        return resultado

@app.route('/iniciar_sesion', methods=['POST'])
def iniciar_sesion():
    global contratobasico
    data =request.get_json()
    resultado = contratobasico.iniciar_sesion(data)
    return resultado

@app.route("/obtener_usuario/<id_usuario>", methods=["GET"])
def obtener_usuario(id_usuario):
    global contratobasico
    resultado = contratobasico.obtener_usuario(id_usuario)
    if isinstance(resultado, tuple) or isinstance(resultado, Response):  # Si se devuelve un make_response, lo regresamos directamente
        return resultado
    return jsonify(resultado), 200

@app.route('/cambiar_rol', methods=['POST'])
def obtener_saldo():
    global contratobasico
    data =request.get_json()
    respuesta = contratobasico.cambiar_rol(data)
    return respuesta

@app.route('/obtener_clave_privada/<usuario>', methods=['GET'])
def obtener_clave_privada(usuario):
    """Obtiene el saldo de un usuario."""
    global contratobasico
    clave_privada = contratobasico.obtener_clave_privada(usuario)
    if isinstance(clave_privada, tuple) or isinstance(clave_privada, Response):  # Si se devuelve un make_response, lo regresamos directamente
        return clave_privada
    return jsonify(clave_privada), 200

@app.route('/actualizar_saldo', methods=['POST'])
def actualizar_saldo():
    """Actualiza el saldo de un usuario y lo registra en la blockchain."""
    data = request.get_json()
    usuario = data.get("usuario")
    monto = data.get("monto")

    if not usuario or monto is None:
        return jsonify({"error": "Usuario y monto son obligatorios"}), 400

    resultado = ContratoBasico.actualizar_saldo(usuario, monto)
    return jsonify(resultado), 200

@app.route('/sync_users', methods=['POST'])
def sync_users():
    """Sincroniza la lista de usuarios con la base de datos local."""
    global canal, nodo, contratobasico
    data = request.get_json()
    lista_usuarios = data.get("usuarios", [])
    firma_b64 = request.json.get("firma")
    firma = base64.b64decode(firma_b64)
    id_nodo_emisor = data.get("id_nodo_emisor")

    if not canal:
        return jsonify({"error": "Este nodo no está en ningún canal"}), 400

    #  Crear instancia del contrato para manejar los usuarios
    if not contratobasico:
        contratobasico = ContratoBasico(nodo, canal)
    doc = "Usuarios"
    verificacion = nodo.verificar_datos_propagados(firma, id_nodo_emisor, canal.nombreCanal, lista_usuarios, doc)
    if verificacion.status_code != 200:
        return verificacion  # devuelve el error de verificación directamente

    contratobasico.sync_users(lista_usuarios)
    return jsonify({"message": "Usuarios sincronizados correctamente."}), 200

@app.route('/ver_transacciones/<usuario>', methods=['GET'])
def ver_transacciones(usuario):
    global canal
    try:
        transacciones = canal.blockchain.obtener_transacciones_usuario(usuario)
        return jsonify(transacciones), 200
    except Exception as e:
        print(f" Error al obtener transacciones para el usuario {usuario}: {e}")
        return jsonify({"error": "No se pudieron obtener las transacciones."}), 500


#__/__/__/__/__/__/__/__/ Para los bonos de carbono __/__/__/__/__/__/__/__/__/__/

@app.route('/consultar_bono_oraculo', methods=['POST'])
def consultar_bono_oraculo():
    global contratobasico, nodo, canal
    data = request.get_json()
    if not data:
        return jsonify({"error": " No se recibió ningún dato."}), 400
    
    #  Detectar si viene desde otro nodo (con firma)
    if "datos" in data and "firma" in data and "id_nodo_emisor" in data:
        datos_bono = data["datos"]
        firma_b64 = data["firma"]
        id_nodo_emisor = data["id_nodo_emisor"]
    else:
        datos_bono = data["datos"]
        firma_b64 = None
        id_nodo_emisor = data["id_nodo_emisor"]

    for bono in datos_bono:
        serial = bono.get("serial")
        id_usuario = bono.get("_id")

        #  Verificar si este nodo es el creador
        print(f"Nodo emisor: {id_nodo_emisor}, nodo local: {nodo.obtener_id_nodo_local(canal.nombreCanal)} ")
        if id_nodo_emisor == nodo.obtener_id_nodo_local(canal.nombreCanal):
            resultado = oraculo_instance.buscar_bono_por_serial(serial)
            if isinstance(resultado, tuple) or isinstance(resultado, Response):  # Si se devuelve un make_response, lo regresamos directamente
                return resultado
            resultado2 = contratobasico.registrar_bc(resultado, id_usuario, serial)
            if isinstance(resultado2, tuple) or isinstance(resultado2, Response):  # Si se devuelve un make_response, lo regresamos directamente
                return resultado2

            return jsonify(resultado2), 200
        else:
            try:
                firma = base64.b64decode(firma_b64)
            except Exception:
                return jsonify({"message": " Firma invalida."}), 400

            doc = "registro de bono"
            verificacion = nodo.verificar_datos_propagados(
                firma, id_nodo_emisor, canal.nombreCanal, datos_bono, doc
            )
            if verificacion.status_code != 200:
                return verificacion

            resultado = oraculo_instance.buscar_bono_por_serial(serial)
            if isinstance(resultado, tuple) or isinstance(resultado, Response):  # Si se devuelve un make_response, lo regresamos directamente
                return resultado
            resultado2 = contratobasico.registrar_bc(resultado, id_usuario, serial)
            #res3= oraculo_instance.marcar_bono_registrado(serial)
            if isinstance(resultado2, tuple) or isinstance(resultado2, Response):  # Si se devuelve un make_response, lo regresamos directamente
                return resultado2
            
            return jsonify(resultado2), 200
    
@app.route("/bonos_disponibles/<id_usuario>", methods=["GET"])
def bonos_disponibles(id_usuario):
    global canal
    db_bc = Database(db_name=f"{canal.nombreCanal}_bonos")
    bonos = db_bc.find_by_fields({"id_propietario": id_usuario})

    bonos_disponibles = []
    for bono in bonos:
        disponible = Decimal(bono.get("cantidad_disponible", 0))
        if disponible> 0:
            bonos_disponibles.append(bono)

    return jsonify(bonos_disponibles), 200


@app.route("/mis_bonos_disponibles/<id_usuario>", methods=["GET"])
def mis_bonos_disponibles(id_usuario):
    global canal
    db_bc = Database(db_name=f"{canal.nombreCanal}_bonos")

    # Obtener todos los bonos del usuario (registrados o en venta)
    bonos = db_bc.find_by_fields({"id_propietario": id_usuario})

    # Filtrar manualmente los que aún tienen unidades disponibles para vender
    bonos_disponibles = []
    for bono in bonos:
        disponible = Decimal(bono.get("cantidad_disponible", 0))
        if disponible > 0:
            bonos_disponibles.append(bono)

    return jsonify(bonos_disponibles), 200

@app.route("/bonos_en_venta", methods=["GET"])
def bonos_en_venta():
    global canal, contratobasico
    bonos = contratobasico.bonos_en_venta()
    return jsonify(bonos), 200

@app.route("/poner_en_venta", methods=["POST"])
def poner_en_venta():
    global canal, contratocompraventa
    data = request.get_json()

    resultado = contratocompraventa.marcar_en_venta(data)
    return resultado

@app.route("/comprar_bono", methods=["POST"])
def comprar_bono():
    global contratocompraventa
    datos_recibidos = request.get_json()
    print("Datos recibidos en realizar_compra en index:", datos_recibidos)
    resultado = contratocompraventa.realizar_compra(datos_recibidos)
    return resultado

@app.route("/sync_compra", methods=["POST"])
def sync_compra():
    global contratocompraventa
    try:
        data = request.get_json()
        datos = data["datos"]
        firma_b64 = data["firma"]
        firma = base64.b64decode(firma_b64)
        id_nodo_emisor = data["id_nodo_emisor"]
        doc = "Usuarios en compraventa"
        
        verificacion = nodo.verificar_datos_propagados(firma, id_nodo_emisor, canal.nombreCanal, datos, doc)
        if verificacion.status_code != 200:
            return verificacion  # devuelve el error de verificación directamente
        
        for dato in datos:
            comprador = dato.get("comprador")
            vendedor = dato.get("vendedor")
            bono = dato.get("bono")
            bono_resultante = dato.get("bono_resultante")
            contratocompraventa.guardar_informacion_usuarios(comprador, vendedor, bono, bono_resultante)

        return jsonify({"message": " Compra sincronizada correctamente"}), 200

    except Exception as e:
        print(f" Error al sincronizar compra: {e}")
        return jsonify({"error": str(e)}), 500


#__/__/__/__/__/__/__/ BLOQUES __/__/__/__/__/__/__/__/__/__/__/
@app.route("/verificar_integridad", methods=["GET"])
def verificacion_integridad():
    global canal
    gestor_bloques = canal.blockchain
    resultado = gestor_bloques.verificar_integridad_blockchain()
    
    if "" in resultado["message"]:
        return jsonify(resultado), 409  # Conflicto, integridad rota
    else:
        return jsonify(resultado), 200  # Todo correcto

#__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/
# Capturador de señal
def manejar_salida(sig, frame):
    print("\n Interrupción detectada. Cerrando nodo y servidor Flask...")
    os._exit(0)

# Asociar la señal Ctrl+C al manejador
signal.signal(signal.SIGINT, manejar_salida)
if __name__ == "__main__":
    threading.Thread(target=iniciar_servidor).start()
    seleccion_de_canal()