# Instala las librerias de requirements.txt y deja el resultado en instalar_log.txt
import os
import sys

base = os.path.dirname(os.path.abspath(__file__))
req = os.path.join(base, "requirements.txt")

log = open(os.path.join(base, "instalar_log.txt"), "w")
sys.stdout = log
sys.stderr = log

print("Carpeta:", base)
print("Archivos:", os.listdir(base))
print("Existe requirements.txt:", os.path.exists(req))
print("Python:", sys.version)
print("-" * 40)

try:
    from pip._internal.cli.main import main as pip_main
    codigo = pip_main(["install", "-r", req])
    print("Codigo de salida pip:", codigo)
except Exception as e:
    print("ERROR:", repr(e))

log.close()
