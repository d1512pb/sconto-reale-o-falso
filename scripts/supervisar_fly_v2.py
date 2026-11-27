"""Ejecuta API y colector en una máquina y propaga el apagado a ambos."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from sconto.presupuesto_fly_v2 import PresupuestoFly


API = (
    '-m', 'uvicorn', 'sconto.api_v2:app', '--factory', '--host', '0.0.0.0',
    '--port', '8080', '--workers', '1', '--no-proxy-headers', '--no-server-header',
    '--limit-concurrency', '32', '--timeout-keep-alive', '5',
)
API_ENV = (
    'PATH', 'LANG', 'LC_ALL', 'PYTHONPATH', 'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE',
    'SCONTO_API_DATOS', 'SCONTO_API_CATALOGO', 'SCONTO_API_ORIGENES',
    'SCONTO_API_PROFECO', 'SCONTO_REVISION',
    'SCONTO_API_SITIO', 'SCONTO_API_MODELO', 'SCONTO_API_DOCS', 'SCONTO_API_MAX_MINUTO',
)
RESPALDO_ENV = (
    'SCONTO_BACKUP_BUCKET', 'SCONTO_BACKUP_ACCESS_KEY_ID',
    'SCONTO_BACKUP_SECRET_ACCESS_KEY', 'SCONTO_BACKUP_AGE_RECIPIENT',
)


def arrancar(argumentos, entorno):
    return subprocess.Popen(
        [sys.executable, *argumentos], env=entorno, user='sconto', group='sconto', extra_groups=[],
        start_new_session=True, stdin=subprocess.DEVNULL, umask=0o077,
    )


def enviar(procesos, senal):
    for _, proceso in procesos:
        try:
            os.killpg(proceso.pid, senal)
        except ProcessLookupError:
            continue


def main():
    raiz = Path(os.environ['SCONTO_API_DATOS'])
    control = PresupuestoFly(raiz.parent) if os.environ.get('SCONTO_CORTE_ESTIMADO') == '1' else None
    if control and not control.continuar():
        print('Apagado preventivo por el control estimado de presupuesto.', file=sys.stderr)
        return 0
    siguiente_medicion = time.monotonic() + 2
    colectar = os.environ.get('SCONTO_COLECTOR_NUBE') == '1'
    if colectar and not all(os.environ.get(nombre) for nombre in RESPALDO_ENV):
        print('El colector requiere configuración de respaldo privado.', file=sys.stderr)
        return 1
    detener = False

    def solicitar_apagado(_senal, _frame):
        nonlocal detener
        detener = True

    signal.signal(signal.SIGTERM, solicitar_apagado)
    signal.signal(signal.SIGINT, solicitar_apagado)
    procesos = []
    entorno_api = {nombre: os.environ[nombre] for nombre in API_ENV if nombre in os.environ}
    entorno_api['SCONTO_API_REVISION_PRIVADA'] = '0'
    try:
        procesos.append(('API', arrancar(API, entorno_api)))
        if colectar:
            comando = ('-m', 'sconto.colector_nube_v2', '--raiz', os.environ['SCONTO_API_DATOS'])
            procesos.append(('colector oficial', arrancar(comando, os.environ.copy())))
        while not detener:
            ahora = time.monotonic()
            if control and ahora >= siguiente_medicion:
                if not control.continuar():
                    print('Apagado preventivo por el control estimado de presupuesto.', file=sys.stderr)
                    return 0
                siguiente_medicion = ahora + 2
            for nombre, proceso in procesos:
                salida = proceso.poll()
                if salida is not None:
                    print(f'Terminó {nombre} con código {salida}.', file=sys.stderr)
                    return 1
            time.sleep(0.25)
        return 0
    finally:
        enviar(procesos, signal.SIGTERM)
        limite = time.monotonic() + 8
        while any(proceso.poll() is None for _, proceso in procesos) and time.monotonic() < limite:
            time.sleep(0.25)
        enviar(procesos, signal.SIGKILL)
        for _, proceso in procesos:
            proceso.wait()


if __name__ == '__main__':
    raise SystemExit(main())
