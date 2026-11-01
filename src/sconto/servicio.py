"""Respaldo local sin sobrescribir las particiones de GitHub ni publicar ZIP obsoletos."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from sconto.almacen import _Candado, hoy, registrar_estado, revisar_alertas

REPOSITORIO = 'd1512pb/sconto-reale-o-falso'
FUENTES = ('tiendas', 'mercadolibre', 'preciometro', 'preciometro_ofertas', 'preciometro_productos')
log = logging.getLogger(__name__)


def comando(argumentos, carpeta=None, entorno=None, permitidos=(0,)):
    resultado = subprocess.run([str(valor) for valor in argumentos], cwd=carpeta, env=entorno,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace')
    if resultado.stdout.strip():
        log.info('%s', resultado.stdout.strip()[-4000:])
    if resultado.returncode not in permitidos:
        raise RuntimeError(f'{argumentos[0]} terminó con código {resultado.returncode}; revisar log local')
    return resultado


def sincronizar(copia):
    if not (copia / '.git').exists():
        copia.parent.mkdir(parents=True, exist_ok=True)
        comando(['git', 'clone', '--quiet', '--depth', '1', f'https://github.com/{REPOSITORIO}.git', copia])
    comando(['git', 'config', 'credential.helper', '!gh auth git-credential'], copia)
    comando(['git', 'config', 'user.name', 'sconto-pc'], copia)
    comando(['git', 'config', 'user.email', '93066782+d1512pb@users.noreply.github.com'], copia)
    comando(['git', 'pull', '--quiet', '--rebase'], copia)


def iguales(origen, destino):
    return destino.exists() and hashlib.sha256(origen.read_bytes()).digest() == hashlib.sha256(destino.read_bytes()).digest()


def legado_local(datos):
    marca = datos / 'data/cache/publicaciones_legadas.json'
    if marca.exists():
        return json.loads(marca.read_text(encoding='utf-8'))
    archivos = []
    for fuente in FUENTES:
        crudos = 'preciometro' if fuente.startswith('preciometro') else fuente
        for archivo in (datos / 'data/bronze' / fuente).glob('*.parquet'):
            if len(archivo.stem) == 10 and (datos / 'data/raw' / crudos / archivo.stem).is_dir():
                archivos.append(archivo.relative_to(datos).as_posix())
    marca.parent.mkdir(parents=True, exist_ok=True)
    marca.write_text(json.dumps(sorted(archivos), indent=2), encoding='utf-8')
    return archivos


def sembrar(copia, datos):
    legado_local(datos)
    for carpeta in ('config', 'reports', 'data/bronze', 'data/estado'):
        origen = copia / carpeta
        for archivo in origen.rglob('*'):
            if not archivo.is_file():
                continue
            destino = datos / archivo.relative_to(copia)
            actualizar = carpeta in ('config', 'reports') or archivo.name in ('github.csv', 'ciclo_github.json')
            if actualizar or not destino.exists():
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(archivo, destino)


def copiar_publicables(datos, copia):
    candidatos = [datos / relativa for relativa in legado_local(datos)]
    for fuente in FUENTES:
        candidatos.extend((datos / 'data/bronze' / fuente).glob('*.local.parquet'))
    anio = hoy()[:4]
    for carpeta in (datos / 'data/bronze').glob('qqp_*'):
        if carpeta.name.startswith('qqp_nacional'):
            continue
        candidatos.extend(archivo for archivo in carpeta.iterdir()
                           if archivo.is_file() and archivo.stem in (anio, f'BF{anio}'))
    copiados = []
    for archivo in candidatos:
        if not archivo.exists():
            continue
        relativa = archivo.relative_to(datos)
        destino = copia / relativa
        if '.local.' not in archivo.name:
            if iguales(archivo, destino):
                continue
            destino = destino.with_name(destino.stem + '.local' + destino.suffix)
        if not iguales(archivo, destino):
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archivo, destino)
            copiados.append(destino.relative_to(copia).as_posix())
    for archivo in (datos / 'data/evidencia/preciometro').glob('*/*.json.gz'):
        destino = copia / 'data/evidencia/preciometro/local' / archivo.relative_to(datos / 'data/evidencia/preciometro')
        if not iguales(archivo, destino):
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archivo, destino)
            copiados.append(destino.relative_to(copia).as_posix())
    for nombre in ('local.csv', 'ciclo_local.json'):
        archivo = datos / 'data/estado' / nombre
        if archivo.exists():
            destino = copia / 'data/estado' / nombre
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archivo, destino)
            copiados.append(destino.relative_to(copia).as_posix())
    return copiados


def publicar(datos, copia):
    archivos = copiar_publicables(datos, copia)
    for inicio in range(0, len(archivos), 100):
        comando(['git', 'add', '--', *archivos[inicio:inicio + 100]], copia)
    cambios = comando(['git', 'diff', '--cached', '--quiet'], copia, permitidos=(0, 1))
    if cambios.returncode:
        comando(['git', 'commit', '--quiet', '-m', f'datos: respaldo local aislado {hoy()}'], copia)
    for intento in range(3):
        try:
            comando(['git', 'pull', '--quiet', '--rebase'], copia)
            comando(['git', 'push', '--quiet'], copia)
            break
        except RuntimeError:
            if intento == 2:
                raise
            time.sleep(2 ** intento)
    comando(['gh', 'workflow', 'run', 'recoleccion_diaria.yml', '--repo', REPOSITORIO, '-f', 'max_productos=0'])


def ejecutar(raiz, publicar_datos=False, solo_preparar=False, max_productos=None):
    datos = raiz / 'data/operacion/workspace'
    copia = raiz / 'data/operacion/repo_servicio'
    datos.mkdir(parents=True, exist_ok=True)
    with _Candado(raiz / 'data/operacion/servicio', espera_max=0):
        error_sync = None
        try:
            sincronizar(copia)
            sembrar(copia, datos)
        except RuntimeError as error:
            error_sync = error
            log.error('Sincronización fallida; se conservan y se intentan las capturas locales: %s', error)
        legado_local(datos)
        codigo = copia if error_sync is None else raiz
        entorno = dict(os.environ, SCONTO_RAIZ=str(datos), SCONTO_ENVFILE=str(raiz / '.env'),
                       SCONTO_PARTICION='local', PYTHONPATH=str(codigo / 'src'), PYTHONIOENCODING='utf-8')
        argumentos = [sys.executable, '-m', 'sconto.operacion', '--entorno', 'local']
        if solo_preparar:
            argumentos.append('--solo-preparar')
        else:
            argumentos.append('--qqp-semanal')
            if datetime.now(ZoneInfo('America/Mexico_City')).hour >= 20:
                argumentos.append('--respaldo')
        if max_productos:
            argumentos.extend(['--max-productos', str(max_productos)])
        comando(argumentos, entorno=entorno)
        resultado = json.loads((datos / 'data/estado/ciclo_local.json').read_text(encoding='utf-8'))
        salud_ok = resultado['salud']['ok']
        registrar_estado('servicio_local', 'ok' if salud_ok else 'parcial', 0,
                         detalle='Ciclo local completado; la publicación del ZIP se delega exclusivamente a GitHub', entorno='local')
        revisar_alertas()
        if publicar_datos:
            if error_sync:
                raise error_sync
            publicar(datos, copia)
        return 0 if salud_ok else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', type=Path, required=True)
    parser.add_argument('--publicar', action='store_true')
    parser.add_argument('--solo-preparar', action='store_true')
    parser.add_argument('--max-productos', type=int)
    argumentos = parser.parse_args(argv)
    esperado = argumentos.raiz.resolve() / 'data/operacion/workspace'
    if Path(os.environ.get('SCONTO_RAIZ', '.')).resolve() != esperado:
        parser.error('Ejecutar mediante scripts/correr_local.ps1 para configurar la carpeta operativa')
    if argumentos.max_productos is not None and argumentos.max_productos < 1:
        parser.error('--max-productos debe ser positivo')
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s')
    try:
        return ejecutar(argumentos.raiz.resolve(), argumentos.publicar, argumentos.solo_preparar, argumentos.max_productos)
    except Exception as error:
        log.exception('El servicio conserva sus datos pendientes y requiere revisión')
        registrar_estado('servicio_local', 'fallo', 0, detalle=str(error)[:300], entorno='local')
        revisar_alertas()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
