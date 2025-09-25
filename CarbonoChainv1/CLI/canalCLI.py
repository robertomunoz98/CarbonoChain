import os
import socket
import sys
from colorama import Fore, Style
import requests
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Data.database import Database

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

def verificar_estado_nodo(ip_nodo):
    try:
        response = requests.get(f"http://{ip_nodo}/ping")  # O algún endpoint liviano
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.ConnectionError:
        return False


def obtener_protocolo_canal(ip_nodo):
    try:
        response = requests.get(f"http://{ip_nodo}/canal_activo", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return data["canal"], data["protocolo"]
    except requests.RequestException:
        pass
    return None, None


def menu():
    os.system('clear')
    while True:
        if verificar_estado_nodo(address):
            canal, protocolo = obtener_protocolo_canal("127.0.0.1:5001")
            print(Fore.LIGHTYELLOW_EX + Style.BRIGHT + "\n" + "#"*16 + " Opciones de nodo " + "#"*16 + Style.RESET_ALL)

            if canal:
                print(Fore.YELLOW + f"\n Canal activo: {Style.RESET_ALL}{canal} {Fore.YELLOW}| Protocolo: {Style.RESET_ALL}{protocolo}")
                print(Style.BRIGHT + "\n Opciones disponibles:" + Style.RESET_ALL)
                print("1. Crear canal")
                print("2. Unirse a un canal")
                if protocolo == "RAFT":
                    print("3. Ver líder actual")
                elif protocolo == "POA":
                    print("3. Establecer nueva autoridad")
                print("4. Verificar la integridad de la blockchain")
                print("S. Salir" + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + Style.DIM + "   No hay un canal activo actualmente." + Style.RESET_ALL)
                print(Style.BRIGHT + "\n Opciones generales:" + Style.RESET_ALL)
                print("1. Crear canal")
                print("2. Unirse a un canal")
                print("S. Salir" + Style.RESET_ALL)

            op1 = input(Style.DIM + "Ingrese el # de la opción del menú: " + Style.RESET_ALL)

            if op1 == "1":
                crear_canal_cli()
            elif op1 == "2":
                unirse_canal_cli()
            elif op1 == "3":
                if protocolo == "RAFT":
                    obtener_lider_cli()
                elif protocolo == "POA":
                    establecer_nueva_autoridad()
            elif op1 == "4":
                print("Verificando la integridad de la blockchain...")
                verificar_integridad()
            elif op1.lower() == "s":
                break
            else:
                print(" Opción no válida, intente de nuevo.")
        else:
            print(f" El nodo {address} no está activo.")
            break  # o puedes hacer time.sleep(5) para reintentar en loop si prefieres
    

# FUNCIONES:
def crear_canal_cli():
    """Función interactiva para crear un canal desde CLI"""
    os.system('clear')
    print(Fore.LIGHTYELLOW_EX + Style.BRIGHT + "\n"+"#"*19+ " Crear Canal "+"#"*18+ Style.RESET_ALL)
    nombre = input(Fore.YELLOW +"Ingrese el nombre del canal: "+Style.RESET_ALL)
    print(Fore.YELLOW +"Protocolos disponibles: "+Style.RESET_ALL)
    print(Fore.YELLOW +"1. RAFT. \n2. PoA. "+Style.RESET_ALL)
    op = input(Fore.YELLOW +"Digite el número para el protocolo: "+Style.RESET_ALL)
    if op =="1":
        protocolo = "raft"
    elif op =="2":
        protocolo = "poa"
    clave = input(Fore.YELLOW +"Ingrese una clave para el canal: "+Style.RESET_ALL)

    data = {"nombre": nombre, "clave": clave, "protocolo": protocolo}
    response = requests.post("http://127.0.0.1:5001/crear_canal", json=data)
    
    print(Fore.YELLOW +f"\n "+"="*50+Style.RESET_ALL)
    if response.status_code == 200:
        print(Fore.GREEN +f" Canal '{nombre}' creado exitosamente."+Style.RESET_ALL)
    else:
        print(Fore.RED + f" Error: {response.json().get('error', 'No se pudo crear el canal.')}"+Style.RESET_ALL)
    print(Fore.YELLOW +f"\n "+"="*50+Style.RESET_ALL)

def unirse_canal_cli():
    os.system('clear')
    """Función interactiva para unirse a un canal"""
    print(Fore.LIGHTYELLOW_EX + Style.BRIGHT +"\n"+"#"*16+" Unirse a un canal "+"#"*15+Style.RESET_ALL)
    nodo_conocido = "192.168.1.107:5001"
    print(Fore.YELLOW +f"La ip del nodo conocido es: {Style.RESET_ALL}{nodo_conocido}")
    nombre = input(Fore.YELLOW +"Ingrese el nombre del canal: "+Style.RESET_ALL)
    clave = input(Fore.YELLOW +"Ingrese la clave del canal: "+Style.RESET_ALL)

    data = {"nombreCanal": nombre, "clave": clave, "nodo_conocido": nodo_conocido}
    response = requests.post("http://127.0.0.1:5001/unirse_canal", json=data)
    
    print(Fore.YELLOW +f"\n "+"="*50+Style.RESET_ALL)
    if response.status_code == 200:
        print(Fore.GREEN +f" Nodo unido exitosamente al canal {nombre}."+Style.RESET_ALL)
    else:
        print(Fore.RED +f" Error: {response.json().get('error', 'No se pudo unir al canal.')}"+Style.RESET_ALL)
    print(Fore.YELLOW +f"\n "+"="*50+Style.RESET_ALL)

def obtener_lider_cli():
    """Consulta y muestra el líder actual del canal."""
    url = "http://127.0.0.1:5001/get_lider"  # Asegúrate de que el servidor está corriendo
    try:
        response = requests.get(url)
        print(Fore.YELLOW +f"\n "+"="*50+Style.RESET_ALL)
        if response.status_code == 200:
            data = response.json()
            if "leader" in data and data["leader"] is not None:
                print(Fore.LIGHTCYAN_EX + f"\n El líder actual del canal es: {data['leader']}" + Style.RESET_ALL)
            elif "message" in data:
                print(Fore.LIGHTYELLOW_EX + f"\n {data['message']}" + Style.RESET_ALL)
            else:
                print(Fore.LIGHTYELLOW_EX + "\n No se encontró información de liderazgo." + Style.RESET_ALL)
        else:
            print(Fore.LIGHTRED_EX + f" Error: {response.json().get('error', 'No se pudo obtener el líder')}" + Style.RESET_ALL)

        print(Fore.YELLOW +f"\n "+"="*50+Style.RESET_ALL)
    except requests.RequestException as e:
        print(f" No se pudo conectar al servidor: {e}")

def establecer_nueva_autoridad():
    os.system('clear')
    canal, protocolo = obtener_protocolo_canal("127.0.0.1:5001")
    
    db_nodos = Database(db_name=f"{canal.lower()}_nodos")
    nodos = db_nodos.get_all_docs()
    print(Fore.LIGHTYELLOW_EX + Style.BRIGHT +"\n"+"#"*14+" Establecer Autoridad "+"#"*14+Style.RESET_ALL)
    print(Fore.YELLOW +f"\n Canal activo: {Style.RESET_ALL}{canal} {Fore.YELLOW}| Protocolo: {Style.RESET_ALL}{protocolo}")
    print("\n Lista de nodos disponibles:")
    for idx, nodo in enumerate(nodos, start=1):
        alias = nodo.get("alias", "sin_alias")
        direccion = nodo.get("direccion")
        actual = " (Autoridad)" if nodo.get("es_autoridad") else "(Observador)"
        print(f"   {idx}. {alias} [{direccion}]{actual}")
    print("\n Escribe 'S' para volver.")
    seleccion = input(" Ingrese el número del nodo que desea convertir en autoridad: ").strip()
    
    if seleccion.lower() == "s":
        print(" Volviendo al menú anterior...")
        return  # Sale de la función y regresa al menú
    try:
        nodo_seleccionado = nodos[int(seleccion) - 1]
        alias_seleccionado = nodo_seleccionado["alias"]
        id = nodo_seleccionado["_id"]
        direccion = nodo_seleccionado["direccion"]
        print(f"\nEl nodo seleccionado es el el nodo: {Fore.YELLOW}{alias_seleccionado}{Style.RESET_ALL} | dirección ip: {Fore.YELLOW}{direccion}{Style.RESET_ALL}")
        if nodo_seleccionado["es_autoridad"]:
            print(f" El nodo {Fore.YELLOW}'{alias_seleccionado}'{Style.RESET_ALL} es actualmente AUTORIDAD. Intente nuevamente")
        else:
            response = requests.post(
                f"http://{address}/asignar_autoridad",
                json={"_id": id, "nombreCanal": canal}
            )
            data = response.json() 
            if response.status_code == 200:
                print(f"\n{data['message']}")
                print(" Autoridad asignada exitosamente.")
            else:
                print(f"\n{data['message']}")
                print(" Error al asignar autoridad:", response.json().get("error"))

    except (IndexError, ValueError):
        print(" Selección inválida.")

def verificar_integridad():
    os.system('clear')
    try:
        response = requests.get("http://127.0.0.1:5001/verificar_integridad")
        data = response.json() 
        print("\nnodo 1:")
        if response.status_code == 200:
            print(f"{data['message']}")
        else:
            print(f"{data['message']}")
    except (IndexError, ValueError):
        print(" Problema al intentar verificar la integridad.")

if __name__ == "__main__":
    os.system('clear')
    if len(sys.argv) > 1:
        comando = sys.argv[1]

        if comando == "menu":
            try:
                menu()
            except KeyboardInterrupt:
                print("\n Saliendo del programa...")
        else:
            print(" Comando no reconocido. Usa: python3 cli.py menu")
    else:
        try:
            menu()
        except KeyboardInterrupt:
            print("\n Saliendo del programa...")
