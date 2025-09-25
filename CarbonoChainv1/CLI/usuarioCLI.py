import os
import socket
import sys
import textwrap
from colorama import Fore, Style
import requests
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Data.database import Database


# __/__/__/__/__/__/__/__/Propio del CLI __/__/__/__/__/__/__/__/
#Estilo
ESTILO_COLOR = Fore.WHITE
RS = Style.RESET_ALL
#Para inicio de sesion activo 
USUARIO_ACTIVO = {}

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
try:
    response1 = requests.post("http://localhost:5000/nodo_id")
    if response1.status_code == 200:
        data = response1.json()
        id_nodo = data['nodo_id']
    else:
        print(" Error al obtener el ID del nodo")
except requests.exceptions.RequestException as e:
    print(f" No se pudo obtener el Id del Nodo: {e}")

def establecer_estilo_por_protocolo(protocolo):
    global ESTILO_COLOR
    if protocolo == "raft":
        ESTILO_COLOR = Fore.GREEN
    elif protocolo == "poa":
        ESTILO_COLOR = Fore.YELLOW
    else:
        ESTILO_COLOR = Fore.WHITE

def mostrar_encabezado_sesion():
    global USUARIO_ACTIVO
    id = USUARIO_ACTIVO.get("_id")
    obtener_usuario(id)
    canal = USUARIO_ACTIVO.get("nombreCanal", "Canal")
    nombre = USUARIO_ACTIVO.get("nombre", "")
    rol = USUARIO_ACTIVO.get("rol", "")
    bonos = USUARIO_ACTIVO.get("cant_bonos", 0)
    saldo = USUARIO_ACTIVO.get("saldo", 0)

    print(ESTILO_COLOR + "\n " + "=" * 50 + RS)
    print(ESTILO_COLOR + " " * 22 + f"{Style.BRIGHT}{canal}{RS}{ESTILO_COLOR}")
    print(ESTILO_COLOR + " " + "=" * 50 + RS)
    print(f"{Style.DIM}   Bienvenido, {RS}{nombre}")
    print(f"{Style.DIM}   Rol: {RS}{rol}")
    if rol != "observador":
        print(f"{Style.DIM}   Saldo: {RS}{saldo}")
    print(f"{Style.DIM}   Mis bonos de carbono disponibles: {RS}{bonos}")
    print(ESTILO_COLOR + " " + "=" * 50 + RS)
   
def obtener_usuario(id):
    try:
        response = requests.get(f"http://localhost:5001/obtener_usuario/{id}")
        if response.status_code == 200:
            return response.json()
        else:
            print(" No se pudo obtener la información actualizada del usuario.")
            return None
    except requests.exceptions.RequestException as e:
        print(f" Error de conexión al obtener usuario: {e}")
        return None

def menu():
    while True:
        print(Fore.LIGHTBLUE_EX + Style.BRIGHT +"\n"+"#"*15+" Opciones de usuario "+"#"*14+ Style.RESET_ALL)
        print("1 . Registrarse")
        print("2 . Ingresar")
        print("S . Salir")

        op1 = input(Style.DIM+ "Ingrese el valor correspondiente: "+ Style.RESET_ALL)

        if op1 == "1":
            os.system('clear')
            registrar_usuario_cli()
        elif op1 == "2":
            os.system('clear')
            inicio_usuario_cli()
        elif op1.lower() == "s":
            print(Fore.BLUE + "Saliendo..."+ Style.RESET_ALL)
            break
        else:
            print(" Opción no válida, intente de nuevo.")

