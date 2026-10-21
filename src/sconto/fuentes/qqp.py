"""PROFECO «Quién es Quién en los Precios» (QQP): archivos anuales oficiales (RAR con CSV quincenales).

Reutiliza la lógica validada del Avance 1 (../crear_notebook_01.py), sin reinventarla:
- se leen TODOS los CSV del RAR por bloques con tar.exe (Windows) o bsdtar (Linux), sin extraer a disco
  (2024–2026 traen cabecera; 2018–2023 no, con las mismas 15 columnas en el mismo orden);
- recorte CDMX + APARATOS ELECTRONICOS con `normalizar`; aparte, la tabla NACIONAL de la misma categoría;
- identidad provisional con `id_estable`: producto_id (producto+marca+presentación), sucursal_id
  (cadena+nombre comercial+dirección+municipio) y serie_id (producto_id+sucursal_id);
- depuración en cascada inválidos → repeticiones → conflictos → limpias: toda fila cruda termina en una;
  fecha inválida si no parsea o si su año no es el del archivo;
- ventanas del Buen Fin relativas a D0 (config/eventos.yaml) y coberturas de ahorro / alza.

Descarga: qqp.php lista 2024–2026; 2015–2023 ya no aparecen, pero sus enlaces file.php?t=... (recuperados de
capturas de qqp.php en Wayback Machine) siguen sirviendo el RAR oficial desde datos.profeco.gob.mx.
QQP 2025 se lee del RAR del Avance 1 (../datos_originales, sólo lectura, SHA-256 verificado).

Tablas (data/bronze/):
- qqp_cdmx/<anio>.parquet, qqp_nacional/<anio>.parquet: observaciones limpias en el esquema común.
  CLAVE única: id_externo = producto_id del Avance 1 y vendedor_o_cadena = 'CADENA | NOMBRE COMERCIAL | sucursal_id'
  (cadena + nombre comercial no basta: hay sucursales homónimas con distinta dirección o municipio).
- qqp_cdmx_exclusiones/<anio>.parquet, qqp_nacional_exclusiones/<anio>.parquet: inválidos, repeticiones y conflictos.
- qqp_cdmx_series/<evento>.parquet, qqp_nacional_series/<evento>.parquet: variables por serie (06 del Avance 1).
- qqp_cdmx_matriz/<evento>.parquet: matriz de 3 variables de las series con cobertura de alza (07 del Avance 1).
- qqp_auditoria/<anio>.parquet (filas por CSV) y qqp_resumen/<anio>.json.

Uso:
    python -m sconto.fuentes.qqp enlaces
    python -m sconto.fuentes.qqp backfill --anios 2018 2019 2020 2021 2022 2023 2024 2025 2026
    python -m sconto.fuentes.qqp reproduccion    # compara el bronze 2025 con el Avance 1
    python -m sconto.fuentes.qqp diario
    python -m sconto.fuentes.qqp historicos      # busca 2018–2023 en PROFECO y espejos gratuitos
    python -m sconto.fuentes.qqp reporte
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from sconto.almacen import (ahora_utc, escribir_bronze, escribir_manifiesto, guardar_crudo, hoy, leer_crudo,
                            registrar_estado, revisar_alertas, sha256_archivo)
from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.esquema import CLAVE, a_dataframe
from sconto.eventos import cargar_eventos
from sconto.normalizar import ESTADOS_CDMX, id_estable, modelo_qqp, normalizar
from sconto.rutas import AVANCE1, BRONZE, LOGS, QQP_2025_RAR, RAIZ, RAW, REPORTS, asegurar_directorios

log = logging.getLogger('qqp')

FUENTE = 'qqp'
FUENTE_CDMX, FUENTE_NACIONAL = 'qqp_cdmx', 'qqp_nacional'
PAGINA = 'https://datos.profeco.gob.mx/datos_abiertos/qqp.php'
DICCIONARIO = 'https://datos.profeco.gob.mx/diccionarioDatosQQP.php'
URL_2025 = 'https://datos.profeco.gob.mx/datos_abiertos/file.php?t=b9540b181657c2bc7735892091e81f96'
SHA256_2025 = '41ca4cd962e696f9f19cca598566d11ce60b200e37b5a5ef46c3b6a1ae58dc59'
CARPETA = RAW / FUENTE
CATEGORIA = 'APARATOS ELECTRONICOS'
REQUERIDAS = {'producto', 'presentacion', 'marca', 'categoria', 'catalogo', 'precio', 'fecha_registro',
              'cadena_comercial', 'giro', 'nombre_comercial', 'direccion', 'estado', 'municipio', 'latitud', 'longitud'}
ORIGINALES = ['producto', 'presentacion', 'marca', 'categoria', 'catalogo', 'precio', 'fecha_registro',
              'cadena_comercial', 'giro', 'nombre_comercial', 'direccion', 'estado', 'municipio', 'latitud', 'longitud']
COLS_PRODUCTO = ['producto', 'marca', 'presentacion']
COLS_SUCURSAL = ['cadena_comercial', 'nombre_comercial', 'direccion', 'municipio']
CLAVE_SERIE = ['serie_id', 'fecha']
BLOQUE = 150_000
TIPO_PRECIO = 'precio_registrado_qqp'
MAGIA_RAR = b'Rar!\x1a\x07'
ANIOS_HISTORICOS = range(2018, 2024)  # ya no listados en qqp.php, pero el servidor oficial aún los sirve
WAYBACK_CDX = ('https://web.archive.org/cdx/search/cdx?url=datos.profeco.gob.mx/datos_abiertos/qqp.php'
               '&output=json&filter=statuscode:200&collapse=digest')

# Fechas del Buen Fin que aún no están en config/eventos.yaml (el orquestador las pasará allá). Se usan sólo si
# eventos.yaml no trae el evento de ese año. Fuente: prensa que cita el anuncio de la Secretaría de Economía.
EVENTOS_HISTORICOS = {
    2018: ('BF2018', '2018-11-16', '2018-11-19',
           'https://www.excelsior.com.mx/nacional/dan-a-conocer-las-fechas-de-el-buen-fin-2018/1269716'),
    2019: ('BF2019', '2019-11-15', '2019-11-18',
           'https://www.xataka.com.mx/comercio-electronico/buen-fin-2019-se-realizara-mexico-15-al-18-noviembre'),
    2020: ('BF2020', '2020-11-09', '2020-11-20',
           'https://expansion.mx/economia/2020/09/08/buen-fin-2020-durara-12-dias-para-evitar-aglomeraciones'),
    2021: ('BF2021', '2021-11-10', '2021-11-16',
           'https://expansion.mx/finanzas-personales/2021/10/25/cuando-es-el-buen-fin-2021-mexico'),
    2022: ('BF2022', '2022-11-18', '2022-11-21',
           'https://vanguardia.com.mx/noticias/llega-el-buen-fin-2022-estas-son-las-fechas-oficiales-seran-4-dias-de-ofertas-AH3867121'),
    2023: ('BF2023', '2023-11-17', '2023-11-20',
           'https://www.nmas.com.mx/economia/buen-fin-mexico-2023-tiene-fecha-empresas-ya-pueden-registrarse/'),
}


# ---------------------------------------------------------------------------------------------- descarga

def descubrir_enlaces(html: str | bytes, base: str = PAGINA) -> dict:
    """Enlaces file.php?t=... de la página de datos abiertos: {'anios': {2025: url}, 'otros': {texto: url}}."""
    soup = BeautifulSoup(html, 'html.parser')
    anios, otros = {}, {}
    for a in soup.find_all('a', href=True):
        if 'file.php?t=' not in a['href']:
            continue
        texto = ' '.join(a.get_text().split())
        url = urljoin(base, a['href'])
        m = re.search(r'\b((?:19|20)\d{2})\b', texto)
        if m and 'precios' in texto.lower():
            anios[int(m.group(1))] = url
        else:
            otros[texto] = url
    return {'anios': dict(sorted(anios.items())), 'otros': otros}


def leer_pagina(cliente: Cliente | None = None) -> tuple[dict, str]:
    """Descarga la página oficial (se guarda cruda) y devuelve (enlaces, ruta_raw)."""
    cliente = cliente or Cliente()
    r = cliente.get(PAGINA)
    r.raise_for_status()
    ruta_raw, _ = guardar_crudo(FUENTE, 'qqp.php.html', r.content)
    return descubrir_enlaces(r.content), ruta_raw


_WAYBACK: dict | None = None  # una consulta al CDX por proceso


def enlaces_wayback(cliente: Cliente | None = None) -> dict:
    """Años que qqp.php ya no lista (2015–2023) pero que el servidor de PROFECO sigue sirviendo: los tokens
    file.php?t=... se recuperan de las capturas de qqp.php en Wayback Machine (gana la captura más reciente que
    lista cada año). Las capturas quedan en data/raw/qqp/wayback/ y no se vuelven a pedir."""
    global _WAYBACK
    if _WAYBACK is not None:
        return _WAYBACK
    cliente = cliente or Cliente(pausa=(1.5, 3.0))
    r = cliente.get(WAYBACK_CDX)
    r.raise_for_status()
    guardar_crudo(FUENTE, 'cdx_qqp_php.json', r.content, fecha='wayback')
    capturas = sorted({f[1] for f in r.json()[1:]}, reverse=True)
    anios, origen = {}, {}
    for ts in capturas:
        ruta = CARPETA / 'wayback' / f'qqp_php_{ts}.html.gz'
        if ruta.exists():
            html = leer_crudo(_relativa(ruta))
        else:
            rr = cliente.get(f'https://web.archive.org/web/{ts}id_/{PAGINA}')
            rr.raise_for_status()
            html = rr.content
            guardar_crudo(FUENTE, f'qqp_php_{ts}.html', html, fecha='wayback')
        for anio, url in descubrir_enlaces(html)['anios'].items():
            if anio not in anios:
                anios[anio], origen[anio] = url, f'https://web.archive.org/web/{ts}/{PAGINA}'
    _WAYBACK = {'anios': dict(sorted(anios.items())), 'origen': origen}
    return _WAYBACK


def ruta_rar(anio: int) -> Path:
    """QQP 2025 se lee del RAR del Avance 1 (sólo lectura, nunca se copia); los demás años, de data/raw/qqp/."""
    if anio == 2025 and QQP_2025_RAR.exists():
        return QQP_2025_RAR
    return CARPETA / f'QQP_{anio}.rar'


def ruta_manifiesto(anio: int) -> Path:
    return CARPETA / f'QQP_{anio}.rar.manifest.json'


def leer_manifiesto(anio: int) -> dict:
    p = ruta_manifiesto(anio)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def _relativa(p: Path) -> str:
    return Path(os.path.relpath(p, RAIZ)).as_posix()


def _verificar_2025() -> Path:
    """Verifica el SHA-256 del RAR del Avance 1 y deja un manifiesto de referencia en data/raw/qqp/."""
    h = sha256_archivo(QQP_2025_RAR)
    if h != SHA256_2025:
        raise ValueError(f'QQP_2025.rar del Avance 1 cambió: SHA-256 {h}. Revisar antes de continuar.')
    original = QQP_2025_RAR.with_name('QQP_2025.manifest.json')
    previo = json.loads(original.read_text(encoding='utf-8')) if original.exists() else {}
    CARPETA.mkdir(parents=True, exist_ok=True)
    manifiesto = {'url': previo.get('url', URL_2025), 'archivo': _relativa(QQP_2025_RAR),
                  'descargado_utc': previo.get('downloaded_at'), 'bytes': QQP_2025_RAR.stat().st_size, 'sha256': h,
                  'verificado_utc': ahora_utc(), 'anio': 2025, 'pagina': PAGINA,
                  'origen': 'RAR del Avance 1 (../datos_originales, sólo lectura; no se copia ni se vuelve a descargar)'}
    ruta_manifiesto(2025).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding='utf-8')
    return QQP_2025_RAR


def _bajar(cliente: Cliente, url: str, destino: Path) -> dict:
    """Descarga en streaming a .part, valida que sea RAR y lo mueve a su lugar. Devuelve cabeceras útiles."""
    parcial = destino.with_name(destino.name + '.part')
    destino.parent.mkdir(parents=True, exist_ok=True)
    r = cliente.get(url, stream=True, timeout=(30, 300))
    r.raise_for_status()
    tipo = r.headers.get('content-type', '')
    if 'html' in tipo:
        raise ValueError(f'PROFECO devolvió HTML en lugar del archivo: {url}')
    n, siguiente = 0, 10 << 20
    with open(parcial, 'wb') as f:
        for bloque in r.iter_content(1 << 20):
            f.write(bloque)
            n += len(bloque)
            if n >= siguiente:
                log.info('%s: %.0f MiB', destino.name, n / 2**20)
                siguiente += 10 << 20
    with open(parcial, 'rb') as f:
        if f.read(6) != MAGIA_RAR:
            raise ValueError(f'El archivo descargado no es RAR: {url}')
    parcial.replace(destino)
    return {'content_type': tipo, 'content_disposition': r.headers.get('content-disposition'),
            'fecha_servidor': r.headers.get('date')}


def descargar(anio: int, cliente: Cliente | None = None, forzar: bool = False, enlaces: dict | None = None) -> Path:
    """RAR anual oficial con manifiesto (url, fecha, bytes, SHA-256). Idempotente: si ya existe, no se descarga."""
    if anio == 2025 and QQP_2025_RAR.exists():
        return _verificar_2025()
    destino = CARPETA / f'QQP_{anio}.rar'
    if destino.exists() and ruta_manifiesto(anio).exists() and not forzar:
        return destino
    cliente = cliente or Cliente()
    enlaces = enlaces or leer_pagina(cliente)[0]
    url, pagina, nota = enlaces['anios'].get(anio), PAGINA, None
    if not url:
        wb = enlaces_wayback()
        url, pagina = wb['anios'].get(anio), wb['origen'].get(anio)
        nota = ('enlace file.php?t=... recuperado de una captura de qqp.php en Wayback Machine; el archivo se '
                'descarga del servidor oficial de PROFECO')
    if not url:
        raise FileNotFoundError(f'PROFECO no publica QQP {anio} (ni en la página actual ni en capturas de Wayback)')
    log.info('descargando QQP %s desde %s', anio, url)
    info = _bajar(cliente, url, destino)
    escribir_manifiesto(destino, url, extra=dict(anio=anio, pagina=pagina, **info, huella_inicio=_huella_local(destino),
                                                 **({'nota': nota} if nota else {})))
    if anio == 2025 and sha256_archivo(destino) != SHA256_2025:
        log.warning('QQP 2025 descargado difiere del Avance 1; la reproducción exacta requiere el RAR original.')
    return destino


def _huella_local(rar: Path, n: int = 1 << 16) -> str:
    with open(rar, 'rb') as f:
        return hashlib.sha256(f.read(n)).hexdigest()


def _huella_remota(cliente: Cliente, url: str, n: int = 1 << 16) -> str:
    """SHA-256 de los primeros 64 KiB del archivo remoto (el servidor no da tamaño, ETag ni Last-Modified).
    En RAR5 la cabecera principal cambia con el tamaño del archivo, así que una versión nueva cambia la huella."""
    r = cliente.get(url, stream=True)
    r.raise_for_status()
    leido = b''
    for bloque in r.iter_content(8192):
        leido += bloque
        if len(leido) >= n:
            break
    r.close()
    return hashlib.sha256(leido[:n]).hexdigest()


def actualizar(anio: int, cliente: Cliente, enlaces: dict, dias_revision_completa: int = 7) -> dict:
    """¿PROFECO publicó una versión nueva del archivo de `anio`? Compara la huella de los primeros 64 KiB y, cada
    `dias_revision_completa` días, descarga completo y compara SHA-256. La versión previa se conserva renombrada."""
    url = enlaces['anios'].get(anio)
    if not url:
        return dict(anio=anio, cambio=False, detalle='no publicado')
    destino = CARPETA / f'QQP_{anio}.rar'
    previo = leer_manifiesto(anio)
    if not destino.exists() or not previo:
        descargar(anio, cliente, forzar=True, enlaces=enlaces)
        return dict(anio=anio, cambio=True, detalle='primera descarga')
    huella = _huella_remota(cliente, url)
    ultima = pd.Timestamp(previo.get('verificado_utc') or previo['descargado_utc'])
    completa = (pd.Timestamp.now(tz='UTC') - ultima) >= pd.Timedelta(days=dias_revision_completa)
    if huella == previo.get('huella_inicio') and not completa:
        return dict(anio=anio, cambio=False, detalle='huella igual')
    nuevo = destino.with_name(destino.name + '.nuevo')
    info = _bajar(cliente, url, nuevo)
    h = sha256_archivo(nuevo)
    if h == previo.get('sha256'):
        nuevo.unlink()
        previo.update(verificado_utc=ahora_utc(), huella_inicio=huella)
        ruta_manifiesto(anio).write_text(json.dumps(previo, ensure_ascii=False, indent=2), encoding='utf-8')
        return dict(anio=anio, cambio=False, detalle='sha igual')
    viejo = destino.with_name(f'QQP_{anio}.{previo["sha256"][:12]}.rar')
    destino.replace(viejo)
    ruta_manifiesto(anio).replace(viejo.with_name(viejo.name + '.manifest.json'))
    nuevo.replace(destino)
    escribir_manifiesto(destino, url, extra=dict(anio=anio, pagina=PAGINA, **info, huella_inicio=huella,
                                                 version_previa=dict(archivo=viejo.name, sha256=previo['sha256'],
                                                                     descargado_utc=previo.get('descargado_utc'))))
    return dict(anio=anio, cambio=True, detalle=f'versión nueva {h[:12]} (previa {previo["sha256"][:12]})')


# ---------------------------------------------------------------------------------------------- lectura del RAR

def _tar() -> str:
    if os.name == 'nt':
        return str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'tar.exe')
    t = shutil.which('bsdtar')
    if not t:
        raise RuntimeError('Se requiere bsdtar (libarchive-tools) para leer el RAR en este entorno.')
    return t


def miembros_csv(rar: Path) -> list[str]:
    listado = subprocess.run([_tar(), '-tf', str(rar)], capture_output=True, check=True)
    nombres = listado.stdout.decode('utf-8', errors='replace').splitlines()
    return sorted(x for x in nombres if x.lower().endswith('.csv'))


def _normalizar_serie(s: pd.Series) -> pd.Series:
    """`s.map(normalizar)` calculado una vez por valor distinto (mismo resultado, mucho más rápido)."""
    mapa = {u: normalizar(u) for u in pd.unique(s.dropna())}
    return s.map(mapa).fillna('').astype(object)


def filtrar_bloque(bloque: pd.DataFrame, inicio: int, desfase: int = 2) -> tuple[pd.DataFrame, dict]:
    """Numera filas como el Avance 1 (número de línea en el CSV: con cabecera la 1.ª fila de datos es la línea 2)
    y conserva APARATOS ELECTRONICOS de todas las entidades."""
    faltan = REQUERIDAS - set(bloque.columns)
    if faltan:
        raise ValueError(f'Esquema inesperado: faltan {sorted(faltan)}')
    bloque['fila_origen'] = range(inicio + desfase, inicio + desfase + len(bloque))
    cdmx = _normalizar_serie(bloque.estado).isin(ESTADOS_CDMX)
    tec = _normalizar_serie(bloque.categoria).eq(CATEGORIA)
    conteo = dict(filas_nacionales=len(bloque), filas_cdmx=int(cdmx.sum()),
                  filas_tecnologia_cdmx=int((cdmx & tec).sum()), filas_tecnologia_nacional=int(tec.sum()))
    return bloque.loc[tec].copy(), conteo


class _ConPrefijo(io.RawIOBase):
    """Flujo que entrega primero `prefijo` (la línea ya leída para mirar la cabecera) y luego el resto."""
    def __init__(self, prefijo: bytes, flujo):
        self.prefijo, self.flujo = prefijo, flujo

    def readable(self):
        return True

    def readinto(self, b):
        if self.prefijo:
            n = min(len(b), len(self.prefijo))
            b[:n], self.prefijo = self.prefijo[:n], self.prefijo[n:]
            return n
        datos = self.flujo.read1(len(b)) if hasattr(self.flujo, 'read1') else self.flujo.read(len(b))
        b[:len(datos)] = datos
        return len(datos)


def es_cabecera(linea: bytes) -> bool:
    """2024–2026 traen cabecera; 2018–2023 no (mismas 15 columnas, mismo orden: ORIGINALES)."""
    campos = linea.decode('utf-8-sig', errors='replace').strip().lower().split(',')
    return {'producto', 'precio', 'fecha_registro'} <= set(campos)


def leer_csv(flujo, miembro: str, hash_rar: str, bloque: int = BLOQUE) -> tuple[list[pd.DataFrame], dict]:
    partes, total = [], dict(archivo=miembro, filas_nacionales=0, filas_cdmx=0, filas_tecnologia_cdmx=0,
                             filas_tecnologia_nacional=0)
    primera = flujo.readline()
    cabecera = es_cabecera(primera)
    total['cabecera'] = cabecera
    flujo = io.BufferedReader(_ConPrefijo(primera, flujo), 1 << 20)
    kw = dict(header=0) if cabecera else dict(header=None, names=ORIGINALES)
    for trozo in pd.read_csv(flujo, dtype=str, encoding='utf-8-sig', chunksize=bloque, **kw):
        sub, conteo = filtrar_bloque(trozo, total['filas_nacionales'], desfase=2 if cabecera else 1)
        for k, v in conteo.items():
            total[k] += v
        sub['archivo_origen'] = miembro
        sub['sha256_archivo'] = hash_rar
        partes.append(sub)
    return partes, total


def leer_rar(rar: Path, hash_rar: str, bloque: int = BLOQUE) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recorre TODOS los CSV del RAR por bloques. Devuelve (tecnología nacional con columnas originales, auditoría)."""
    miembros = miembros_csv(rar)
    if not miembros:
        raise ValueError(f'{rar.name} no contiene CSV.')
    partes, auditoria = [], []
    for miembro in miembros:
        proc = subprocess.Popen([_tar(), '-xOf', str(rar), miembro], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            p, conteo = leer_csv(proc.stdout, miembro, hash_rar, bloque)
        except Exception:
            proc.kill()
            proc.wait()
            raise
        finally:
            proc.stdout.close()
        error = proc.stderr.read().decode(errors='replace')
        proc.stderr.close()
        if proc.wait():
            raise RuntimeError(f'{miembro}: {error}')
        partes.extend(p)
        auditoria.append(conteo)
        log.info('%s: %s filas; %s tecnología nacional; %s tecnología CDMX', miembro, f"{conteo['filas_nacionales']:,}",
                 f"{conteo['filas_tecnologia_nacional']:,}", f"{conteo['filas_tecnologia_cdmx']:,}")
    tecnologia = pd.concat(partes, ignore_index=True)
    return tecnologia, pd.DataFrame(auditoria)


def recorte_cdmx(tecnologia: pd.DataFrame) -> pd.DataFrame:
    return tecnologia.loc[_normalizar_serie(tecnologia.estado).isin(ESTADOS_CDMX)].reset_index(drop=True)


# ---------------------------------------------------------------------------------------------- depuración

def _ids(df: pd.DataFrame) -> list[str]:
    """`df.apply(id_estable, axis=1)` del Avance 1, con caché por combinación."""
    cache, salida = {}, []
    for fila in df.itertuples(index=False, name=None):
        v = cache.get(fila)
        if v is None:
            v = cache[fila] = id_estable(fila)
        salida.append(v)
    return salida


def depurar(originales: pd.DataFrame, anio: int) -> dict:
    """Misma depuración del Avance 1. Devuelve datos (todas las filas con identidad y banderas), limpios,
    exclusiones (con `motivo_exclusion`) y calidad."""
    datos = originales.copy()
    for col in COLS_PRODUCTO + COLS_SUCURSAL:
        datos['n_' + col] = _normalizar_serie(datos[col])
    pk, sk = ['n_' + c for c in COLS_PRODUCTO], ['n_' + c for c in COLS_SUCURSAL]
    datos['producto_id'] = _ids(datos[pk])
    datos['sucursal_id'] = _ids(datos[sk])
    datos['serie_id'] = _ids(datos[['producto_id', 'sucursal_id']])
    datos['precio_num'] = pd.to_numeric(datos.precio, errors='coerce')
    datos['fecha'] = pd.to_datetime(datos.fecha_registro, errors='coerce').dt.normalize()
    datos['identidad_incompleta'] = datos[pk + sk].eq('').any(axis=1)
    datos['precio_invalido'] = datos.precio_num.isna() | datos.precio_num.le(0)
    datos['fecha_invalida'] = datos.fecha.isna() | datos.fecha.dt.year.ne(anio)
    invalido = datos[['identidad_incompleta', 'precio_invalido', 'fecha_invalida']].any(axis=1)
    validos = datos.loc[~invalido]
    repetido = validos.duplicated(CLAVE_SERIE + ['precio_num'], keep='first')
    unicos = validos.loc[~repetido]
    conflicto = unicos.groupby(CLAVE_SERIE).precio_num.transform('nunique').gt(1)
    limpios = unicos.loc[~conflicto].copy()
    exclusiones = pd.concat([datos.loc[invalido].assign(motivo_exclusion='invalido'),
                             validos.loc[repetido].assign(motivo_exclusion='repeticion'),
                             unicos.loc[conflicto].assign(motivo_exclusion='conflicto')])
    calidad = {'originales': len(datos), 'invalidos': int(invalido.sum()), 'repeticiones': int(repetido.sum()),
               'filas_en_conflicto': int(conflicto.sum()),
               'serie_fechas_en_conflicto': len(unicos.loc[conflicto, CLAVE_SERIE].drop_duplicates()),
               'limpios': len(limpios),
               'identidad_incompleta': int(datos.identidad_incompleta.sum()),
               'precio_invalido': int(datos.precio_invalido.sum()), 'fecha_invalida': int(datos.fecha_invalida.sum())}
    assert sum(calidad[k] for k in ['invalidos', 'repeticiones', 'filas_en_conflicto', 'limpios']) == len(datos)
    assert not limpios.duplicated(CLAVE_SERIE).any()
    return dict(datos=datos, limpios=limpios, exclusiones=exclusiones, calidad=calidad)


# ---------------------------------------------------------------------------------------------- eventos y cobertura

def eventos() -> pd.DataFrame:
    """Eventos de config/eventos.yaml más los históricos de EVENTOS_HISTORICOS que aún no estén allí."""
    ev = cargar_eventos()
    anios = set(ev.d0.dt.year)
    extra = []
    for anio, (eid, ini, fin, fuente) in EVENTOS_HISTORICOS.items():
        if anio in anios:
            continue
        d0, f = pd.Timestamp(ini), pd.Timestamp(fin)
        extra.append(dict(evento_id=eid, nombre=f'Buen Fin {anio}', d0=d0, fin=f,
                          base_inicio=d0 - timedelta(days=60), base_fin=d0 - timedelta(days=15),
                          previo_inicio=d0 - timedelta(days=14), previo_fin=d0 - timedelta(days=1),
                          evento_inicio=d0, evento_fin=f, posterior_inicio=f + timedelta(days=1),
                          posterior_fin=f + timedelta(days=14), fuente_fechas=fuente))
    if extra:
        ev = pd.concat([ev, pd.DataFrame(extra)], ignore_index=True)
    return ev.sort_values('d0').reset_index(drop=True)


def evento_de(anio: int) -> pd.Series | None:
    ev = eventos()
    ev = ev.loc[ev.d0.dt.year.eq(anio)]
    return ev.iloc[0] if len(ev) else None


def variables_por_serie(limpios: pd.DataFrame, ev: pd.Series) -> pd.DataFrame:
    """06_variables_por_serie del Avance 1, para cualquier evento. Mediana de días observados; no se imputa."""
    meta = ['producto_id', 'sucursal_id', 'producto', 'marca', 'presentacion', 'nombre_comercial',
            'cadena_comercial', 'municipio']
    series = limpios.groupby('serie_id')[meta].first().copy()
    for nombre in ('base', 'previo', 'evento'):
        sub = limpios.loc[limpios.fecha.between(ev[f'{nombre}_inicio'], ev[f'{nombre}_fin'])]
        g = sub.groupby('serie_id').agg(n=('fecha', 'nunique'), mediana=('precio_num', 'median'),
                                        minimo=('precio_num', 'min'), inicio=('fecha', 'min'), fin=('fecha', 'max'))
        series = series.join(g.add_suffix('_' + nombre))
        series['n_' + nombre] = series['n_' + nombre].fillna(0).astype(int)
    series['amplitud_base_dias'] = (series.fin_base - series.inicio_base).dt.days
    series['cobertura_ahorro'] = series.n_base.ge(4) & series.amplitud_base_dias.ge(21) & series.n_evento.ge(1)
    series['cobertura_alza'] = series.cobertura_ahorro & series.n_previo.ge(2)
    series['ahorro_historico_pct'] = (100 * (1 - series.mediana_evento / series.mediana_base)).where(series.cobertura_ahorro)
    series['alza_previa_pct'] = (100 * (series.mediana_previo / series.mediana_base - 1)).where(series.cobertura_alza)
    series['estado_evidencia'] = series.cobertura_ahorro.map({True: 'cobertura_provisional_suficiente',
                                                              False: 'evidencia_insuficiente'})
    # Diagnóstico para años en curso (2026): ¿la base ya tiene la cobertura mínima, aunque falte el evento?
    series['base_suficiente'] = series.n_base.ge(4) & series.amplitud_base_dias.ge(21)
    series['evento_id'] = ev['evento_id']
    return series


def matriz_modelo(limpios: pd.DataFrame, series: pd.DataFrame, ev: pd.Series) -> pd.DataFrame:
    """07_matriz_modelo del Avance 1: series con cobertura de alza × (ahorro, alza, variabilidad base)."""
    columnas = ['ahorro_historico_pct', 'alza_previa_pct', 'variabilidad_base_pct']
    preparadas = series.loc[series.cobertura_alza].copy()
    if preparadas.empty:
        return pd.DataFrame(columns=columnas, index=pd.Index([], name='serie_id'))
    base = limpios.loc[limpios.fecha.between(ev.base_inicio, ev.base_fin)]
    cuartiles = base.groupby('serie_id').precio_num.quantile([.25, .75]).unstack()
    preparadas['variabilidad_base_pct'] = 100 * (cuartiles[.75] - cuartiles[.25]) / preparadas.mediana_base
    return preparadas[columnas].astype(float)


def resumen_cobertura(series: pd.DataFrame) -> dict:
    return {'series': len(series), 'series_con_base': int(series.n_base.gt(0).sum()),
            'series_base_suficiente': int(series.base_suficiente.sum()),
            'series_con_previo': int(series.n_previo.gt(0).sum()), 'series_con_evento': int(series.n_evento.gt(0).sum()),
            'series_cobertura_ahorro': int(series.cobertura_ahorro.sum()),
            'series_cobertura_alza': int(series.cobertura_alza.sum())}


# ---------------------------------------------------------------------------------------------- bronze

def _modelos(presentaciones: pd.Series) -> pd.Series:
    mapa = {p: modelo_qqp(p)['modelo_normalizado'] for p in pd.unique(presentaciones.dropna())}
    return presentaciones.map(mapa)


def a_observaciones(limpios: pd.DataFrame, fuente: str, url: str, hash_rar: str, rar_rel: str,
                    fecha_captura: str, anio: int) -> pd.DataFrame:
    """Observaciones limpias en el esquema común; columnas originales, n_* e identidad quedan como extras."""
    t = lambda c: limpios[c].fillna('').astype(str)  # noqa: E731
    obs = pd.DataFrame({
        'fuente': fuente, 'metodo': 'archivo_oficial', 'canal': 'tienda_fisica', 'tipo_precio': TIPO_PRECIO,
        'fecha_precio': limpios.fecha.dt.strftime('%Y-%m-%d'), 'fecha_captura': fecha_captura,
        'producto_canonico_id': pd.NA, 'id_externo': limpios.producto_id, 'tipo_id_externo': 'qqp',
        'marca': limpios.marca, 'modelo_normalizado': _modelos(limpios.presentacion),
        'descripcion_original': t('producto') + ' | ' + t('marca') + ' | ' + t('presentacion'),
        'plataforma': pd.NA,
        'vendedor_o_cadena': limpios.n_cadena_comercial + ' | ' + limpios.n_nombre_comercial + ' | ' + limpios.sucursal_id,
        'sucursal_id': limpios.sucursal_id, 'estado': limpios.estado, 'alcaldia': limpios.municipio,
        'precio': limpios.precio_num.astype(float), 'precio_anterior_anunciado': np.nan,
        'pct_descuento_anunciado': np.nan, 'moneda': 'MXN', 'disponibilidad': pd.NA, 'condiciones': pd.NA,
        'url': url, 'ruta_raw': rar_rel + '::' + limpios.archivo_origen + '#' + limpios.fila_origen.astype(str),
        'hash_raw': hash_rar,
        # extras: identidad del Avance 1, columnas originales y normalizadas
        'serie_id': limpios.serie_id, 'producto_id': limpios.producto_id, 'anio_archivo': anio,
        **{c: limpios[c] for c in ORIGINALES if c not in ('precio', 'estado', 'marca')},
        'precio_texto': limpios.precio,
        **{'n_' + c: limpios['n_' + c] for c in COLS_PRODUCTO + COLS_SUCURSAL},
        'archivo_origen': limpios.archivo_origen, 'fila_origen': limpios.fila_origen,
    })
    return a_dataframe(obs.reset_index(drop=True))


def validar_observaciones(obs: pd.DataFrame) -> None:
    assert not obs.duplicated(CLAVE).any(), 'CLAVE duplicada'
    assert obs.precio.gt(0).all(), 'precio no positivo'
    assert pd.to_datetime(obs.fecha_precio, format='%Y-%m-%d', errors='coerce').notna().all(), 'fecha inválida'
    pct = obs.pct_descuento_anunciado.dropna()
    assert pct.between(-100, 100).all()


def _reemplazar(fuente: str, df: pd.DataFrame, nombre: str, clave=None) -> Path:
    """Re-extraer un año reemplaza su tabla completa (si PROFECO corrige filas no quedan restos de la versión previa)."""
    (BRONZE / fuente / f'{nombre}.parquet').unlink(missing_ok=True)
    return escribir_bronze(fuente, df, fecha=nombre, clave=clave)


def _para_parquet(df: pd.DataFrame) -> pd.DataFrame:
    return df.reset_index() if df.index.name else df


def extraer(anio: int, nacional: bool = True) -> dict:
    """Lee el RAR completo de `anio` y escribe en bronze CDMX, nacional, exclusiones, series y resumen."""
    asegurar_directorios()
    rar = ruta_rar(anio)
    if not rar.exists():
        raise FileNotFoundError(f'Falta {rar}; correr primero descargar({anio}).')
    hash_rar = sha256_archivo(rar)
    if anio == 2025 and rar == QQP_2025_RAR and hash_rar != SHA256_2025:
        raise ValueError(f'QQP_2025.rar cambió: {hash_rar}')
    manif = leer_manifiesto(anio)
    if manif.get('sha256') and manif['sha256'] != hash_rar:
        raise ValueError(f'El RAR de {anio} no coincide con su manifiesto; revisar antes de continuar.')
    url = manif.get('url') or (URL_2025 if anio == 2025 else '')
    fecha_captura = str(manif.get('descargado_utc') or ahora_utc())[:10]
    t0 = datetime.now(timezone.utc)
    tecnologia, auditoria = leer_rar(rar, hash_rar)
    auditoria['anio'] = anio
    recortes = {FUENTE_CDMX: recorte_cdmx(tecnologia)}
    if nacional:
        recortes[FUENTE_NACIONAL] = tecnologia
    ev = evento_de(anio)
    resumen = dict(anio=anio, url=url, sha256=hash_rar, archivo=_relativa(rar), bytes=rar.stat().st_size,
                   archivos_csv=len(auditoria), filas_nacionales_leidas=int(auditoria.filas_nacionales.sum()),
                   filas_cdmx_todas_categorias=int(auditoria.filas_cdmx.sum()),
                   evento=None if ev is None else ev['evento_id'], recortes={}, extraido_utc=ahora_utc())
    for fuente, originales in recortes.items():
        r = depurar(originales, anio)
        limpios = r['limpios']
        obs = a_observaciones(limpios, fuente, url, hash_rar, _relativa(rar), fecha_captura, anio)
        validar_observaciones(obs)
        _reemplazar(fuente, obs, str(anio), clave=CLAVE)
        exc = r['exclusiones'].copy()
        exc['fecha'] = exc.fecha.dt.strftime('%Y-%m-%d')
        _reemplazar(f'{fuente}_exclusiones', exc.reset_index(drop=True), str(anio))
        info = dict(calidad=r['calidad'], referencias=int(limpios.producto_id.nunique()),
                    sucursales=int(limpios.sucursal_id.nunique()), series=int(limpios.serie_id.nunique()),
                    alcaldias_o_municipios=int(limpios.n_municipio.nunique()),
                    entidades=int(_normalizar_serie(limpios.estado).nunique()),
                    fecha_min=str(limpios.fecha.min().date()) if len(limpios) else None,
                    fecha_max=str(limpios.fecha.max().date()) if len(limpios) else None,
                    dias_con_dato=int(limpios.fecha.nunique()))
        if ev is not None and len(limpios):
            series = variables_por_serie(limpios, ev)
            _reemplazar(f'{fuente}_series', _para_parquet(series), ev['evento_id'])
            info['cobertura'] = resumen_cobertura(series)
            if fuente == FUENTE_CDMX:
                X = matriz_modelo(limpios, series, ev)
                _reemplazar(f'{FUENTE_CDMX}_matriz', _para_parquet(X), ev['evento_id'])
                info['matriz_filas'] = len(X)
        resumen['recortes'][fuente] = info
        log.info('%s %s: %s', fuente, anio, r['calidad'])
    _reemplazar('qqp_auditoria', auditoria, str(anio))
    resumen['segundos'] = round((datetime.now(timezone.utc) - t0).total_seconds())
    carpeta = BRONZE / 'qqp_resumen'
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f'{anio}.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2, default=str),
                                          encoding='utf-8')
    return resumen


