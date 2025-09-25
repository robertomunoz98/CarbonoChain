# script_generar_clave.py

def generar_clave_privada(id_nodo, id_bloque, palabra1, palabra2):
    """
    Genera una clave privada a partir de los elementos dados, usando codificación UTF-8 y hex.
    """
    clave_cruda = f"{id_nodo}{id_bloque}{palabra1}{palabra2}"
    clave_codificada = clave_cruda.encode("utf-8").hex()
    return clave_codificada

if __name__ == "__main__":
    print(" Generador de Clave Privada")
    id_nodo = "9a112054"
    id_bloque = "Yina"
    palabra1 = input(" Ingresa la primera palabra clave: ")
    palabra2 = input(" Ingresa la segunda palabra clave: ")

    clave = generar_clave_privada(id_nodo, id_bloque, palabra1, palabra2)

    print("\n Clave privada generada (hexadecimal):")
    print(clave)
