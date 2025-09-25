import base64
import hashlib
import json
import time
from colorama import Fore, Style
import requests
from Data.database import Database

class Blockchain:
    def __init__(self, nodo, canalNombre, canal):
        self.canalNombre = canalNombre.lower()
        self.db = Database(db_name=f"{self.canalNombre}_blockchain")
        self.nodo = nodo
        self.canal = canal
        self.chain = self.get_chain_from_db()
        self.transactions = []


    def get_chain_from_db(self):
        """ Recupera la cadena de bloques desde CouchDB y los ordena por índice. """
        chain = self.db.get_all_docs()
        return sorted(chain, key=lambda x: x['index']) if chain else []

    def agregar_transaccion(self, transaccion):
        """ Agrega una transacción a la lista temporal. """
        self.transactions.append(transaccion)
    
    def bloque_genesis(self, canalNombre):
        db = Database(db_name=f"{canalNombre}_blockchain")
        bloque_genesis = {
            "_id": f"0-bloque_genesis",
            "index": 0,
            "timestamp": time.time(),
            "transactions": [{
                "tipo": "bloque_genesis",
                "mensaje": "Inicio de la cadena de bloques"
            }],
            "previous_hash": "0"
        }
        bloque_genesis["current_hash"] = self.hash(bloque_genesis)
        db.save_doc(bloque_genesis)
        self.chain = self.get_chain_from_db() 


    def crear_bloque(self):
        """ Crea un nuevo bloque y lo almacena en la base de datos. """

        previous_block = self.chain[-1] if self.chain else None
        previous_hash = previous_block["current_hash"] if previous_block else '0'  #  Corrección aquí
        index = previous_block["index"] + 1 if previous_block else 0

        block = {
            "index": index,
            "timestamp": time.time(),
            "transactions": self.transactions,
            "previous_hash": previous_hash
        }
        
        block["current_hash"] = self.hash(block)  #  Ahora calcula el hash del bloque completo
        block["_id"] = f"{block['index']}-{block['current_hash'][:8]}"  #  ID basado en el hash

        self.db.save_doc(block)  #  Guardar el bloque en la base de datos
        self.chain.append(block)  # Agregarlo a la lista de bloques en memoria
        self.transactions = []  #  Limpiar las transacciones en espera

        self.propagar_blockchain(block)  #  Propagar a los demás nodos

    def hash(self, block):
        bloque_copia = dict(block)
        bloque_copia.pop("current_hash", None)  # Muy importante
        bloque_copia.pop("_id", None)  # Opcional, si el _id cambia por bloque
        bloque_copia.pop("_rev", None)  #  Opcional, si estás incluyendo documentos desde CouchDB
        block_string = json.dumps(bloque_copia, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def propagar_blockchain(self, block):
        """ Propaga el nuevo bloque a todos los nodos en el canal. """
        if not self.canal:
            print(" No se puede propagar la blockchain: este nodo no está en ningún canal.")
            return

        nodos_canal = self.canal.listar_nodos_canal(self.canalNombre)

        for nodo in nodos_canal:
            if nodo["direccion"] != self.nodo.my_address:
                try:
                    firma = self.nodo.firma_cod([block], self.canalNombre)
                    response = requests.post(f"http://{nodo['direccion']}/sync_chain", json={"chain": [block], "nombreCanal": self.canalNombre, "protocolo": self.canal.protocolo.nombre_protocolo,"firma": firma, "id_nodo_emisor": self.nodo.obtener_id_nodo_local(self.canalNombre)})
                    data = response.json()
                    print(f"{self.estilo(Fore.LIGHTYELLOW_EX, 'blockchain')}:   {data['message']}" + Style.RESET_ALL)
                    print(f"{self.estilo(Fore.LIGHTYELLOW_EX, 'blockchain')}:  Blockchain propagada a {nodo['direccion']}" + Style.RESET_ALL)
                except requests.RequestException:
                    print(f" No se pudo sincronizar la blockchain con {nodo['direccion']}")

    def verificar_integridad_blockchain(self):
        blockchain = self.db.get_all_docs()
        blockchain = sorted(blockchain, key=lambda b: b['index'])  # Ordena por índice

        for i in range(1, len(blockchain)):
            bloque_anterior = blockchain[i - 1]
            bloque_actual = blockchain[i]

            # Usamos la función hash de la clase
            if bloque_actual['previous_hash'] != self.hash(bloque_anterior):
                return {"message": f" Error de integridad en el bloque {i}: hash previo incorrecto"}

            if self.hash(bloque_actual) != bloque_actual['current_hash']:
                return {"message": f" Error de integridad en el bloque {i}: hash del bloque incorrecto"}

        return {"message": " La cadena es íntegra"}

    def obtener_transacciones_usuario(self, id_usuario):
        blockchain = self.get_chain_from_db()  #  Obtiene toda la blockchain
        transacciones_usuario = []

        for bloque in blockchain:
            transacciones = bloque.get("transactions", [])
            for tx in transacciones:
                if (
                    tx.get("tipo") == "Compraventa" and
                    (tx.get("comprador") == id_usuario or tx.get("vendedor") == id_usuario)
                ):
                    transacciones_usuario.append(tx)

        return transacciones_usuario

    def estilo(self, color, etiqueta):
        return f"{color}{etiqueta}{Style.RESET_ALL}"