# ---------------------------------------------------------------------------------------------- corridas

def _registrar(resumenes: list[dict], fallos: list[str], bloqueado: bool, inicio: str, entorno: str):
    for fuente in (FUENTE_CDMX, FUENTE_NACIONAL):
        filas = sum(r['recortes'].get(fuente, {}).get('calidad', {}).get('limpios', 0) for r in resumenes)
        detalle = '; '.join([f"{r['anio']}: {r['recortes'][fuente]['calidad']['limpios']} limpias"
                             for r in resumenes if fuente in r['recortes']] + fallos)
        estado = ('bloqueado' if bloqueado else 'ok' if resumenes and not fallos else
                  'parcial' if resumenes else 'fallo')
        registrar_estado(fuente, estado, filas, detalle=detalle, inicio_utc=inicio, entorno=entorno)
    revisar_alertas()


def backfill(anios: list[int] | None = None, nacional: bool = True, entorno: str = 'local',
             forzar_extraccion: bool = False) -> dict:
    """Descarga (si falta) y procesa cada año. Idempotente: el RAR no se vuelve a bajar y un año ya extraído
    con el mismo SHA-256 no se vuelve a leer, salvo `forzar_extraccion`."""
    asegurar_directorios()
    inicio = ahora_utc()
    cliente, enlaces = Cliente(), None
    resumenes, fallos, bloqueado = [], [], False
    try:
        enlaces = leer_pagina(cliente)[0]
    except (Bloqueado, NoPermitido) as e:
        bloqueado = True
        fallos.append(f'página bloqueada: {e}')
    except Exception as e:
        fallos.append(f'página: {e}')
    anios = anios or sorted(set((enlaces or {}).get('anios', {})) | {2025} | set(ANIOS_HISTORICOS))
    for anio in anios:
        try:
            if anio != 2025 and not ruta_rar(anio).exists():
                if enlaces is None:
                    raise RuntimeError('sin enlaces de la página oficial')
                descargar(anio, cliente, enlaces=enlaces)
            else:
                descargar(anio, cliente, enlaces=enlaces or {'anios': {}})
            previo = BRONZE / 'qqp_resumen' / f'{anio}.json'
            if previo.exists() and not forzar_extraccion:
                r = json.loads(previo.read_text(encoding='utf-8'))
                if r.get('sha256') == sha256_archivo(ruta_rar(anio)) and (not nacional or FUENTE_NACIONAL in r['recortes']):
                    log.info('QQP %s ya extraído con el mismo SHA-256; se reutiliza.', anio)
                    resumenes.append(r)
                    continue
            resumenes.append(extraer(anio, nacional=nacional))
        except (Bloqueado, NoPermitido) as e:
            bloqueado = True
            fallos.append(f'{anio}: bloqueado {e}')
            break
        except Exception as e:
            log.exception('QQP %s: %s', anio, e)
            fallos.append(f'{anio}: {type(e).__name__}: {e}')
    _registrar(resumenes, fallos, bloqueado, inicio, entorno)
    return dict(anios=[r['anio'] for r in resumenes], fallos=fallos, bloqueado=bloqueado,
                limpias={r['anio']: {k: v['calidad']['limpios'] for k, v in r['recortes'].items()} for r in resumenes})


