"""Lectura del contrato del ETL; la web no accede a tiendas ni ejecuta modelos."""
from __future__ import annotations

import hashlib
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pandas as pd
import requests


def verificar(carpeta):
    carpeta = Path(carpeta)
    manifest = json.loads((carpeta / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version') != 'sconto-mart-v1':
        raise ValueError('Versión de datos no compatible')
    if 'sconto_web.sqlite' not in manifest['archivos']:
        raise ValueError('Falta SQLite en el manifiesto')
    for nombre, esperado in manifest['archivos'].items():
        if Path(nombre).name != nombre or '\\' in nombre:
            raise ValueError('Ruta de archivo no permitida')
        if hashlib.sha256((carpeta / nombre).read_bytes()).hexdigest() != esperado:
            raise ValueError(f'Archivo modificado o incompleto: {nombre}')
    return manifest


def descargar(url, destino):
    respuesta = requests.get(url, timeout=180)
    respuesta.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(respuesta.content)) as paquete:
        if sum(info.file_size for info in paquete.infolist()) > 300_000_000:
            raise ValueError('Exportación demasiado grande')
        manifiesto = json.loads(paquete.read('manifest.json'))
        contenidos = {}
        for nombre, esperado in manifiesto['archivos'].items():
            if Path(nombre).name != nombre or '\\' in nombre:
                raise ValueError('Ruta de archivo no permitida')
            contenido = paquete.read(nombre)
            if hashlib.sha256(contenido).hexdigest() != esperado:
                raise ValueError(f'SHA-256 incorrecto: {nombre}')
            contenidos[nombre] = contenido
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in contenidos.items():
        (destino / nombre).write_bytes(contenido)
    (destino / 'manifest.json').write_text(json.dumps(manifiesto, ensure_ascii=False), encoding='utf-8')
    return verificar(destino)


def leer(carpeta, tabla, serie_id=None):
    permitidas = {'productos', 'eventos', 'series', 'precios_diarios', 'referencias_base',
                  'ofertas', 'resultados_modelo', 'evaluacion_modelo', 'calidad_fuentes', 'sensibilidad'}
    if tabla not in permitidas:
        raise ValueError('Tabla no disponible para consultas web')
    ruta = (Path(carpeta) / 'sconto_web.sqlite').resolve()
    with closing(sqlite3.connect(ruta.as_uri() + '?mode=ro', uri=True)) as conexion:
        consulta = f'SELECT * FROM "{tabla}"'
        parametros = ()
        if serie_id is not None:
            if tabla not in {'series', 'precios_diarios', 'referencias_base', 'ofertas', 'resultados_modelo'}:
                raise ValueError('Esta tabla no tiene serie_id')
            consulta += ' WHERE serie_id = ?'
            parametros = (serie_id,)
        return pd.read_sql_query(consulta, conexion, params=parametros)
