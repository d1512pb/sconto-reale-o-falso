"""Vigila la publicación anual QQP y aísla las nuevas descargas antes del ETL."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.fuentes.qqp_archivo import MAGIA_RAR, _tar
from sconto.intraday import CDMX
from sconto.rutas import DATA, RAW


CATALOGO = 'https://datos.profeco.gob.mx/index.php'
CARPETA = DATA / 'operacion' / 'v2' / 'publicacion_qqp'
MUESTRA = 65536
MAX_BYTES = 250 * 1024 * 1024


class EspacioInsuficiente(OSError):
    """No se puede conservar el candidato respetando la reserva del volumen."""


class EnlaceAnual(HTMLParser):
    def __init__(self, anio):
        super().__init__()
        self.objetivo = f'/docs/qqp/QQP_{anio}.rar'
        self.url = None

    def handle_starttag(self, tag, attrs):
        if tag != 'a' or self.url:
            return
        href = dict(attrs).get('href')
        if not href:
            return
        url = urlsplit(urljoin(CATALOGO, href))
        if (url.scheme == 'https' and url.netloc == 'datos.profeco.gob.mx'
                and url.path == self.objetivo and not url.query and not url.fragment):
            self.url = url.geturl()


def descubrir(html, anio):
    parser = EnlaceAnual(anio)
    parser.feed(html.decode('utf-8', errors='replace') if isinstance(html, bytes) else html)
    return parser.url


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


def _descargar(cliente, url, salida, esperado, reserva_bytes=0):
    limite = min(MAX_BYTES, shutil.disk_usage(salida.parent).free - reserva_bytes)
    if limite <= 0 or (esperado['bytes_remotos'] is not None and esperado['bytes_remotos'] > limite):
        raise EspacioInsuficiente('No hay espacio disponible para conservar un nuevo RAR con la reserva del volumen')
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
                    if total > limite:
                        raise EspacioInsuficiente('El RAR excede el límite disponible de almacenamiento')
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


def _reconocer_version(salida, datos, ahora):
    campos = ('url', 'bytes_remotos', 'huella_inicio', 'etag', 'ultima_modificacion')
    manifiestos = (salida / 'estado.json', *sorted(salida.glob('QQP_*.rar.json'), reverse=True))
    for reporte in manifiestos:
        if not reporte.is_file():
            continue
        anterior = json.loads(reporte.read_bytes())
        archivo = anterior.get('archivo', '')
        patron = r'QQP_\d{4}\.[0-9a-f]{64}\.rar(?:\.rechazado)?'
        if (not re.fullmatch(patron, archivo) or not all(anterior.get(k) == datos[k] for k in campos)
                or not anterior.get('descargado_utc')):
            continue
        candidato = salida / archivo
        if (candidato.is_file() and candidato.stat().st_size == anterior.get('bytes_descargados')
                and ahora - datetime.fromisoformat(anterior['descargado_utc']) < timedelta(days=28)):
            return anterior
    return None


def vigilar(cliente, anio, salida, conocido, ahora, referencia=None, reserva_bytes=0):
    with cliente.get(CATALOGO) as r:
        r.raise_for_status()
        url = descubrir(r.content, anio)
    if not url:
        return dict(estado='sin_publicacion', anio=anio)
    datos = dict(url=url, anio=anio, **huella_remota(cliente, url))
    if conocido.is_file() or referencia:
        largo, inicio = ((conocido.stat().st_size, _huella_local(conocido)) if conocido.is_file()
                         else (referencia['bytes'], referencia['huella_inicio']))
        datos['bytes_preservados'] = largo
        if (datos['bytes_remotos'] is not None and datos['bytes_remotos'] < largo
                and datos['huella_inicio'] == inicio):
            # Una publicación anual más corta con el mismo inicio requiere revisión, no reemplazo.
            return dict(datos, estado='publicacion_mas_corta')
    anterior = _reconocer_version(salida, datos, ahora)
    if anterior:
        return {**anterior, **datos}
    info = _descargar(cliente, url, salida / f'QQP_{anio}.rar', datos, reserva_bytes)
    resultado = dict(datos, **info, descargado_utc=ahora.isoformat())
    if resultado['estado'] == 'candidato_validado':
        registro = salida / f"{info['archivo']}.json"
        if not registro.exists():
            temporal = registro.with_suffix('.tmp')
            temporal.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temporal.replace(registro)
    return resultado


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