def diario(productos: pd.DataFrame | None = None, fecha: str | None = None, entorno: str = 'local') -> dict:
    """Revisión periódica: ¿hay versión nueva del archivo del año en curso o un año nuevo publicado? Si cambió,
    descarga y re-extrae. QQP publica el archivo nacional completo, así que `productos` no filtra la descarga
    (la lista fija se aplica al emparejar); se acepta por compatibilidad con la interfaz común."""
    asegurar_directorios()
    inicio = ahora_utc()
    anio_actual = int((fecha or hoy())[:4])
    cliente = Cliente()
    resumenes, fallos, bloqueado, cambios = [], [], False, []
    try:
        enlaces = leer_pagina(cliente)[0]
        objetivo = [a for a in enlaces['anios'] if a == anio_actual]
        for anio in objetivo:
            if anio == 2025 and QQP_2025_RAR.exists():
                continue  # el archivo 2025 del Avance 1 queda congelado
            c = actualizar(anio, cliente, enlaces)
            cambios.append(c)
            if c['cambio'] or not (BRONZE / 'qqp_resumen' / f'{anio}.json').exists():
                resumenes.append(extraer(anio))
    except (Bloqueado, NoPermitido) as e:
        bloqueado = True
        fallos.append(f'bloqueado: {e}')
    except Exception as e:
        log.exception('diario QQP: %s', e)
        fallos.append(f'{type(e).__name__}: {e}')
    if not resumenes:  # sin cambios: el estado refleja que la revisión se hizo
        for fuente in (FUENTE_CDMX, FUENTE_NACIONAL):
            registrar_estado(fuente, 'bloqueado' if bloqueado else 'fallo' if fallos else 'ok', 0,
                             detalle='; '.join([f"{c['anio']}: {c['detalle']}" for c in cambios] + fallos),
                             inicio_utc=inicio, entorno=entorno)
        revisar_alertas()
    else:
        _registrar(resumenes, fallos, bloqueado, inicio, entorno)
    return dict(cambios=cambios, extraidos=[r['anio'] for r in resumenes], fallos=fallos, bloqueado=bloqueado)