# __/__/__/__/__/__/__/__/ FUNCIONES __/__/__/__/__/__/__/__/
def registrar_usuario_cli():
    try:
        print(Fore.LIGHTMAGENTA_EX + Style.BRIGHT + "\n"+"#"*15+" Registro de Usuario "+"#"*14+ RS)
        nombre = input(Fore.CYAN + " Nombre: " + RS)
        id = input(Fore.CYAN +" Ingrese su identificación: "+ RS)
        clave_sesion = input(Fore.CYAN +" Ingrese una clave para inicio de sesion: "+ RS)
        print(Fore.CYAN +"¿Que rol quieres ser:"+ RS)
        print("  1. Observador (Solo visualiza el mercado)")
        print("  2. Comprador (Puede comprar bonos)")
        print("  3. Vendedor (Debe registrar bonos certificados)")
        rol = input(Style.DIM+ "Ingrese el número correspondiente: "+ RS)
        
        if rol == "1":
            usuario = {"_id": id, "nombre": nombre, "rol": "observador", "clave_sesion": clave_sesion, "nodo_creador_id": id_nodo}
        elif rol == "2":
            saldo_inicial = float(input(Fore.CYAN +" Ingrese su saldo: "+ Style.RESET_ALL))
            usuario = {"_id": id, "nombre": nombre, "rol": "comprador", "saldo": saldo_inicial, "clave_sesion": clave_sesion, "nodo_creador_id": id_nodo}
        elif rol == "3":
            saldo_inicial = float(input(Fore.CYAN +" Ingrese su saldo: "+ Style.RESET_ALL))
            usuario = {"_id": id, "nombre": nombre,"rol": "vendedor",  "saldo": saldo_inicial, "clave_sesion": clave_sesion, "nodo_creador_id": id_nodo}
            print("Recuerda iniciar sesión para agregar tus bonos de carbono.")
        else:
            print(Fore.RED +"Opción inválida."+ Style.RESET_ALL)
            return
    except KeyboardInterrupt:
        print("\nRegresando al menú principal...")
        return
    
    try:
        response = requests.post("http://localhost:5001/registrar_usuario", json=usuario)
        data = response.json()  # Convertir respuesta JSON a diccionario
        
        if response.status_code == 200:
            print(Fore.LIGHTMAGENTA_EX +f"\n "+"="*50+Style.RESET_ALL+"\n")
            print(f" {data['message']}")
            print(f" Palabras de seguridad: {Style.BRIGHT+Fore.LIGHTCYAN_EX}{', '.join(data['palabras'])}{Style.RESET_ALL}")  # Muestra palabras generadas
            mensaje = " NOTA: Guarda estas palabras de seguridad porque no se podrán visualizar después."
            mensaje_justificado = textwrap.fill(mensaje, width=50)
            print(Fore.RED + mensaje_justificado[:8] + Fore.YELLOW + mensaje_justificado[8:] + Style.RESET_ALL)
            print(Fore.LIGHTMAGENTA_EX +f"\n "+"="*50+Style.RESET_ALL)
            while True:
                op = input(Style.DIM+ "\n Escriba S para salir al menú principal: "+ Style.RESET_ALL)
                if op.lower() == "s":
                    os.system('clear')
                    break
        else:
            print(f"{data['message']}")
            print(f" Error: {data.get('error', 'Ocurrió un problema.')}")
    except requests.exceptions.RequestException as e:
        print(f" Error de conexión: {e}")

