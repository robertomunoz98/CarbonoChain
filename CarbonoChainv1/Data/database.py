import couchdb
from couchdb.http import PreconditionFailed

class Database:
    def __init__(self, url='http://admin:admin@localhost:5984/', db_name='blockchain'):
        self.couch = couchdb.Server(url)
        self.db_name = db_name
        
        # Conectar a la base de datos o crearla si no existe
        try:
            if self.db_name in self.couch:
                self.db = self.couch[self.db_name]
            else:
                self.db = self.couch.create(self.db_name)
        except PreconditionFailed:
            self.db = self.couch[self.db_name]

    def save_doc(self, doc):
        """Guarda un documento en la base de datos, manejando conflictos."""
        existing_doc = self.get_doc(doc["_id"])

        if existing_doc:
            doc["_rev"] = existing_doc["_rev"]  # 🔹 Usa la última versión (_rev)
        else:
            if "_rev" in doc:
                del doc["_rev"]  #  Si el doc no existe, eliminamos `_rev` antes de guardar

        try:
            return self.db.save(doc)  # 🔹 Guardar con la versión actualizada
        except couchdb.http.ResourceConflict:
            print(f" Conflicto de actualización en CouchDB para el documento {doc['_id']}. Reintentando...")

            existing_doc = self.get_doc(doc["_id"])  # Obtener la versión actual
            if existing_doc:
                doc["_rev"] = existing_doc["_rev"]
                return self.db.save(doc)  # 🔹 Intentar nuevamente con la versión más reciente

    def get_all_docs(self):
        docs = []
        for doc_id in self.db:
            docs.append(self.db[doc_id])
        return docs

    def get_doc(self, doc_id):
        return self.db.get(doc_id)
    
    def find_by_fields(self, filtros):
        resultados = []
        for doc_id in self.db:
            doc = self.get_doc(doc_id)
            if all(doc.get(k) == v for k, v in filtros.items()):
                resultados.append(doc)
        return resultados