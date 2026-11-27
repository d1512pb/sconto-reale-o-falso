"""Registra el historial diario de las consultas oficiales archivadas del Buen Fin."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from sconto.fuentes.profeco_buenfin import API, CATALOGOS, _historico, _leer, _url_producto, consolidar_observaciones
from sconto.intraday import CDMX, RAIZ_INTRADIA, IntradayStore, Observacion, Oferta, Trabajo
from sconto.rutas import RAW

FUENTE = 'profeco_buen_fin'


def _leer_captura(directorio: Path, nombre: str, url_esperada: str):
    archivo = (directorio / (nombre + '.gz')).resolve(strict=True)
    if not archivo.is_relative_to(directorio):
        raise ValueError('La referencia cruda sale del archivo del piloto')
    meta = json.loads((directorio / (nombre + '.json')).read_bytes())
    crudo = gzip.decompress(archivo.read_bytes())
    hora = datetime.fromisoformat(meta['fetched_at_utc'])
    if (meta['sha256'] != hashlib.sha256(crudo).hexdigest() or meta['bytes'] != len(crudo)
            or hora.utcoffset() is None or meta['url'] != url_esperada):
        raise ValueError('Los metadatos no corresponden a la captura original')
    return archivo, crudo, hora, meta


def _catalogo(directorio: Path) -> dict[int, tuple[int, dict]]:
    productos = {}
    for categoria, nombre in CATALOGOS.items():
        catalogo, _, _ = _leer(directorio, nombre, f'{API}/productos/10/{categoria}')
        for producto in catalogo['data']:
            clave = int(producto['id_producto'])
            if clave in productos and productos[clave] != (categoria, producto):
                raise ValueError(f'Conflicto de identidad del producto {clave} en catálogo oficial')
            productos[clave] = categoria, producto
    return productos


def _sucursal(fila: dict) -> str:
    partes = [' '.join(fila[clave].casefold().split()) for clave in ('sucursal', 'direccion')]
    return hashlib.sha256('\n'.join(partes).encode()).hexdigest()


def _precios(crudo: bytes, ruta: Path, meta: dict, producto_id: int, producto: dict,
             categoria: int, hora: datetime) -> tuple[list[Observacion], int, list[dict]]:
    filas = _historico(producto, producto_id, categoria, json.loads(crudo), meta, ruta)
    limpias, descartadas = consolidar_observaciones(filas)
    observaciones = []
    for fila in limpias:
        dia = date.fromisoformat(fila['fecha_precio'])
        if dia > hora.astimezone(CDMX).date():
            raise ValueError('El historial contiene una fecha futura')
        oferta = Oferta(f'{producto_id}:{_sucursal(fila)}', f'PROFECO-BF26-{producto_id}', 'Sucursal física',
                        meta['url'], variante=str(producto_id), vendedor=fila['sucursal'])
        observaciones.append(Observacion(oferta, float(fila['precio_mxn']), 'MXN',
                                         precision_temporal='dia', fecha_precio=dia, condiciones={
                                             'zona_consulta': 'plaza CDMX/ZMVM', 'canal': 'fisico',
                                             'marca': fila['marca'], 'descripcion': fila['descripcion'],
                                         }))
    duplicados = sum(fila['motivo'] == 'duplicado_identico' for fila in descartadas)
    conflictos = [dict(sucursal=_sucursal(fila), fecha=fila['fecha_precio'], precio=fila['precio_mxn'],
                       motivo=fila['motivo']) for fila in descartadas if fila['motivo'] != 'duplicado_identico']
    return observaciones, duplicados, conflictos


def importar(origen: Path, store: IntradayStore) -> dict:
    origen = origen.resolve(strict=True)
    productos = _catalogo(origen)
    resumen = dict(importadas=0, repetidas=0, precios=0, precios_buen_fin=0, duplicados=0,
                   productos_buen_fin=[], conflictos=[], rechazadas=[])
    patron_meta = r'bf_cdmx_producto_(\d+)(?:_[\w-]+)?\.json'
    for archivo in sorted(origen.rglob('bf_cdmx_producto_*.json')):
        m = re.fullmatch(patron_meta, archivo.name)
        if m is None:
            continue
        producto_id = int(m[1])
        nombre = archivo.relative_to(origen).as_posix()
        try:
            categoria, producto = productos[producto_id]
            url = _url_producto(categoria, producto_id)
            ruta, crudo, hora, meta = _leer_captura(archivo.parent, archivo.stem, url)
            http = meta['http']
            if http == 200:
                observaciones, duplicados, conflictos = _precios(crudo, ruta, meta, producto_id, producto, categoria, hora)
            else:
                observaciones, duplicados, conflictos = [], 0, []
            resumen['conflictos'].extend(dict(conflicto, archivo=nombre) for conflicto in conflictos)
            trabajo = Trabajo(FUENTE, url, hora, max_intentos=2)
            captura = store.tomar(trabajo)
            if captura is None:
                if store.resultado_trabajo(trabajo) in {None, 'interrumpido'}:
                    raise ValueError('La captura previa sigue incompleta')
                resumen['repetidas'] += 1
                continue
            if http in {401, 403, 429, 503} or 300 <= http < 400:
                resultado = 'bloqueado'
            else:
                resultado = 'ok' if observaciones else ('sin_oferta' if http == 200 else 'fallo')
            store.registrar(captura, fetched_at=hora, resultado=resultado, crudo=crudo, estado_http=http,
                            observaciones=observaciones, crudo_preexistente=ruta, diario_publicado=True,
                            version_colector='archivo-profeco-bf-v1', registrado_at=datetime.now(timezone.utc),
                            ultimo_error=None if http == 200 else f'HTTP {http}')
            durante = sum(date(2026, 11, 13) <= fila.fecha_precio <= date(2026, 11, 17) for fila in observaciones)
            resumen['importadas'] += 1
            resumen['precios'] += len(observaciones)
            resumen['precios_buen_fin'] += durante
            resumen['duplicados'] += duplicados
            if durante:
                resumen['productos_buen_fin'].append(producto_id)
        except (KeyError, TypeError, ValueError, OSError, EOFError) as error:
            resumen['rechazadas'].append(dict(archivo=nombre, motivo=f'{type(error).__name__}: {error}'))
    resumen['productos_buen_fin'] = sorted(set(resumen['productos_buen_fin']))
    return resumen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origen', type=Path, default=RAW / 'piloto_p0_v2')
    parser.add_argument('--salida', type=Path, default=RAIZ_INTRADIA)
    argumentos = parser.parse_args(argv)
    store = IntradayStore(argumentos.salida)
    with store.exclusividad_colector() as permiso:
        if not permiso:
            parser.error('Ya existe un recolector usando el almacén')
        store.vencidos()
        resultado = importar(argumentos.origen, store)
    print(json.dumps(dict(resultado, almacen=store.estado()), ensure_ascii=False))
    return bool(resultado['rechazadas'])


if __name__ == '__main__':
    raise SystemExit(main())
