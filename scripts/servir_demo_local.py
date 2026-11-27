"""Sirve en local la app v3 y la API del modelo (mismo origen), como en Fly. Uso: python scripts/servir_demo_local.py"""
import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / 'src'), str(RAIZ / 'data/operacion/v2/api_deps')]
DEMO = RAIZ / 'data/operacion/v2/app_v3/demo_local'
CORTE = RAIZ / 'data/operacion/v2/corte_final_20261126/fly'

(DEMO / 'intradia').mkdir(parents=True, exist_ok=True)
for origen, destino in ((CORTE / 'intradia.sqlite3', DEMO / 'intradia/intradia.sqlite3'),
                        (CORTE / 'catalogo.sqlite', DEMO / 'catalogo.sqlite')):
    if not destino.exists():
        shutil.copy2(origen, destino)
os.environ.update(SCONTO_API_DATOS=str(DEMO / 'intradia'), SCONTO_API_CATALOGO=str(DEMO / 'catalogo.sqlite'),
                  SCONTO_API_SITIO=str(RAIZ / 'data/operacion/v2/app_v3/site'),
                  SCONTO_API_MODELO=str(RAIZ / 'data/operacion/v2/app_v3/modelo'),
                  SCONTO_API_DOCS='1', SCONTO_REVISION='demo-local')

import uvicorn  # noqa: E402

uvicorn.run('sconto.api_v2:app', factory=True, host='127.0.0.1', port=int(os.environ.get('PORT', '8787')))
