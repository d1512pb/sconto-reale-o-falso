"""Rutas del proyecto. Todo con pathlib: la carpeta "Mineria  de datos" tiene DOS espacios."""
from pathlib import Path
import os

RAIZ = Path(os.environ.get('SCONTO_RAIZ', Path(__file__).resolve().parents[2]))
CONFIG = RAIZ / 'config'
DATA = RAIZ / 'data'
RAW = DATA / 'raw'
BRONZE = DATA / 'bronze'
SILVER = DATA / 'silver'
GOLD = DATA / 'gold'
CACHE = DATA / 'cache'
LOGS = RAIZ / 'logs'
REPORTS = RAIZ / 'reports'
ESTADO_FUENTES = DATA / 'estado_fuentes.csv'  # vista combinada
ESTADO_DIR = DATA / 'estado'  # un archivo por entorno (github, local)
ALERTA = RAIZ / 'ALERTA.md'

# Evidencia del Avance 1: solo lectura. Nunca se escribe ahí.
SCONTO = RAIZ.parent
AVANCE1 = SCONTO / 'resultados_anuales_2025'
QQP_2025_RAR = SCONTO / 'datos_originales' / 'QQP_2025.rar'


def asegurar_directorios():
    for p in (RAW, BRONZE, SILVER, GOLD, CACHE, LOGS, REPORTS):
        p.mkdir(parents=True, exist_ok=True)
