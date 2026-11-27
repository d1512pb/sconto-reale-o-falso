"""Muestra fija de la consulta pública del Buen Fin de PROFECO para la plaza CDMX.

Los precios se refieren al día del levantamiento en un establecimiento físico.
La hora UTC de descarga acredita la consulta a PROFECO. Los historiales no
contienen hora de levantamiento, versión, ID numérico de sucursal ni stock.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import os
from pathlib import Path

import requests

from sconto.cliente import MARCAS_CAPTCHA, Bloqueado, Cliente, NoPermitido
from sconto.rutas import RAIZ

API = 'https://elbuenfin.profeco.gob.mx/api/get'
RAW = RAIZ / 'data' / 'raw' / 'piloto_p0_v2'
OUT = RAIZ / 'data' / 'analitica' / 'piloto_p0_v2'
MUESTRA = {
    4: (35250, 35251, 35252, 36107, 36128, 36779, 36780, 37111, 37112),
    1: (37105, 37106, 37107, 37108, 37109, 37110, 33046, 35320, 29627, 33045,
        34471, 35051, 35270, 35955, 36760),
}
CATALOGOS = {4: 'bf_cdmx_computo', 1: 'bf_cdmx_audio'}
CP = re.compile(r'\bC\.?\s*P\.?\s*:?\s*(\d{5})\b', re.I)
CAMPOS = (
    'producto_profeco_id', 'categoria_profeco_id', 'tipo_producto', 'marca',
    'descripcion', 'sucursal', 'direccion', 'cp_sucursal', 'zona_sucursal',
    'fecha_precio', 'precio_mxn', 'consultado_utc', 'url', 'hash_raw', 'ruta_raw',
)
MAX_RESPUESTA = 2 * 1024 * 1024


def _url_producto(categoria, producto):
    return f'{API}/producto/10/{categoria}/0/{producto}'


def reintento_desde(error, ahora):
    respuesta = getattr(error, 'respuesta', None)
    if respuesta is None or respuesta.status_code not in {429, 503}:
        return None
    indicacion = respuesta.headers.get('Retry-After', '').strip()
    try:
        if indicacion.isascii() and indicacion.isdigit():
            fecha = ahora + timedelta(seconds=int(indicacion))
        else:
            fecha = parsedate_to_datetime(indicacion)
            if fecha.utcoffset() is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
        return max(ahora, fecha.astimezone(timezone.utc)).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def _sincronizar(archivo):
    archivo.flush()
    os.fsync(archivo.fileno())


def _completar_par(ruta, nombre):
    """Si ambos archivos llegaron al disco, finaliza una publicación interrumpida."""
    meta = ruta / f'{nombre}.json'
    cuerpo = ruta / f'{nombre}.gz'
    meta_pendiente = meta.with_suffix('.json.part')
    cuerpo_pendiente = cuerpo.with_suffix('.gz.part')
    if meta.exists() or not meta_pendiente.exists():
        return
    candidato = cuerpo if cuerpo.exists() else cuerpo_pendiente
    registro = json.loads(meta_pendiente.read_bytes())
    with gzip.open(candidato, 'rb') as archivo:
        datos = archivo.read(MAX_RESPUESTA + 1)
    if (len(datos) != registro['bytes'] or len(datos) > MAX_RESPUESTA
            or hashlib.sha256(datos).hexdigest() != registro['sha256']):
        raise ValueError('La respuesta interrumpida no pasó la verificación')
    if not cuerpo.exists():
        cuerpo_pendiente.replace(cuerpo)
    meta_pendiente.replace(meta)


def _guardar_respuesta(ruta, nombre, respuesta, datos=None):
    datos = respuesta.content if datos is None else datos
    if len(datos) > MAX_RESPUESTA:
        raise ValueError('Respuesta oficial por encima del tamaño admitido')
    registro = dict(
        url=respuesta.url, fetched_at_utc=datetime.now(timezone.utc).isoformat(),
        http=respuesta.status_code, bytes=len(datos), sha256=hashlib.sha256(datos).hexdigest(),
    )
    with (ruta / f'{nombre}.gz.part').open('xb') as archivo:
        archivo.write(gzip.compress(datos, mtime=0))
        _sincronizar(archivo)
    with (ruta / f'{nombre}.json.part').open('x', encoding='utf-8') as archivo:
        json.dump(registro, archivo)
        _sincronizar(archivo)
    _completar_par(ruta, nombre)
    return registro


def _capturar(cliente, ruta, nombre, url):
    _completar_par(ruta, nombre)
    meta = ruta / f'{nombre}.json'
    crudo = ruta / f'{nombre}.gz'
    if meta.exists() or crudo.exists():
        if meta.exists() and crudo.exists():
            _leer(ruta, nombre, url)
            return
        raise FileExistsError(f'Captura incompleta; conservar evidencia y utilizar otro directorio: {nombre}')
    if (ruta / f'{nombre}.gz.part').exists():
        # La respuesta parcial queda en el volumen, sin ostentar una consulta completa.
        pendiente = ruta / f'{nombre}.gz.part'
        etiqueta = datetime.now(timezone.utc).strftime('%H%M%S%f')
        pendiente.rename(ruta / f'{nombre}_{etiqueta}.incompleto')
    def verificar_redireccion(respuesta, *args, **kwargs):
        if respuesta.status_code == 401 or 300 <= respuesta.status_code < 400:
            raise Bloqueado(f'HTTP {respuesta.status_code} en la consulta oficial', respuesta)

    with cliente.get(url, stream=True, hooks={'response': verificar_redireccion}) as respuesta:
        datos = bytearray()
        for segmento in respuesta.iter_content(65536):
            datos.extend(segmento)
            if len(datos) > MAX_RESPUESTA:
                raise ValueError('Respuesta oficial por encima del tamaño admitido')
        contenido = bytes(datos)
        if 'html' in respuesta.headers.get('content-type', '').casefold():
            pagina = contenido[:20000].decode('utf-8', errors='replace').casefold()
            if any(marca in pagina for marca in MARCAS_CAPTCHA):
                _guardar_respuesta(ruta, f'{nombre}_bloqueo', respuesta, contenido)
                raise Bloqueado(f'CAPTCHA en la consulta oficial: {url}')
        if respuesta.status_code == 200:
            _guardar_respuesta(ruta, nombre, respuesta, contenido)
            return
        etiqueta = datetime.now(timezone.utc).strftime('%H%M%S%f')
        _guardar_respuesta(ruta, f'{nombre}_http_{respuesta.status_code}_{etiqueta}', respuesta, contenido)
        respuesta.raise_for_status()
        raise ValueError(f'PROFECO HTTP no utilizable: {respuesta.status_code}')


def _consultar(ruta, destinos):
    ruta.mkdir(parents=True, exist_ok=True)
    if (ruta / 'bf_suspension.json').exists():
        raise RuntimeError('La bitácora de esta pasada contiene una suspensión')
    cliente = Cliente(reintentos=0, timeout=(10, 35), detectar_captcha=False)
    try:
        for nombre, url in destinos:
            try:
                _capturar(cliente, ruta, nombre, url)
            except (Bloqueado, NoPermitido) as exc:
                ahora = datetime.now(timezone.utc)
                with (ruta / 'bf_suspension.json').open('x', encoding='utf-8') as archivo:
                    json.dump({
                        'fetched_at_utc': ahora.isoformat(), 'siguiente_utc': reintento_desde(exc, ahora),
                        'url': url, 'error': type(exc).__name__,
                    }, archivo)
                    _sincronizar(archivo)
                if isinstance(exc, Bloqueado) and exc.respuesta is not None:
                    with exc.respuesta as respuesta:
                        datos = respuesta.raw.read(MAX_RESPUESTA + 1, decode_content=True)
                        if len(datos) <= MAX_RESPUESTA:
                            _guardar_respuesta(ruta, f'{nombre}_bloqueo', respuesta, datos)
                raise
            except requests.RequestException as exc:
                with (ruta / 'bf_fallos.jsonl').open('a', encoding='utf-8') as archivo:
                    archivo.write(json.dumps({
                        'fetched_at_utc': datetime.now(timezone.utc).isoformat(),
                        'url': url, 'error': type(exc).__name__,
                    }) + '\n')
                print(f'{nombre}: {type(exc).__name__}')
    finally:
        cliente.sesion.close()


def capturar(ruta):
    destinos = [(nombre, f'{API}/productos/10/{categoria}') for categoria, nombre in CATALOGOS.items()]
    destinos.extend(
        (f'bf_cdmx_producto_{producto}', _url_producto(categoria, producto))
        for categoria, productos in MUESTRA.items() for producto in productos
    )
    _consultar(ruta, destinos)


def reconsultar(ruta, producto):
    categoria = next(categoria for categoria, ids in MUESTRA.items() if producto in ids)
    nombre = f'bf_cdmx_producto_{producto}'
    _consultar(ruta, [(nombre, _url_producto(categoria, producto))])
    _, meta, _ = _leer(ruta, nombre, _url_producto(categoria, producto))
    print(json.dumps(meta))


def _leer(ruta, nombre, url):
    meta = json.loads((ruta / f'{nombre}.json').read_text(encoding='utf-8'))
    crudo = ruta / f'{nombre}.gz'
    datos = gzip.decompress(crudo.read_bytes())
    consulta = datetime.fromisoformat(meta['fetched_at_utc'])
    if consulta.utcoffset() != timezone.utc.utcoffset(consulta):
        raise ValueError(f'Consulta sin fecha UTC: {nombre}')
    if (
        meta['http'] != 200 or meta['url'] != url or meta['bytes'] != len(datos)
        or meta['sha256'] != hashlib.sha256(datos).hexdigest()
    ):
        raise ValueError(f'Captura no válida: {nombre}')
    return json.loads(datos), meta, crudo


def _zona(direccion):
    coincidencia = CP.search(direccion)
    if coincidencia is None:
        return '', 'sin_CP_verificable'
    cp = coincidencia.group(1)
    if 1000 <= int(cp) <= 16999:
        return cp, 'CDMX_CP'
    if 50000 <= int(cp) <= 57999:
        return cp, 'Edomex_CP'
    return cp, 'otro_CP'


def _historico(catalogo, producto, categoria, registro, meta, crudo):
    datos = registro.get('data') if isinstance(registro, dict) else registro
    if not isinstance(datos, list):
        raise ValueError(f'Historial de objeto {producto} sin sucursales válidas')
    for ubicacion in datos:
        sucursal, direccion = ubicacion['estacion'].strip(), ubicacion['direccion'].strip()
        if not sucursal or not direccion:
            raise ValueError(f'Identidad de sucursal incompleta para producto {producto}')
        cp, zona = _zona(direccion)
        for punto in ubicacion['historial']:
            try:
                precio = Decimal(str(punto['precio']))
                fecha = date.fromisoformat(punto['fecha'])
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f'Precio inválido para producto {producto}') from exc
            if not precio.is_finite() or precio <= 0:
                raise ValueError(f'Precio no positivo o no finito para producto {producto}')
            yield dict(
                producto_profeco_id=producto, categoria_profeco_id=categoria,
                tipo_producto=catalogo['tipo_producto'], marca=catalogo['marca'],
                descripcion=catalogo['descripcion'], sucursal=sucursal, direccion=direccion,
                cp_sucursal=cp, zona_sucursal=zona, fecha_precio=fecha.isoformat(),
                precio_mxn=str(precio), consultado_utc=meta['fetched_at_utc'], url=meta['url'],
                hash_raw=meta['sha256'],
                ruta_raw=crudo.relative_to(RAIZ).as_posix() if crudo.is_relative_to(RAIZ) else str(crudo),
            )


def observaciones(ruta):
    filas = []
    faltantes = []
    for categoria, nombre in CATALOGOS.items():
        datos, _, _ = _leer(ruta, nombre, f'{API}/productos/10/{categoria}')
        catalogo = {p['id_producto']: p for p in datos['data']}
        for producto in MUESTRA[categoria]:
            archivo = f'bf_cdmx_producto_{producto}'
            if not (ruta / f'{archivo}.json').exists():
                faltantes.append(str(producto))
                continue
            datos, meta, crudo = _leer(ruta, archivo, _url_producto(categoria, producto))
            filas.extend(_historico(catalogo[producto], producto, categoria, datos, meta, crudo))
    return filas, faltantes


def consolidar_observaciones(filas):
    grupos = defaultdict(list)
    for fila in filas:
        sucursal = ' '.join(fila['sucursal'].casefold().split())
        direccion = ' '.join(fila['direccion'].casefold().split())
        clave = fila['producto_profeco_id'], sucursal, direccion, fila['fecha_precio']
        grupos[clave].append(fila)
    limpias, descartadas = [], []
    for grupo in grupos.values():
        precios = {Decimal(fila['precio_mxn']) for fila in grupo}
        if len(precios) > 1:
            descartadas.extend(dict(fila, motivo='precios_distintos_misma_sucursal_fecha') for fila in grupo)
        else:
            limpias.append(grupo[0])
            descartadas.extend(dict(fila, motivo='duplicado_identico') for fila in grupo[1:])
    return limpias, descartadas


def _escribir_csv(destino, filas, campos):
    temporal = destino.with_suffix('.tmp')
    with temporal.open('w', newline='', encoding='utf-8') as archivo:
        escritor = csv.DictWriter(archivo, campos)
        escritor.writeheader()
        escritor.writerows(filas)
    temporal.replace(destino)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crudos', type=Path, default=RAW)
    parser.add_argument('--salida', type=Path, default=OUT)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument('--capturar', action='store_true', help='Consultar una vez la muestra explícita')
    modo.add_argument('--reconsultar', type=int, choices=tuple(p for ids in MUESTRA.values() for p in ids),
                      help='Consultar una sola ficha y conservar la respuesta bajo --crudos')
    args = parser.parse_args(argv)
    if args.reconsultar:
        if args.crudos.resolve() == RAW:
            parser.error('--reconsultar requiere un directorio --crudos aparte de la muestra original')
        reconsultar(args.crudos.resolve(), args.reconsultar)
        return 0
    if args.capturar:
        capturar(args.crudos.resolve())
    filas, faltantes = observaciones(args.crudos.resolve())
    limpias, descartadas = consolidar_observaciones(filas)
    args.salida.mkdir(parents=True, exist_ok=True)
    destino = args.salida / 'profeco_bf2026_observaciones.csv'
    _escribir_csv(destino, limpias, CAMPOS)
    _escribir_csv(args.salida / 'profeco_bf2026_exclusiones.csv', descartadas, CAMPOS + ('motivo',))
    print(f'{len(limpias)} observaciones comparables en {destino}; {len(descartadas)} exclusiones')
    if faltantes:
        print(f'{len(faltantes)} productos sin captura: {", ".join(faltantes)}')
    return 2 if faltantes else 0


if __name__ == '__main__':
    raise SystemExit(main())