# ---------------------------------------------------------------------------------------------- años 2018–2023

# Lugares revisados para años anteriores a 2024 (todo gratuito y sin cuenta). `historicos()` deja el crudo de
# cada respuesta en data/raw/qqp/<fecha>/ para poder auditar la búsqueda. Resultado (2026-10-16): qqp.php ya sólo
# lista 2024–2026, pero sus capturas de Wayback (2023-12 a 2025-01) listan 2015–2023 y esos enlaces file.php?t=...
# siguen respondiendo con el RAR oficial: `enlaces_wayback()` los recupera y `descargar()` los usa. El portal
# Dato_historico.aspx sólo ofrece la base 1999+ por solicitud escrita (formulario o correo), no por descarga.
CONSULTAS_HISTORICOS = [
    ('PROFECO datos abiertos (página actual)', PAGINA),
    ('PROFECO índice de datos abiertos', 'https://datos.profeco.gob.mx/datos_abiertos/index.php'),
    ('PROFECO portal de históricos (canasta)', 'https://www.profeco.gob.mx/precios/canasta/Dato_historico.aspx'),
    ('datos.gob.mx CKAN API (búsqueda QQP)',
     'https://datos.gob.mx/api/3/action/package_search?q=quien%20es%20quien%20en%20los%20precios&rows=20'),
    ('datos.gob.mx ficha del conjunto', 'https://datos.gob.mx/busca/dataset/quien-es-quien-en-los-precios'),
    ('datamx.io CKAN API (búsqueda QQP)', 'https://datamx.io/api/3/action/package_search?q=profeco&rows=50'),
    ('Wayback CDX de qqp.php (enlaces de años previos)',
     'https://web.archive.org/cdx/search/cdx?url=datos.profeco.gob.mx/datos_abiertos/qqp.php&output=json'
     '&filter=statuscode:200&collapse=digest'),
]


