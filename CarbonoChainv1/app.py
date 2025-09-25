from decimal import Decimal
import socket
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, session


app = Flask(__name__)
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

# Obtén la IP de la máquina local automáticamente
address = obtener_ip_local() + ":5001"



def datos_canal_nodo():
    try:
        response = requests.get("http://localhost:5001/datos_canal")
        if response.status_code == 200:
            datos_canal = response.json()
            nombre_canal = datos_canal.get("nombre_canal")
            protocolo = datos_canal.get("protocolo", "Desconocido").lower()
            id_nodo = datos_canal.get("id_nodo", "Desconocido")
        else:
            nombre_canal = "Desconocido"
            protocolo = "Desconocido"
            id_nodo = "Desconocido"
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener datos del canal: {e}")
        nombre_canal = "Desconocido"
        protocolo = "Desconocido"
        id_nodo = "Desconocido"
    return nombre_canal, protocolo, id_nodo

nombre_canal, protocolo, id_nodo = datos_canal_nodo()


@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    global nombre_canal, protocolo, id_nodo
    if request.method == "POST":
        nombre = request.form.get("nombre")
        _id = request.form.get("_id")
        clave_sesion = request.form.get("clave_sesion")
        rol = request.form.get("rol")
        saldo = request.form.get("saldo")

        usuario = {
            "_id": _id,
            "nombre": nombre,
            "rol": rol,
            "clave_sesion": clave_sesion,
            "nodo_creador_id": id_nodo
        }
        print(f"el id del nodo conocido es: {id_nodo}")
        if rol in ["comprador", "vendedor"] and saldo:
            usuario["saldo"] = str(Decimal(saldo))

        try:
            response = requests.post("http://localhost:5001/registrar_usuario", json=[usuario])
            data = response.json()
            if response.ok:
                if rol in ["comprador", "vendedor"]:
                    mensaje = f"{data['message']}\n Palabras: {', '.join(data['palabras'])}"
                else:
                   mensaje = " Usuario observador registrado éxitosamente." 
            else:
                mensaje = f" {data.get('message', 'Error')}"
        except Exception as e:
            mensaje = f" Error al conectar: {e}"
        flash(mensaje)
        return redirect(url_for("inicio", rol=rol, nombre_canal=nombre_canal, protocolo=protocolo))

    return render_template("registrar.html", rol=None, nombre_canal=nombre_canal, protocolo=protocolo)

app.secret_key = "clave_secreta"  # Necesaria para usar `session` y `flash`

@app.route("/", methods=["GET"])
def inicio():
    global nombre_canal, protocolo, id_nodo
    context = {"nombre_canal": nombre_canal, "protocolo": protocolo}
    return render_template("index.html", **context)

# Diccionario global para guardar intentos fallidos
intentos_fallidos = {}


@app.route("/iniciar_sesion", methods=["POST"])
def iniciar_sesion():
    _id = request.form.get("_id")
    clave = request.form.get("clave_sesion")

    # Si el usuario ya falló 3 veces, bloquear inicio
    if intentos_fallidos.get(_id, 0) >= 3:
        flash("Has excedido el número máximo de intentos. Intenta más tarde.")
        return redirect(url_for("inicio"))

    datos = {"_id": _id, "clave_sesion": clave}

    try:
        response = requests.post("http://localhost:5001/iniciar_sesion", json=datos)
        if response.status_code == 200:
            user_data = response.json()
            session["usuario"] = user_data  # puedes guardar datos en sesión
            
            # Reiniciar el contador de intentos fallidos al iniciar sesión correctamente
            intentos_fallidos[_id] = 0
            return redirect(url_for("dashboard"))  # página posterior al login
        else:
            # Sumar un intento fallido
            intentos_fallidos[_id] = intentos_fallidos.get(_id, 0) + 1
            flash(f"{response.json().get('message', 'Error desconocido')}. Intento {intentos_fallidos[_id]} de 3.")
            return redirect(url_for("inicio"))
    except requests.exceptions.RequestException as e:
        flash(f"Error de conexión: {e}")
        return redirect(url_for("inicio"))

