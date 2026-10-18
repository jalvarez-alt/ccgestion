import os
import sys

# Asegura que Python encuentre los archivos de la app
sys.path.insert(0, os.path.dirname(__file__))

from app import app as application
