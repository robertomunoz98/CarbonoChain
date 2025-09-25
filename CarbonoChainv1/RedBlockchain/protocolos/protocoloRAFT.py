import threading
import time
from colorama import Fore, Style
import requests

class ProtocoloRaft:
    def __init__(self, nodo, canal, nombreCanal):
        self.nodo = nodo
        self.nombreCanal = nombreCanal
        self.canal = canal
        self.lider = None
        self.id_lider = None
        self.enviar_latidos_activo = False
        self.ultimo_latido_recibido = None  #  Guardamos el tiempo del último latido recibido
        self.protocolo_en_reeleccion = False
        self.nombre_protocolo = "raft"

    def iniciar_raft(self):
        """Determina si el nodo debe ser líder y comienza el protocolo."""
        lider_actual = self.consultar_lider_en_red()

        if lider_actual:  
            self.lider = lider_actual
            print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}: 🔹 Nodo {self.nodo.my_address} reconoce que el líder del canal es {self.lider}")
            # Iniciar un hilo que monitoree la caída del líder
            self.monitor_latidos_thread = threading.Thread(target=self.monitor_latidos, daemon=True)
            self.monitor_latidos_thread.start()
        else:  
            self.lider = self.nodo.obtener_id_nodo_local(self.nombreCanal)
            print(f" {self.nodo.obtener_id_nodo_local(self.nombreCanal)} se proclama líder del canal automáticamente porque está solo.")
            print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}: Iniciando envío de latidos...")
            self.iniciar_envio_latidos()

    def consultar_lider_en_red(self):
        """Consulta a los demás nodos en el canal para ver si ya hay un líder activo."""
        nodos_canal = self.canal.listar_nodos_canal(self.nombreCanal)
        
        for nodo in nodos_canal:
            if nodo["_id"] != self.nodo.obtener_id_nodo_local(self.nombreCanal):
                try:
                    response = requests.get(f"http://{nodo['direccion']}/get_lider")
                    if response.status_code == 200:
                        data = response.json()
                        posible_lider = data.get("leader")
                        
                        if posible_lider:
                            # Verificamos si el líder realmente está activo
                            try:
                                posible_lider_ip = self.get_lider_ip(posible_lider)
                                r = requests.get(f"http://{posible_lider_ip}/ping", timeout=3)
                                if r.status_code == 200:
                                    return posible_lider
                                else:
                                    print(f" El nodo {posible_lider} fue reportado como líder pero no respondió al ping.")
                            except requests.RequestException:
                                print(f" El líder reportado ({posible_lider}) no responde. Ignorando...")
                except requests.RequestException:
                    print(f" No se pudo contactar a {nodo['direccion']} para consultar el líder.")
        
        return None

    def iniciar_envio_latidos(self):
        """Comienza a enviar latidos a los demás nodos en el canal."""
        if not self.enviar_latidos_activo:
            print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}:  Iniciando envío de latidos desde {self.nodo.my_address} | id: {self.nodo.obtener_id_nodo_local(self.nombreCanal)}...")
            self.enviar_latidos_activo = True
            thread = threading.Thread(target=self.enviar_latidos, daemon=True)
            thread.start()
        else:
            print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}:  Latidos ya están activos en {self.nodo.my_address} | id: {self.nodo.obtener_id_nodo_local(self.nombreCanal)}.")

    def enviar_latidos(self):
        """Envía latidos a los demás nodos en el canal cada 5 segundos."""
        while self.enviar_latidos_activo:
            nodos = self.canal.listar_nodos_canal(self.nombreCanal)

             #  Filtrar el propio nodo para que no se envíe latidos a sí mismo
            nodos_a_contactar = [nodo for nodo in nodos if nodo["direccion"] != self.nodo.my_address]

            if not nodos_a_contactar:
                print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}:  No hay otros nodos en el canal para enviar latidos.")
            for nodo in nodos_a_contactar:
                try:
                    response = requests.post(f"http://{nodo['direccion']}/latido", json={"sender": self.nodo.obtener_id_nodo_local(self.nombreCanal)})
                    if response.status_code == 200:
                        print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}:  Latido enviado a {nodo['direccion']}")
                    else:
                        print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}:  No se pudo enviar latido a {nodo['direccion']}")
                except requests.RequestException:
                    print(f"{Fore.GREEN}{self.nombreCanal}{Style.RESET_ALL}:  No se pudo enviar latido a {nodo['direccion']}")

            time.sleep(5)  # Esperar antes del siguiente latido

    def puede_crear_bloque(self):
        lider_actual = self.get_lider().strip()  # Eliminamos espacios en blanco
        mi_ip = self.nodo.obtener_id_nodo_local(self.nombreCanal).strip()  # Hacemos lo mismo con la IP local

        #  Depuración avanzada
        print(f"🔍 Comparando líder {lider_actual} ({type(lider_actual)}, len={len(lider_actual)}) "
            f"con nodo actual {mi_ip} ({type(mi_ip)}, len={len(mi_ip)})")
        return lider_actual == mi_ip

    def get_lider(self):
        """Devuelve el líder actual del canal."""
        return self.lider  #  Devuelve el líder guardado en el protocolo
    
    def get_lider_ip(self, id):
        """Devuelve la ip líder actual del canal."""
        lider_ip = self.nodo.obtener_ip_cualquier_nodo(self.nombreCanal, id)
        return lider_ip  #  Devuelve el líder guardado en el protocolo
    
    def recibir_latido(self, sender):
        """Actualiza la marca de tiempo cuando se recibe un latido del líder."""
        
        if self.ultimo_latido_recibido is None or self.ultimo_latido_recibido > time.time():
            print(f" Inconsistencia detectada en `ultimo_latido_recibido`. Reiniciando...")
            self.ultimo_latido_recibido = time.time()  

        tiempo_anterior = self.ultimo_latido_recibido  
        self.ultimo_latido_recibido = time.time()  
        
        tiempo_transcurrido = self.ultimo_latido_recibido - tiempo_anterior

        # 🔹 **Manejo de liderazgo**
        if self.lider != sender:
            print(f" Nuevo líder detectado: {sender}")
            self.lider = sender  

            #  Si este nodo era líder y detecta otro, cede el liderazgo
            if self.nodo.obtener_id_nodo_local(self.nombreCanal) == sender:
                print(" Conflicto detectado: este nodo se proclamó líder, pero hay otro activo. Corrigiendo...")
                self.lider = sender  

        print(f" Latido recibido de {sender} - Última actualización: {self.ultimo_latido_recibido:.2f}")
        print(f" Tiempo transcurrido desde el último latido: {tiempo_transcurrido:.2f} segundos")

    def iniciar_reeleccion(self):
        """Proceso para elegir un nuevo líder si el actual cae."""
        print(f" Iniciando reelección en el canal {self.nombreCanal}...")
        self.lider = self.nodo.obtener_id_nodo_local(self.nombreCanal)  # Se autoproclama líder
        print(f" {self.nodo.obtener_id_nodo_local(self.nombreCanal)} es el nuevo líder.")
        self.iniciar_envio_latidos()  # Empieza a enviar latidos

    def monitor_latidos(self):
        """Monitorea si el líder deja de enviar latidos y activa una reelección solo si es necesario."""
        self.protocolo_en_reeleccion = False  
        fallos_consecutivos = 0  

        while True:
            time.sleep(6)  #  Esperar más de un ciclo de latidos

            if self.ultimo_latido_recibido is None:
                print(" No se ha recibido ningún latido todavía. Esperando...")
                continue  

            if self.lider and self.lider != self.nodo.my_address:
                tiempo_sin_latidos = time.time() - self.ultimo_latido_recibido
                print(f" Último latido recibido hace {tiempo_sin_latidos:.2f} segundos de {self.lider}")

                # Validar si el tiempo tiene sentido
                if tiempo_sin_latidos < 0 or tiempo_sin_latidos > 10000:
                    print(f" Error en la sincronización de tiempos. Reiniciando `ultimo_latido_recibido`...")
                    self.ultimo_latido_recibido = time.time()
                    continue  

                if tiempo_sin_latidos > 10:  
                    fallos_consecutivos += 1  

                    if fallos_consecutivos == 1:  
                        print(f" No se reciben latidos de {self.lider} en {tiempo_sin_latidos:.2f}s, verificando nuevamente...")
                        time.sleep(5)  
                        continue  

                    print(f" {self.lider} no ha respondido en más de 15s, asumiendo que ha caído. Iniciando reelección...")

                    if self.protocolo_en_reeleccion:
                        print(" Reelección ya en proceso, esperando resultados...")
                        time.sleep(5)
                        continue  

                    self.protocolo_en_reeleccion = True  
                    self.lider = None
                    print(f"El lider que tengo es: {self.get_lider()}")

                    #  **Antes de autoproclamarse líder, verificar si otro nodo ya lo hizo**
                    nuevo_lider = self.consultar_lider_en_red()
                    if nuevo_lider:
                        print(f"🔹 {nuevo_lider} ya es líder. Cancelando reelección.")
                        self.lider = nuevo_lider
                    else:
                        self.iniciar_reeleccion()  

                    fallos_consecutivos = 0  
                    self.protocolo_en_reeleccion = False  

                else:
                    fallos_consecutivos = 0  
