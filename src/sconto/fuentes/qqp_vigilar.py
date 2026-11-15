"""Vigila la publicación anual QQP y aísla las nuevas descargas antes del ETL."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.fuentes.qqp import MAGIA_RAR, _tar
from sconto.intraday import CDMX
from sconto.rutas import DATA, RAW


CATALOGO = 'https://datos.profeco.gob.mx/index.php'
CARPETA = DATA / 'operacion' / 'v2' / 'publicacion_qqp'
MUESTRA = 65536
MAX_BYTES = 250 * 1024 * 1024


def descubrir(html, anio):
    objetivo = f'/docs/qqp/QQP_{anio}.rar'
    for nodo in BeautifulSoup(html, 'html.parser').select('a[href]'):
        url = urlsplit(urljoin(CATALOGO, nodo['href']))
        if (url.scheme == 'https' and url.netloc == 'datos.profeco.gob.mx'
                and url.path == objetivo and not url.query and not url.fragment):
            return url.geturl()
    return None


def huella_remota(cliente, url):
    with cliente.get(url, stream=True, headers={'Range': f'bytes=0-{MUESTRA - 1}', 'Accept-Encoding': 'identity'}) as r:
        r.raise_for_status()
        if r.status_code not in (200, 206):
            raise ValueError(f'HTTP inesperado de QQP: {r.status_code}')
        cuerpo = r.raw.read(MUESTRA)
        if not cuerpo.startswith(MAGIA_RAR):
            raise ValueError('La publicación no empieza con la firma RAR')
        rango = re.fullmatch(r'bytes 0-\d+/(\d+)', r.headers.get('Content-Range', ''))
        largo = r.headers.get('Content-Length', '')
        return dict(bytes_remotos=int(rango[1]) if rango else int(largo) if r.status_code == 200 and largo.isdigit() else None,
                    huella_inicio=hashlib.sha256(cuerpo).hexdigest(), http=r.status_code,
                    etag=r.headers.get('ETag'), ultima_modificacion=r.headers.get('Last-Modified'))


def _huella_local(ruta):
    with ruta.open('rb') as archivo:
        return hashlib.sha256(archivo.read(MUESTRA)).hexdigest()


def _verificar_archivo(ruta):
    listado = subprocess.run([_tar(), '-tf', str(ruta)], capture_output=True, check=True, timeout=150)
    nombres = [nombre for nombre in listado.stdout.decode('utf-8', errors='replace').splitlines()
               if nombre.lower().endswith('.csv')]
    if not 1 <= len(nombres) <= 30:
        raise ValueError('El RAR no contiene una lista anual reconocible de CSV')
    # Se leen los CSV, sin escribir archivos ni pedir a libarchive que descomprima las entradas de directorio.
    subprocess.run([_tar(), '-xOf', str(ruta), '--', *nombres], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                   check=True, timeout=240)
    return len(nombres)


def _descargar(cliente, url, salida, esperado):
    temporal = salida.with_suffix('.part')
    sha = hashlib.sha256()
    total = 0
    try:
        with cliente.get(url, stream=True, headers={'Accept-Encoding': 'identity'}) as r:
            r.raise_for_status()
            if r.status_code != 200:
                raise ValueError('La descarga entera no devolvió HTTP 200')
            with temporal.open('wb') as archivo:
                for parte in r.iter_content(1 << 20):
                    total += len(parte)
                    if total > MAX_BYTES:
                        raise ValueError('Archivo remoto fuera del límite de tamaño')
                    sha.update(parte)
                    archivo.write(parte)
        if esperado['bytes_remotos'] not in (None, total) or _huella_local(temporal) != esperado['huella_inicio']:
            raise ValueError('El contenido completo difiere del tamaño o la huella consultada')
        digest = sha.hexdigest()
        destino = salida.with_name(f'{salida.stem}.{digest}.rar')
        try:
            miembros = _verificar_archivo(temporal)
            estado = 'candidato_validado'
        except (ValueError, subprocess.CalledProcessError):
            miembros, estado = 0, 'ruptura_de_archivo'
            destino = destino.with_suffix('.rar.rechazado')
        if not destino.exists():
            temporal.replace(destino)
        return dict(archivo=destino.name, sha256=digest, bytes_descargados=total, miembros_csv=miembros, estado=estado)
    finally:
        temporal.unlink(missing_ok=True)


def vigilar(cliente, anio, salida, conocido, ahora):
    with cliente.get(CATALOGO) as r:
        r.raise_for_status()
        url = descubrir(r.content, anio)
    if not url:
        return dict(estado='sin_publicacion', anio=anio)
    datos = dict(url=url, anio=anio, **huella_remota(cliente, url))
    if conocido.is_file():
        largo = conocido.stat().st_size
        datos['bytes_preservados'] = largo
        if (datos['bytes_remotos'] is not None and datos['bytes_remotos'] < largo
                and datos['huella_inicio'] == _huella_local(conocido)):
            # Una publicación anual más corta con el mismo inicio requiere revisión, no reemplazo.
            return dict(datos, estado='publicacion_mas_corta')
    reporte = salida / 'estado.json'
    anterior = json.loads(reporte.read_bytes()) if reporte.is_file() else {}
    campos = ('url', 'bytes_remotos', 'huella_inicio', 'etag', 'ultima_modificacion')
    sin_cambios = (anterior.get('sha256') and all(anterior.get(k) == datos[k] for k in campos)
                   and anterior.get('descargado_utc')
                   and ahora - datetime.fromisoformat(anterior['descargado_utc']) < timedelta(days=28))
    if sin_cambios:
        return {**anterior, **datos}
    info = _descargar(cliente, url, salida / f'QQP_{anio}.rar', datos)
    return dict(datos, **info, descargado_utc=ahora.isoformat())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salida', type=Path, default=CARPETA)
    args = parser.parse_args(argv)
    ahora = datetime.now(timezone.utc)
    anio = ahora.astimezone(CDMX).year
    args.salida.mkdir(parents=True, exist_ok=True)
    try:
        datos = vigilar(Cliente(reintentos=0, timeout=(10, 40)), anio, args.salida,
                       RAW / 'qqp' / f'QQP_{anio}.rar', ahora)
    except (Bloqueado, NoPermitido, requests.RequestException, OSError, ValueError, subprocess.SubprocessError) as error:
        datos = dict(estado='fallo_de_verificacion', clase_error=type(error).__name__, anio=anio)
    datos['consultado_utc'] = ahora.isoformat()
    temp = args.salida / 'estado.tmp'
    temp.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(args.salida / 'estado.json')
    alerta = args.salida / 'ALERTA.md'
    if datos['estado'] == 'candidato_validado':
        texto = 'RAR candidato preservado para validar un corte independiente.'
    elif datos['estado'] == 'publicacion_mas_corta':
        texto = (f"El RAR publicado tiene {datos['bytes_remotos']:,} bytes y el mismo inicio que el archivo "
                 f"preservado de {datos['bytes_preservados']:,} bytes. Se conserva el archivo completo.")
    else:
        texto = f"El archivo anual de QQP requiere revisión ({datos['estado']})."
    temp = alerta.with_suffix('.tmp')
    temp.write_text(f"# Vigilancia anual de QQP\n\n{ahora.isoformat()}\n\n{texto}\n", encoding='utf-8')
    temp.replace(alerta)
    print(json.dumps(datos, ensure_ascii=False))
    return 0 if datos['estado'] == 'candidato_validado' else 2


if __name__ == '__main__':
    raise SystemExit(main())