def historicos(consultas: list[tuple[str, str]] | None = None) -> list[dict]:
    """Busca archivos QQP 2018–2023 publicados gratis. No envía formularios ni crea cuentas."""
    cliente = Cliente(pausa=(3.0, 6.0))
    salida = []
    for nombre, url in consultas or CONSULTAS_HISTORICOS:
        fila = dict(lugar=nombre, url=url, consultado_utc=ahora_utc())
        try:
            r = cliente.get(url)
            fila.update(status=r.status_code, tipo=r.headers.get('content-type'), bytes=len(r.content),
                        url_final=r.url)
            fila['ruta_raw'], _ = guardar_crudo(FUENTE, 'historicos_' + re.sub(r'\W+', '_', nombre)[:60], r.content)
            texto = r.text if 'json' in fila['tipo'] or 'html' in fila['tipo'] or 'text' in fila['tipo'] else ''
            fila['anios_mencionados'] = sorted({int(a) for a in re.findall(r'\b(20[12]\d)\b', texto)
                                                if 2015 <= int(a) <= 2023})
            fila['enlaces_archivo'] = len(re.findall(r'file\.php\?t=[0-9a-f]+', texto))
        except (Bloqueado, NoPermitido) as e:
            fila.update(status='bloqueado' if isinstance(e, Bloqueado) else 'robots', error=str(e))
        except Exception as e:
            fila.update(status='error', error=f'{type(e).__name__}: {e}')
        salida.append(fila)
        log.info('%s', fila)
    return salida