def inicio_usuario_cli():
    global USUARIO_ACTIVO
    print(Fore.YELLOW + Style.BRIGHT + "\n"+"#"*16+" Inicio de sesion "+"#"*16+ Style.RESET_ALL)
    id = input(Fore.CYAN +"\n🆔 Ingrese su identificación: "+ Style.RESET_ALL)
    clave_sesion = input(Fore.CYAN +" Ingrese su clave: "+ Style.RESET_ALL)

    usuario = {"_id": id, "clave_sesion": clave_sesion}
    try:
        response = requests.post("http://localhost:5001/iniciar_sesion", json=usuario)
        user_data = response.json()
        if response.status_code == 200:
            os.system('clear')
            user_data = response.json()
            rol = user_data.get("rol")
            nombreCanal = user_data.get("nombreCanal")
            USUARIO_ACTIVO = user_data  #  Guarda todo el usuario para reutilizarlo

            establecer_estilo_por_protocolo(user_data.get("protocolo"))
            mostrar_encabezado_sesion()
            # Menú de sesión activa
            while True:
                mostrar_bonos_en_venta(nombreCanal)
                print(ESTILO_COLOR +f"\n "+"="*50+RS)
                print(Fore.CYAN+"\n   Menú de sesión activa:"+Style.RESET_ALL)
                if rol == "observador":
                    print("     1. Cambiar de rol para comprar bonos")
                elif rol == "comprador":
                    print("     1. Ver mis bonos de carbono")
                    print("     2. Comprar bonos de carbono")
                    print("     3. Vender bonos de carbono")
                elif rol == "vendedor":
                    print("     1. Ver mis bonos de carbono")
                    print("     2. Comprar bonos de carbono")
                    print("     3. Poner a la venta bonos de carbono")
                    print("     4. Registrar un bono de carbono")
                print("     S. Salir de sesión")

                opcion = input(Style.DIM+ "   Ingrese el valor correspondiente: "+ RS)

                if opcion == "1":
                    print("1. Esta opcion aun no esta disponible")
                elif opcion == "2":
                    comprar(id, nombreCanal)
                    menu_inicio()
                elif opcion == "3":
                    vender_bc(id)
                    menu_inicio()
                elif opcion == "4":
                    print(ESTILO_COLOR +f"\n "+"="*50+RS)
                    registrar_bc(id)
                    menu_inicio()
                elif opcion.lower() == "s":
                    print(Fore.GREEN +f"\n "+"="*50+RS)
                    print(Fore.BLUE + "🚪 Sesión cerrada. Volviendo al menú principal..."+ RS)
                    os.system('clear')
                    break
                else:
                    print(" Opción no válida. Intenta de nuevo.")
        else:
            print(f"{user_data['message']}")
    except requests.exceptions.RequestException as e:
        print(f" Error de conexión: {e}")

def vender_bc(usuario_id):
    os.system('clear')
    mostrar_encabezado_sesion()
    print(ESTILO_COLOR + "\n Bonos de carbono disponibles para vender:" + RS)

    try:
        response = requests.get(f"http://localhost:5001/bonos_disponibles/{usuario_id}")
        bonos = response.json()

        if not bonos:
            print(" No tienes bonos disponibles para vender.")
            return

        for idx, bono in enumerate(bonos):
            print(f"{idx+1}. Id: {bono['_id']} | Disponibles: {bono['cantidad_total']}")

        opcion = int(input(Fore.CYAN + "\n   Seleccione el número del bono a vender: " + RS)) - 1
        cantidad = float(input(Fore.CYAN + "   La cantidad de bonos que desea poner en venta: " + RS))
        precio = float(input(Fore.CYAN + "    Ingrese el precio de venta (por bono): " + RS))
        id = bonos[opcion]['_id']

        payload = {"_id": id, "precio": precio, "cantidad_enVenta": cantidad, "id_usuario": usuario_id}
        res = requests.post("http://localhost:5001/poner_en_venta", json=payload)
        
        os.system('clear')
        print(res.json().get("message", "    Operación completada."))

    except Exception as e:
        print(f" Error al procesar venta: {e}")

def imprimir_bonos_en_venta(bonos, numerar=False):
    if not bonos:
        print(" No hay bonos de carbono en venta actualmente.\n")
        return

    print(Fore.CYAN + "\n  🌱 Bonos de Carbono en Venta:" + Style.RESET_ALL)

    print(" "+"-" * 50)

    for i, bono in enumerate(bonos, 1):
        encabezado = f"{i}. " if numerar else "   "
        print(f"{encabezado} Id Bono de carbono: {bono.get('_id')}")
        print(f"     Proyecto: {bono.get('proyecto_id')}")
        print(f"     Cantidad en venta: {bono.get('cantidad_enventa')}")
        print(f"     Precio: {bono.get('precio')}")
        print(f"     Vendedor ID: {bono.get('id_propietario')}")
        print(" "+"-" * 50)
