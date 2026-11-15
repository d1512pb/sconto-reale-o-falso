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
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

from sconto.cliente import Bloqueado, Cliente, NoPermitido
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


def _url_producto(categoria, producto):
    return f'{API}/producto/10/{categoria}/0/{producto}'


def _guardar_respuesta(ruta, nombre, respuesta):
    datos = respuesta.content
    registro = dict(
        url=respuesta.url, fetched_at_utc=datetime.now(timezone.utc).isoformat(),
        http=respuesta.status_code, bytes=len(datos), sha256=hashlib.sha256(datos).hexdigest(),
    )
    with gzip.open(ruta / f'{nombre}.gz', 'xb') as archivo:
        archivo.write(datos)
    with (ruta / f'{nombre}.json').open('x', encoding='utf-8') as archivo:
        json.dump(registro, archivo)
    return registro


def _capturar(cliente, ruta, nombre, url):
    meta = ruta / f'{nombre}.json'
    crudo = ruta / f'{nombre}.gz'
    if meta.exists() or crudo.exists():
        if meta.exists() and crudo.exists():
            _leer(ruta, nombre, url)
            return
        raise FileExistsError(f'Captura incompleta; conservar evidencia y utilizar otro directorio: {nombre}')
    with cliente.get(url) as respuesta:
        if respuesta.status_code == 200:
            _guardar_respuesta(ruta, nombre, respuesta)
            return
        _guardar_respuesta(ruta, f'{nombre}_http_{respuesta.status_code}', respuesta)
        respuesta.raise_for_status()
        raise ValueError(f'PROFECO HTTP no utilizable: {respuesta.status_code}')


def _consultar(ruta, destinos):
    ruta.mkdir(parents=True, exist_ok=True)
    if (ruta / 'bf_suspension.json').exists():
        raise RuntimeError('La bitácora de esta pasada contiene una suspensión')
    cliente = Cliente(reintentos=0, timeout=(10, 35))
    for nombre, url in destinos:
        try:
            _capturar(cliente, ruta, nombre, url)
        except (Bloqueado, NoPermitido) as exc:
            if isinstance(exc, Bloqueado) and exc.respuesta is not None:
                _guardar_respuesta(ruta, f'{nombre}_bloqueo', exc.respuesta)
            with (ruta / 'bf_suspension.json').open('x', encoding='utf-8') as archivo:
                json.dump({
                    'fetched_at_utc': datetime.now(timezone.utc).isoformat(),
                    'url': url, 'error': str(exc),
                }, archivo)
            raise
        except requests.RequestException as exc:
            with (ruta / 'bf_fallos.jsonl').open('a', encoding='utf-8') as archivo:
                archivo.write(json.dumps({
                    'fetched_at_utc': datetime.now(timezone.utc).isoformat(),
                    'url': url, 'error': type(exc).__name__,
                }) + '\n')
            print(f'{nombre}: {type(exc).__name__}')


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