@app.route("/dashboard")
def dashboard():
    usuario = session.get("usuario")
    if not usuario:
        return redirect(url_for("inicio"))
    try:
        response = requests.get(f"http://localhost:5001/obtener_usuario/{usuario['_id']}")
        if response.status_code == 200:
            usuario_actualizado = response.json()
            session["usuario"] = usuario_actualizado  # actualizar sesión con los datos más recientes
            usuario = usuario_actualizado
        else:
            flash(" No se pudieron obtener los datos más recientes del usuario.")
    except requests.exceptions.RequestException as e:
        flash(f" Error al conectar para actualizar el usuario: {e}")
    modo = request.args.get("modo", "bonos_en_venta")  # por defecto se muestran bonos en venta

    context = {
        "usuario": usuario,
        "modo": modo
    }

    if modo == "bonos_en_venta":
        try:
            response = requests.get("http://localhost:5001/bonos_en_venta")
            context["bonos_en_venta"] = response.json()
        except:
            context["bonos_en_venta"] = []
    elif modo == "poner_en_venta":
        try:
            response = requests.get(f"http://localhost:5001/mis_bonos_disponibles/{usuario['_id']}")
            context["mis_bonos_disponibles"] = response.json()
        except:
            context["mis_bonos_disponibles"] = []
    elif modo == "ver_mis_bonos":
        try:
            response = requests.get(f"http://localhost:5001/bonos_disponibles/{usuario['_id']}")
            context["bonos_disponibles"] = response.json()
        except:
            context["bonos_disponibles"] = []
    elif modo == "confirmar_compra":
        bono_id = request.args.get("bono_id")
        try:
            response = requests.get("http://localhost:5001/bonos_en_venta")
            bonos = response.json()
            bono_seleccionado = next((b for b in bonos if str(b["_id"]) == bono_id), None)
            if bono_seleccionado:
                if bono_seleccionado["id_propietario"] == usuario["_id"]:
                    flash(" Ups... no puedes comprar tu propio bono.")
                    return redirect(url_for("dashboard", modo="bonos_en_venta"))
                context["bono"] = bono_seleccionado
            else:
                flash(" Bono no encontrado.")
                return redirect(url_for("dashboard"))
        except:
            flash(" Error al conectar con el servidor.")
            return redirect(url_for("dashboard"))
    elif modo == "ver_transacciones":
        try:
            response = requests.get(f"http://localhost:5001/ver_transacciones/{usuario['_id']}")
            context["transacciones"] = response.json()
            context["usuario_id"] = usuario["_id"] 
        except:
            context["transacciones"] = []
            context["usuario_id"] = usuario["_id"] 
    elif modo == "retirar":
        try:
            response = requests.get(f"http://localhost:5001/mis_bonos_disponibles/{usuario['_id']}")
            context["mis_bonos_disponibles"] = response.json()
        except:
            context["mis_bonos_disponibles"] = []
    
    # para registrar no necesitas datos extra
    try:
        response = requests.get("http://localhost:5001/datos_canal")
        if response.status_code == 200:
            datos_canal = response.json()
            context["nombre_canal"] = datos_canal.get("nombre_canal")
            context["protocolo"] = datos_canal.get("protocolo")
        else:
            context["nombre_canal"] = "Desconocido"
            context["protocolo"] = "Desconocido"
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener datos del canal: {e}")
        context["nombre_canal"] = "Desconocido"
        context["protocolo"] = "Desconocido"
        
    return render_template("sesion_activa.html", **context)

@app.route("/procesar_registro_bono", methods=["POST"])
def procesar_registro_bono():
    global nombre_canal, protocolo, id_nodo
    usuario = session.get("usuario")
    if not usuario:
        flash("Inicia sesión.")
        return redirect(url_for("inicio"))

    serial = request.form.get("serial_bono")
    datos={
        "serial": serial, 
        "_id": usuario["_id"],

    }
    try:
        response = requests.post(
            "http://localhost:5001/consultar_bono_oraculo",
            json={"datos": [datos],"id_nodo_emisor":id_nodo}
        )
        data = response.json()
        flash(data.get("message", "Operación realizada"))

    except requests.exceptions.RequestException as e:
        flash(f"Error de conexión: {e}")

    return redirect(url_for("dashboard"))


@app.route("/registrar_bono")
def registrar_bono():
    return render_template("sesion_activa.html", registrar_bono=True)

@app.route("/procesar_venta", methods=["POST"])
def procesar_venta():
    usuario = session.get("usuario")
    if not usuario:
        flash("Inicia sesión.")
        return redirect(url_for("inicio"))

    bono_id = request.form.get("bono_id")
    precio = str(Decimal(request.form.get("precio")))
    cantidad = str(Decimal(request.form.get("cantidad")))

    payload = {
        "_id": bono_id,
        "precio": precio,
        "cantidad_enVenta": cantidad,
        "id_usuario": usuario["_id"]
    }

    try:
        res = requests.post("http://localhost:5001/poner_en_venta", json=payload)
        flash(res.json().get("message", "Bono puesto en venta"))
    except Exception as e:
        flash(f"Error al poner bono en venta: {e}")

    return redirect(url_for("dashboard"))

@app.route("/bonos_disponibles")
def bonos_disponibles():
    usuario = session.get("usuario")
    if not usuario:
        flash("Debes iniciar sesión para ver esta página.")
        return redirect(url_for("inicio"))

    try:
        print("Voy a enviar la solicitud")
        response = requests.get(f"http://localhost:5001/bonos_disponibles/{usuario['_id']}")
        if response.status_code == 200:
            bonos = response.json()
            return render_template("bonos_disponibles.html", bonos_disponibles=bonos, usuario=usuario)
        else:
            flash("No se pudieron obtener los bonos.")
            return redirect(url_for("dashboard"))
    except requests.exceptions.RequestException as e:
        flash(f"Error al conectar con el backend: {e}")
        return redirect(url_for("dashboard"))