# ---------------------------------------------------------------------------------------------- comprobaciones

ESPERADO_AVANCE1 = {'originales': 39989, 'invalidos': 0, 'repeticiones': 440, 'filas_en_conflicto': 186,
                    'serie_fechas_en_conflicto': 93, 'limpios': 39363, 'referencias': 231, 'sucursales': 80,
                    'series': 4551, 'series_cobertura_ahorro': 298, 'series_cobertura_alza': 93}


def reproduccion_avance1() -> dict:
    """Recalcula las cifras del Avance 1 leyendo SOLO el bronze generado y compara con 06/07 del Avance 1."""
    obs = pd.read_parquet(BRONZE / FUENTE_CDMX / '2025.parquet')
    exc = pd.read_parquet(BRONZE / f'{FUENTE_CDMX}_exclusiones' / '2025.parquet')
    series = pd.read_parquet(BRONZE / f'{FUENTE_CDMX}_series' / 'BF2025.parquet').set_index('serie_id')
    X = pd.read_parquet(BRONZE / f'{FUENTE_CDMX}_matriz' / 'BF2025.parquet').set_index('serie_id')
    motivo = exc.motivo_exclusion.value_counts()
    conflictos = exc.loc[exc.motivo_exclusion.eq('conflicto')]
    obtenido = {'originales': len(obs) + len(exc), 'invalidos': int(motivo.get('invalido', 0)),
                'repeticiones': int(motivo.get('repeticion', 0)), 'filas_en_conflicto': len(conflictos),
                'serie_fechas_en_conflicto': len(conflictos[CLAVE_SERIE].drop_duplicates()), 'limpios': len(obs),
                'referencias': obs.id_externo.nunique(), 'sucursales': obs.sucursal_id.nunique(),
                'series': obs.serie_id.nunique(), 'series_cobertura_ahorro': int(series.cobertura_ahorro.sum()),
                'series_cobertura_alza': int(series.cobertura_alza.sum())}
    comparacion = {'cifras': {k: dict(esperado=v, obtenido=int(obtenido[k]), igual=v == int(obtenido[k]))
                              for k, v in ESPERADO_AVANCE1.items()}}
    a06, a07 = AVANCE1 / '06_variables_por_serie.csv', AVANCE1 / '07_matriz_modelo.csv'
    if a06.exists():
        ref = pd.read_csv(a06, index_col='serie_id', encoding='utf-8-sig')
        comparacion['06_mismos_serie_id'] = set(ref.index) == set(series.index)
        num = ['n_base', 'mediana_base', 'minimo_base', 'n_previo', 'mediana_previo', 'minimo_previo', 'n_evento',
               'mediana_evento', 'minimo_evento', 'amplitud_base_dias', 'ahorro_historico_pct', 'alza_previa_pct']
        s = series.loc[ref.index]
        comparacion['06_columnas_numericas_iguales'] = all(
            np.allclose(s[c].astype(float), ref[c].astype(float), equal_nan=True, rtol=1e-9, atol=1e-9) for c in num)
        comparacion['06_coberturas_iguales'] = bool((s.cobertura_ahorro == ref.cobertura_ahorro.astype(bool)).all()
                                                    and (s.cobertura_alza == ref.cobertura_alza.astype(bool)).all())
        fechas = ['inicio_base', 'fin_base', 'inicio_previo', 'fin_previo', 'inicio_evento', 'fin_evento']
        comparacion['06_fechas_iguales'] = all(
            (pd.to_datetime(s[c]).fillna(pd.Timestamp(0)) == pd.to_datetime(ref[c]).fillna(pd.Timestamp(0))).all()
            for c in fechas)
        comparacion['06_texto_igual'] = all((s[c].fillna('') == ref[c].fillna('')).all()
                                            for c in ['producto_id', 'sucursal_id', 'producto', 'marca', 'presentacion',
                                                      'nombre_comercial', 'cadena_comercial', 'municipio'])
    if a07.exists():
        ref7 = pd.read_csv(a07, index_col='serie_id', encoding='utf-8-sig')
        comparacion['07_mismos_serie_id'] = set(ref7.index) == set(X.index)
        comparacion['07_valores_iguales'] = bool(set(ref7.index) == set(X.index) and np.allclose(
            X.loc[ref7.index, ref7.columns].to_numpy(), ref7.to_numpy(), rtol=1e-9, atol=1e-9))
    a05 = AVANCE1 / '05_observaciones_limpias.parquet'
    if a05.exists():
        ref5 = pd.read_parquet(a05, columns=['serie_id', 'fecha', 'precio_num', 'archivo_origen', 'fila_origen'])
        ref5 = ref5.assign(fecha=pd.to_datetime(ref5.fecha).dt.strftime('%Y-%m-%d'))
        mio = obs[['serie_id', 'fecha_precio', 'precio', 'archivo_origen', 'fila_origen']].set_axis(ref5.columns, axis=1)
        comparacion['05_mismas_filas'] = bool(len(ref5) == len(mio) and ref5.sort_values(['archivo_origen', 'fila_origen'])
                                              .reset_index(drop=True).equals(mio.sort_values(['archivo_origen', 'fila_origen'])
                                                                            .reset_index(drop=True).astype(ref5.dtypes)))
    comparacion['todo_igual'] = all(v['igual'] for v in comparacion['cifras'].values()) and all(
        v for k, v in comparacion.items() if k not in ('cifras', 'todo_igual'))
    return comparacion


# ---------------------------------------------------------------------------------------------- reporte

def _leer(fuente: str, nombre: str) -> pd.DataFrame | None:
    p = BRONZE / fuente / f'{nombre}.parquet'
    return pd.read_parquet(p) if p.exists() else None


def anios_extraidos() -> list[int]:
    return sorted(int(p.stem) for p in (BRONZE / FUENTE_CDMX).glob('*.parquet') if p.stem.isdigit())


def metricas(fuente: str, anio: int) -> dict | None:
    """Cifras de un año y recorte calculadas SÓLO desde el bronze (observaciones, exclusiones, series, auditoría)."""
    obs = _leer(fuente, str(anio))
    if obs is None:
        return None
    exc = _leer(f'{fuente}_exclusiones', str(anio))
    exc = exc if exc is not None else pd.DataFrame(columns=['motivo_exclusion'])
    motivo = exc.motivo_exclusion.value_counts()
    inval = exc.loc[exc.motivo_exclusion.eq('invalido')]
    aud = _leer('qqp_auditoria', str(anio))
    fechas = pd.to_datetime(obs.fecha_precio)
    por_prod, por_serie = obs.groupby('id_externo').size(), obs.groupby('serie_id').size()
    m = dict(anio=anio, fuente=fuente, crudas=len(obs) + len(exc), limpias=len(obs),
             invalidos=int(motivo.get('invalido', 0)), repeticiones=int(motivo.get('repeticion', 0)),
             conflictos=int(motivo.get('conflicto', 0)),
             inv_fecha=int(inval.get('fecha_invalida', pd.Series(dtype=bool)).sum()),
             inv_precio=int(inval.get('precio_invalido', pd.Series(dtype=bool)).sum()),
             inv_identidad=int(inval.get('identidad_incompleta', pd.Series(dtype=bool)).sum()),
             auditoria=None if aud is None else int(aud['filas_tecnologia_cdmx' if fuente == FUENTE_CDMX
                                                        else 'filas_tecnologia_nacional'].sum()),
             filas_archivo=None if aud is None else int(aud.filas_nacionales.sum()),
             csv=None if aud is None else len(aud),
             fecha_min=str(fechas.min().date()), fecha_max=str(fechas.max().date()),
             dias_con_dato=int(fechas.nunique()), productos=int(obs.id_externo.nunique()),
             sucursales=int(obs.sucursal_id.nunique()), series=int(obs.serie_id.nunique()),
             entidades=int(_normalizar_serie(obs.estado).nunique()),
             pts_prod_med=float(por_prod.median()), pts_prod_max=int(por_prod.max()),
             pts_serie_med=float(por_serie.median()), pts_serie_max=int(por_serie.max()))
    # ¿cuántas filas colapsaría la CLAVE si vendedor_o_cadena fuera sólo 'CADENA | NOMBRE COMERCIAL'?
    corto = obs.n_cadena_comercial + ' | ' + obs.n_nombre_comercial
    m['homonimas'] = int(obs.groupby(corto).sucursal_id.nunique().gt(1).sum())
    m['colapsarian'] = int(obs.assign(v=corto).duplicated(['id_externo', 'fecha_precio', 'v']).sum())
    ev = evento_de(anio)
    series = None if ev is None else _leer(f'{fuente}_series', ev['evento_id'])
    if series is not None:
        m.update(evento=ev['evento_id'], **resumen_cobertura(series))
        for v in ('base', 'previo', 'evento'):
            m[f'dias_{v}'] = int(fechas[fechas.between(ev[f'{v}_inicio'], ev[f'{v}_fin'])].nunique())
    return m