def menu_inicio():
    usuario_actualizado = obtener_usuario(id)
    if usuario_actualizado:
        USUARIO_ACTIVO.update(usuario_actualizado)  # Actualiza los datos locales del usuario
    mostrar_encabezado_sesion()
    return
def mostrar_bonos_en_venta(nombre_canal):
    db = Database(db_name=f"{nombre_canal}_bonos")
    bonos = db.find_by_fields({"estado": "en_venta"})
    imprimir_bonos_en_venta(bonos, numerar=False)

def mostrar_bonos_para_compra(nombre_canal):
    db = Database(db_name=f"{nombre_canal}_bonos")
    bonos = db.find_by_fields({"estado": "en_venta"})
    imprimir_bonos_en_venta(bonos, numerar=True)
    return bonos
 
def comprar(id, nombreCanal):
    os.system('clear')
    mostrar_encabezado_sesion()
    bonos_disponibles = mostrar_bonos_para_compra(nombreCanal)
    print(ESTILO_COLOR +f"\n "+"="*50+RS)
    if not bonos_disponibles:
        input("🔙 Presione Enter para volver al menú...")
        return

    try:
        print(ESTILO_COLOR + "\n Digite el número del bono de carbono a comprar:" + RS)
        num = int(input(" Número: "))
        
        bono_seleccionado = bonos_disponibles[num - 1]
        cantidad_disponible = bono_seleccionado.get("cantidad_enventa", 0)
        if num < 1 or num > cantidad_disponible:
            print(" Número fuera de rango.")
            return
        
        print(f"\n Seleccionaste el bono con serial: {bono_seleccionado['_id']}")
        

        print(f"📦 Cantidad disponible para compra: {cantidad_disponible}")
        cantidad_deseada = int(input(" ¿Cuántos bonos desea comprar?: "))
        
        if cantidad_deseada < 1 or cantidad_deseada > cantidad_disponible:
            print(" Cantidad no válida.")
            return

        datos = {"id_bono": bono_seleccionado['_id'], "id_comprador":id, "cantidad": cantidad_deseada, "canal": nombreCanal}
        try:
            response = requests.post("http://localhost:5001/comprar_bono", json=datos)
            data = response.json()  # Convertir respuesta JSON a diccionario
            
            if response.status_code == 200:
                print(Fore.LIGHTMAGENTA_EX +f"\n "+"="*50+Style.RESET_ALL+"\n")
                print(f" {data['message']}")
                print(Fore.LIGHTMAGENTA_EX +f"\n "+"="*50+Style.RESET_ALL)
                while True:
                    op = input(Style.DIM+ "\n Escriba S para salir al menú principal: "+ Style.RESET_ALL)
                    if op.lower() == "s":
                        os.system('clear')
                        break
            else:
                print(f"{data['message']}")
                print(f" Error: {data.get('error', 'Ocurrió un problema.')}")
        except requests.exceptions.RequestException as e:
            print(f" Error de conexión: {e}")

        os.system('clear')
        print(f" Compra de {cantidad_deseada} bonos realizada con éxito.")

    except ValueError:
        print(" Entrada no válida. Intente de nuevo.")

def registrar_bc(id):
    os.system('clear')
    mostrar_encabezado_sesion()
    codigo_bc = input(Fore.CYAN +"   Ingrese el serial del bono de carbono:\n    "+ RS)
    try:
        response = requests.post("http://localhost:5001/consultar_bono_oraculo", json={"serial": codigo_bc, "_id": id})
        data = response.json()  # Convertir respuesta JSON a diccionario
        if response.status_code == 200:
            os.system('clear')
            print(f" {data['message']}")
            print(f"El serial {codigo_bc} sera agregado a su cuenta")
        else:
            os.system('clear')
            print(f" {data['message']}")
    except requests.exceptions.RequestException as e:
        print(f" Error de conexión: {e}")

#__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/__/
if __name__ == "__main__":
    if len(sys.argv) > 1:
        comando = sys.argv[1]

        if comando == "menu":
            menu()
        else:
            print(" Comando no reconocido. Usa: python3 cli.py menu")
    else:
        menu()