@app.route("/vender_bono", methods=["GET", "POST"])
def vender_bono():
    usuario = session.get("usuario")
    if not usuario or usuario["rol"] != "vendedor":
        flash("Acceso no autorizado.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        bono_id = request.form.get("bono_id")
        cantidad = Decimal(str(request.form.get("cantidad")))
        precio = Decimal(str(request.form.get("precio")))

        payload = {
            "_id": bono_id,
            "precio": precio,
            "cantidad_enVenta": cantidad,
            "id_usuario": usuario["_id"]
        }

        try:
            res = requests.post("http://localhost:5001/poner_en_venta", json=payload)
            flash(res.json().get("message", "Operación completada"))
        except Exception as e:
            flash(f"Error al procesar venta: {e}")

        return redirect(url_for("dashboard"))

    # GET: mostrar bonos disponibles del usuario
    try:
        response = requests.get(f"http://localhost:5001/mis_bonos_disponibles/{usuario['_id']}")
        bonos = response.json()
    except Exception as e:
        bonos = []
        flash(f"Error al obtener bonos: {e}")

    return render_template("vender_bono.html", bonos=bonos, usuario=usuario)

@app.route("/comprar_bono", methods=["POST"])
def comprar_bono():
    usuario = session.get("usuario")
    if not usuario:
        flash("Inicia sesión para comprar bonos.")
        return redirect(url_for("inicio"))

    bono_id = request.form.get("bono_id")
    cantidad = Decimal(request.form.get("cantidad", 0))
    print(f"La cantidad que recibo es: {cantidad}")
    palabra1 = request.form.get("palabra1", "")
    palabra2 = request.form.get("palabra2", "")

    # Validaciones básicas
    if cantidad <= 0 or not palabra1 or not palabra2:
        flash(f"cantidad {cantidad}, palabra 1: {palabra1}, palabra 2: {palabra2}")
        flash(" Verifica los datos ingresados.")
        return redirect(url_for("dashboard"))

    # Lógica real de compra
    datos_compra = {
        "_id": bono_id,
        "id_propietario": usuario["_id"],
        "cantidad": str(cantidad),
    }

    try:
        resp = requests.get(f"http://localhost:5001/obtener_clave_privada/{usuario['_id']}")
        data = resp.json()

        if resp.status_code == 200:
            clave_real = data.get("clave_privada")
            clave_privada_obtenida = f"{usuario['nodo_creador_id']}{usuario['_id']}{palabra1}{palabra2}".encode("utf-8").hex()
            if clave_real == clave_privada_obtenida:
                flash(f" Palabras correctas")
                print("Palabras correctas")
                print("Datos recibidos en realizar_compra:", datos_compra)
                response = requests.post("http://localhost:5001/comprar_bono", json=datos_compra)
                print("Procesado correctas")
                data1 = response.json()

                if response.status_code == 200:
                    flash(f"{data1['message']}")
                else:
                    flash(f" Error: {data1.get('error', 'Ocurrió un problema.')}")
            else:
                flash(f" Palabras incorrectas")
        else:
            flash(f"{data['message']}")
  
    except requests.exceptions.RequestException as e:
        flash(f" Error de conexión: {e}")

    return redirect(url_for("dashboard"))

@app.route("/cambiar_rol", methods=["POST"])
def cambiar_rol():
    usuario = session.get("usuario")
    try:
        nuevo_rol = request.form.get("nuevo_rol")
        saldo = str(Decimal(request.form.get("saldo")))

        response = requests.post(
            "http://localhost:5001/cambiar_rol",
            json={
                "_id": usuario["_id"],
                "saldo_inicial": saldo,
                "nuevo_rol": nuevo_rol
            }
        )
        data = response.json()
        if response.status_code ==200:
            mensaje = f"{data['message']}\n🔑 Palabras: {', '.join(data['palabras'])}"
            flash(mensaje)
        return redirect(url_for("dashboard"))
    except Exception as e:
        flash(mensaje)
        return redirect(url_for("dashboard"))

@app.route("/cerrar_sesion", methods=["POST"])
def cerrar_sesion():
    session.clear()
    return redirect(url_for("inicio"))

# __/__/ Funciones
def obtener_id_nodo():
    try:
        response1 = requests.post("http://localhost:5001/nodo_id")
        if response1.status_code == 200:
            data = response1.json()
            id_nodo = data['nodo_id']
            return id_nodo
        else:
            print(f" No se pudo obtener el Id del Nodo")
            return None
    except requests.exceptions.RequestException as e:
        print(f" No se pudo obtener el Id del Nodo: {e}")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