def series_con_base_reciente(fuente: str, anio: int, dias: int = 60) -> tuple[int, str, str]:
    """Diagnóstico para el año en curso: series que, en los últimos `dias` días del archivo, ya cumplen la regla
    de base (≥4 fechas que abarquen ≥21 días). No sustituye a la ventana base oficial."""
    o = _leer(fuente, str(anio))
    f = pd.to_datetime(o.fecha_precio)
    fin = f.max()
    ini = fin - pd.Timedelta(days=dias - 1)
    g = o.assign(f=f).loc[f.between(ini, fin)].groupby('serie_id').f.agg(['nunique', 'min', 'max'])
    return int((g['nunique'].ge(4) & (g['max'] - g['min']).dt.days.ge(21)).sum()), str(ini.date()), str(fin.date())


def _n(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return '—'
    return f'{x:,.1f}' if isinstance(x, float) and not float(x).is_integer() else f'{int(x):,}'


def fila_recorte(m: dict) -> str:
    return (f"| {m['anio']} | {_n(m['crudas'])} | {_n(m['limpias'])} | {_n(m['invalidos'])} "
            f"({_n(m['inv_fecha'])}/{_n(m['inv_precio'])}/{_n(m['inv_identidad'])}) | {_n(m['repeticiones'])} | "
            f"{_n(m['conflictos'])} | {m['fecha_min']} – {m['fecha_max']} | {_n(m['dias_con_dato'])} | "
            f"{_n(m['productos'])} | {_n(m['sucursales'])} | {_n(m['series'])} | {_n(m['pts_prod_med'])} / "
            f"{_n(m['pts_prod_max'])} | {_n(m['pts_serie_med'])} / {_n(m['pts_serie_max'])} |")


def fila_cobertura(m: dict) -> str:
    if 'evento' not in m:
        return f"| {m['anio']} | sin evento | — | — | — | — | — | — | — | — |"
    return (f"| {m['anio']} | {m['evento']} | {_n(m['series'])} | {_n(m['series_con_base'])} "
            f"({_n(m['dias_base'])} d) | {_n(m['series_base_suficiente'])} | {_n(m['series_con_previo'])} "
            f"({_n(m['dias_previo'])} d) | {_n(m['series_con_evento'])} ({_n(m['dias_evento'])} d) | "
            f"**{_n(m['series_cobertura_ahorro'])}** | **{_n(m['series_cobertura_alza'])}** |")


def escribir_reporte(ruta: Path | None = None) -> Path:
    """reports/cobertura_qqp.md con cifras calculadas desde el bronze."""
    ruta = ruta or REPORTS / 'cobertura_qqp.md'
    anios = anios_extraidos()
    M = {(f, a): metricas(f, a) for a in anios for f in (FUENTE_CDMX, FUENTE_NACIONAL)}
    ev = eventos().set_index('evento_id')
    L = ['# Cobertura de PROFECO «Quién es Quién en los Precios» (QQP)', '',
         f'Generado {ahora_utc()} con `python -m sconto.fuentes.qqp reporte`. Todas las cifras se calculan con código '
         'desde `data/bronze/qqp_*` (no son estimaciones). Costo: **0** (archivos oficiales gratuitos, sin cuenta).', '',
         '- Fuente: archivos anuales oficiales (RAR con CSV quincenales/semanales) de '
         f'[datos.profeco.gob.mx]({PAGINA}); diccionario: {DICCIONARIO}.',
         "- Método `archivo_oficial`, canal `tienda_fisica`, `tipo_id_externo='qqp'`, `id_externo` = `producto_id` del "
         'Avance 1 (producto+marca+presentación normalizados).',
         "- `vendedor_o_cadena` = `CADENA | NOMBRE COMERCIAL | sucursal_id` (normalizados). Cadena + nombre comercial no "
         'basta: hay sucursales homónimas con otra dirección o alcaldía; con `sucursal_id` la CLAVE '
         '(fuente, id_externo, fecha_precio, vendedor_o_cadena) equivale a (serie_id, fecha) y es única.',
         '- Recortes: `qqp_cdmx` (CIUDAD DE MEXICO / DISTRITO FEDERAL / CDMX + APARATOS ELECTRONICOS) y `qqp_nacional` '
         '(todas las entidades, misma categoría). Son tablas separadas; el nacional incluye a CDMX y no se mezcla '
         'con el análisis principal.',
         '- Depuración idéntica al Avance 1: inválidos (identidad incompleta, precio no numérico o ≤ 0, fecha que no '
         'parsea o cuyo año no es el del archivo) → repeticiones (misma serie, fecha y precio) → conflictos (misma '
         'serie y fecha con precios distintos; no se elige ninguno) → limpias. Toda fila cruda termina en limpias o '
         'en `*_exclusiones` (columna `motivo_exclusion`). No se imputa ni se rellena nada.', '']
    if 2025 in anios and (BRONZE / f'{FUENTE_CDMX}_series' / 'BF2025.parquet').exists():
        rep = reproduccion_avance1()
        L += ['## Reproducción exacta del Avance 1 (QQP 2025, CDMX)', '',
              'RAR leído: `../datos_originales/QQP_2025.rar` (sólo lectura, SHA-256 verificado '
              f'`{SHA256_2025}`; no se copió ni se volvió a descargar).', '',
              '| cifra | esperado | obtenido | ¿igual? |', '|---|---:|---:|:---:|']
        L += [f"| {k} | {_n(v['esperado'])} | {_n(v['obtenido'])} | {'sí' if v['igual'] else '**NO**'} |"
              for k, v in rep['cifras'].items()]
        L += ['', 'Comparación contra los archivos del Avance 1 (`../resultados_anuales_2025/`):', '']
        L += [f"- `{k}`: {'sí' if v else '**NO**'}" for k, v in rep.items() if k not in ('cifras', 'todo_igual')]
        L += ['', f"**Resultado: {'reproducción exacta' if rep['todo_igual'] else 'HAY DIFERENCIAS'}.**", '']
    L += ['## Archivos obtenidos', '',
          '| año | archivo | bytes | SHA-256 (12) | CSV | cabecera | filas leídas (todas las categorías) | enlace descubierto en |',
          '|---|---|---:|---|---:|:---:|---:|---|']
    for a in anios:
        man = leer_manifiesto(a)
        aud = _leer('qqp_auditoria', str(a))
        cab = '—' if aud is None or 'cabecera' not in aud else ('sí' if aud.cabecera.all() else 'no' if not aud.cabecera.any() else 'mixta')
        origen = 'Wayback → servidor oficial' if 'web.archive.org' in str(man.get('pagina', '')) else 'qqp.php actual'
        L.append(f"| {a} | {Path(str(man.get('archivo', ruta_rar(a).name))).name} | {_n(man.get('bytes'))} | "
                 f"`{str(man.get('sha256', ''))[:12]}` | {_n(M[(FUENTE_CDMX, a)]['csv'])} | {cab} | "
                 f"{_n(M[(FUENTE_CDMX, a)]['filas_archivo'])} | {origen} |")
    encabezado = ['| año | filas crudas | limpias | inválidos (fecha/precio/identidad) | repeticiones | en conflicto | '
                  'rango de fechas | días con dato | productos | sucursales | series | puntos por producto (mediana / '
                  'máx.) | puntos por serie (mediana / máx.) |', '|---|' + '---:|' * 6 + '---|' + '---:|' * 6]
    enc_cob = ['| año | evento | series | con base (días) | base suficiente | con previo (días) | con evento (días) | '
               'cobertura ahorro | cobertura alza |', '|---|---|' + '---:|' * 7]
    for fuente, titulo in ((FUENTE_CDMX, 'CDMX'), (FUENTE_NACIONAL, 'Nacional (todas las entidades)')):
        filas = [M[(fuente, a)] for a in anios if M[(fuente, a)]]
        L += ['', f'## {titulo}: observaciones por año', ''] + encabezado + [fila_recorte(m) for m in filas]
        cuadra = all(m['auditoria'] in (None, m['crudas']) for m in filas)
        homon = ', '.join(f"{m['anio']}: {m['homonimas']} ({_n(m['colapsarian'])} filas)" for m in filas)
        L += ['', f"Filas crudas = limpias + exclusiones; {'coinciden' if cuadra else '**NO coinciden**'} con el conteo "
              'por CSV de `qqp_auditoria` en todos los años. Inválidos entre paréntesis: fecha / precio / identidad '
              '(una fila puede tener más de un motivo).', '',
              'Pares cadena + nombre comercial con más de un `sucursal_id` (y filas que colapsarían en la CLAVE si '
              f'`vendedor_o_cadena` no incluyera `sucursal_id`): {homon}.', '',
              f'### {titulo}: series con cobertura para el Buen Fin del mismo año', ''] + enc_cob
        L += [fila_cobertura(m) for m in filas]
    L += ['', 'Reglas (Avance 1): cobertura de ahorro = ≥4 fechas en la base que abarquen ≥21 días y ≥1 fecha en el '
          'evento; cobertura de alza = además ≥2 fechas en el previo. Base D−60…D−15, previo D−14…D−1, evento D0…fin. '
          '"Base suficiente" = sólo la condición de base (útil para el año en curso). Entre paréntesis: días '
          'distintos con algún dato en esa ventana.', '']
    if 2026 in anios and M[(FUENTE_CDMX, 2026)]:
        m, e = M[(FUENTE_CDMX, 2026)], ev.loc['BF2026']
        mn = M[(FUENTE_NACIONAL, 2026)]
        rc, ini, fin = series_con_base_reciente(FUENTE_CDMX, 2026)
        rn, _, _ = series_con_base_reciente(FUENTE_NACIONAL, 2026)
        ultimo = _leer('qqp_auditoria', '2026').archivo.iloc[-1]
        L += ['## 2026: base previa al Buen Fin 2026', '',
              f"El archivo 2026 publicado hoy llega sólo hasta **{m['fecha_max']}** (CDMX; nacional: {mn['fecha_max']}; "
              f"último CSV `{ultimo}`). Ventana base BF2026: {e.base_inicio.date()} – {e.base_fin.date()} "
              f"(evento {e.d0.date()} – {e.fin.date()}; fechas de eventos.yaml: {e.fuente_fechas}). Por lo tanto la "
              f"base BF2026 tiene **{_n(m['series_con_base'])} series** con dato en CDMX ({_n(m['dias_base'])} días) "
              f"y {_n(mn['series_con_base'])} a nivel nacional: el archivo todavía NO trae la base previa al BF2026. "
              f"Diagnóstico: en los últimos 60 días del archivo ({ini} – {fin}) ya hay {_n(rc)} series CDMX y "
              f"{_n(rn)} nacionales con ≥4 fechas en ≥21 días; si PROFECO publica septiembre–octubre con un muestreo "
              'similar, ese es el orden de magnitud esperable. `diario` detecta la versión nueva del RAR y re-extrae.',
              '']
    L += ['## Fechas del Buen Fin usadas', '', '| evento | inicio | fin | fuente de las fechas |', '|---|---|---|---|']
    L += [f'| {i} | {r.d0.date()} | {r.fin.date()} | {r.fuente_fechas} |' for i, r in ev.iterrows()]
    L += ['', 'BF2018–BF2023 no están en `config/eventos.yaml`; se toman de `EVENTOS_HISTORICOS` (qqp.py) con la '
          'fuente de prensa indicada, que cita el anuncio de la Secretaría de Economía. El orquestador debe pasarlas a '
          'eventos.yaml. BF2020 duró 12 días por la pandemia y BF2021 7 días: la ventana de evento es más larga.', '',
          '## Búsqueda de años 2018–2023', '',
          '- `qqp.php` (página actual) sólo lista 2024, 2025 y 2026, más metadatos y diccionario.',
          '- Wayback Machine: el CDX de `qqp.php` tiene capturas de 2023-12-04 a 2025-12-08; las de 2023-12 a 2025-12 '
          'listan "Base de Datos Histórica Quién es Quién en los Precios" 2015–2023 con sus enlaces `file.php?t=...`. '
          'Esos enlaces **siguen respondiendo hoy en el servidor oficial** con `application/x-rar` '
          '(`QQP_<año>.rar`). Se descargaron 2018–2023 desde datos.profeco.gob.mx (no desde Wayback); el manifiesto '
          'de cada RAR guarda la URL oficial, la captura donde se halló el enlace, bytes y SHA-256. 2015–2017 también '
          'existen, pero quedan fuera del alcance pedido.',
          '- Portal de históricos (`profeco.gob.mx/precios/canasta/Dato_historico.aspx`): la base 1999+ sólo se '
          'entrega por solicitud escrita (formulario o correo a quienesquien@profeco.gob.mx); no hay descarga directa. '
          'No se envió ninguna solicitud.',
          '- datos.gob.mx (API CKAN y ficha del conjunto): respondió 403 a nuestro user-agent; no se insistió.',
          '- datamx.io: el conjunto "Quién es Quién en los precios" sólo enlaza un CSV en Google Drive actualizado en '
          '2018-06 (histórico desde 2015) y una API de datos.gob.mx ya retirada; no aporta 2018–2023 completos.',
          '- Los crudos de cada consulta están en `data/raw/qqp/2026-10-16/` y `data/raw/qqp/wayback/`.', '',
          '## Diferencias de formato entre años', '',
          '- 2024–2026: CSV con cabecera; 2018–2023: sin cabecera (mismas 15 columnas en el mismo orden). '
          '`fila_origen` es el número de línea del CSV en ambos casos.',
          '- 2018–2022: un CSV por semana (`NNAAAA.csv`); 2023–2025: dos por mes; 2026: `MM-2026_Q1/Q2`.',
          '- 2018–2023 vienen en MAYÚSCULAS; `normalizar` iguala mayúsculas/acentos, pero los `producto_id` de años '
          'distintos pueden diferir si PROFECO cambió la redacción de la presentación: el empate entre años se hace '
          'después por `modelo_normalizado`, no por `producto_id`.', '',
          '## Límites', '',
          '- QQP muestrea de forma esporádica: faltan días por serie y no hay precio diario; un día sin dato es faltante.',
          '- Precio registrado en tienda física por verificadores de PROFECO; QQP no publica precio anterior ni '
          'porcentaje de descuento (esas columnas quedan vacías).',
          '- Identidad provisional (texto de producto+marca+presentación), no EAN/GTIN.',
          '- Filas con fecha de otro año dentro de un archivo (p. ej. la semana 53) se excluyen como inválidas, igual '
          'que en el Avance 1; quedan en `*_exclusiones`.', '',
          '## Verificado / pendiente', '',
          '- Verificado: reproducción exacta del Avance 1 (tabla arriba); CLAVE única, precio > 0 y fechas válidas en '
          'cada tabla bronze (`validar_observaciones` y tests); filas crudas = limpias + exclusiones = auditoría por CSV.',
          '- Pendiente: pasar BF2018–BF2023 a `config/eventos.yaml`; re-extraer 2026 cuando PROFECO publique la versión '
          'con noviembre; emparejar `modelo_normalizado` con la lista fija de productos.', '',
          '## Comandos', '', '```',
          'python -m sconto.fuentes.qqp backfill --anios 2018 2019 2020 2021 2022 2023 2024 2025 2026   # reanudable',
          'python -m sconto.fuentes.qqp diario        # detecta versión nueva de 2026 y re-extrae',
          'python -m sconto.fuentes.qqp reproduccion  # compara 2025 con el Avance 1',
          'python -m sconto.fuentes.qqp reporte', '```', '']
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text('\n'.join(L), encoding='utf-8')
    return ruta


def main(argv=None):
    ap = argparse.ArgumentParser(description='PROFECO QQP: archivos anuales oficiales → bronze')
    sub = ap.add_subparsers(dest='orden', required=True)
    sub.add_parser('enlaces', help='lista los archivos publicados en la página oficial')
    for nombre in ('descargar', 'extraer', 'backfill'):
        p = sub.add_parser(nombre)
        p.add_argument('--anios', type=int, nargs='+', default=None)
        p.add_argument('--sin-nacional', action='store_true')
        p.add_argument('--forzar', action='store_true')
        p.add_argument('--entorno', default='local')
    p = sub.add_parser('diario')
    p.add_argument('--entorno', default='local')
    sub.add_parser('historicos', help='busca QQP 2018–2023 en PROFECO y espejos gratuitos')
    sub.add_parser('reproduccion', help='compara el bronze 2025 con el Avance 1')
    sub.add_parser('reporte', help='escribe reports/cobertura_qqp.md desde el bronze')
    a = ap.parse_args(argv)
    asegurar_directorios()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOGS / f'qqp_{hoy()}.log', encoding='utf-8')])
    if a.orden == 'enlaces':
        print(json.dumps(leer_pagina()[0], ensure_ascii=False, indent=2))
    elif a.orden == 'descargar':
        cliente = Cliente()
        enlaces = leer_pagina(cliente)[0]
        for anio in a.anios or sorted(enlaces['anios']):
            print(anio, descargar(anio, cliente, forzar=a.forzar, enlaces=enlaces))
    elif a.orden == 'extraer':
        for anio in a.anios or [2025]:
            print(json.dumps(extraer(anio, nacional=not a.sin_nacional), ensure_ascii=False, indent=2, default=str))
    elif a.orden == 'backfill':
        print(json.dumps(backfill(a.anios, nacional=not a.sin_nacional, entorno=a.entorno,
                                  forzar_extraccion=a.forzar), ensure_ascii=False, indent=2, default=str))
    elif a.orden == 'diario':
        print(json.dumps(diario(entorno=a.entorno), ensure_ascii=False, indent=2, default=str))
    elif a.orden == 'historicos':
        print(json.dumps(historicos(), ensure_ascii=False, indent=2, default=str))
    elif a.orden == 'reproduccion':
        print(json.dumps(reproduccion_avance1(), ensure_ascii=False, indent=2, default=str))
    elif a.orden == 'reporte':
        print(escribir_reporte())


if __name__ == '__main__':
    main()
