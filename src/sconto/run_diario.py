"""Colector diario idempotente: correrlo dos veces el mismo día no duplica nada.

    python -m sconto.run_diario --entorno github
    python -m sconto.run_diario --entorno local --fuentes amazon
    python -m sconto.run_diario --entorno local --solo-si-falta   # reintento de lo que GitHub no logró hoy

Cada fuente: crudo comprimido en data/raw/, filas en data/bronze/, estado en data/estado/<entorno>.csv.
Un día sin dato es un faltante: nunca se imputa.
"""
from __future__ import annotations

import argparse
import importlib
import logging
import json
import sys
import traceback

import pandas as pd
import yaml

from sconto.almacen import ahora_utc, combinar_estados, hoy, registrar_estado, revisar_alertas
from sconto.eventos import en_temporada_doble
from sconto.rutas import CONFIG, ESTADO_FUENTES, LOGS, asegurar_directorios

log = logging.getLogger('run_diario')


def cargar_productos() -> pd.DataFrame:
    return pd.read_csv(CONFIG / 'productos_objetivo.csv', dtype=str, keep_default_na=False).assign(
        prioridad=lambda d: pd.to_numeric(d.prioridad))


def ya_ok_hoy(fuente: str, fecha: str) -> bool:
    combinar_estados()  # trae lo que haya registrado el otro entorno (tras git pull)
    if not ESTADO_FUENTES.exists():
        return False
    e = pd.read_csv(ESTADO_FUENTES, dtype=str)
    return bool(((e.fuente == fuente) & (e.fecha == fecha) & e.estado.isin(['ok'])).any())


def ya_intentada(fuente: str, fecha: str, entorno: str) -> bool:
    combinar_estados()
    if not ESTADO_FUENTES.exists():
        return False
    estados = pd.read_csv(ESTADO_FUENTES, dtype=str)
    return bool(((estados.fuente == fuente) & (estados.fecha == fecha) &
                 (estados.entorno == entorno) & estados.estado.isin(['ok', 'bloqueado', 'sin_credenciales'])).any())


def seleccionar_productos(productos: pd.DataFrame, fuente: str, maximo: int | None) -> pd.DataFrame:
    columnas = {'preciometro': ['preciometro_ids'], 'mercadolibre': ['mlm_ids', 'mlm_item_ids'],
                'amazon': ['asins']}.get(fuente, [])
    if columnas:
        seleccion = pd.Series(False, index=productos.index)
        for columna in columnas:
            if columna in productos:
                seleccion |= productos[columna].fillna('').ne('')
        productos = productos.loc[seleccion]
    return productos.head(maximo) if maximo else productos


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--entorno', choices=['github', 'local'], default='local')
    ap.add_argument('--fuentes', nargs='*', help='Subconjunto de fuentes (por defecto, las del entorno).')
    ap.add_argument('--solo-si-falta', action='store_true',
                    help='Omite fuentes que ya tienen estado ok hoy en cualquier entorno.')
    ap.add_argument('--pasada', type=int, choices=[1, 2], default=1)
    ap.add_argument('--plan', action='store_true', help='Muestra qué se ejecutaría, sin red ni escritura de datos.')
    ap.add_argument('--max-productos', type=int, default=None, help='Limita una prueba a N productos canónicos.')
    a = ap.parse_args(argv)
    asegurar_directorios()
    fecha = hoy()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOGS / f'run_diario_{fecha}_{a.entorno}.log', encoding='utf-8')])
    cfg = yaml.safe_load((CONFIG / 'fuentes.yaml').read_text(encoding='utf-8'))['fuentes']
    if a.fuentes and set(a.fuentes) - set(cfg):
        ap.error('Fuentes desconocidas: ' + ', '.join(sorted(set(a.fuentes) - set(cfg))))
    if a.max_productos is not None and a.max_productos < 1:
        ap.error('--max-productos debe ser positivo')
    productos = cargar_productos()
    resumen = {}
    for nombre, c in cfg.items():
        if a.fuentes and nombre not in a.fuentes:
            continue
        if not c.get('habilitada', True):
            resumen[nombre] = {'estado': 'deshabilitada', 'motivo': c.get('motivo', '')}
            continue
        if not a.fuentes and a.entorno not in c['entornos']:
            continue
        if a.pasada == 2 and not (en_temporada_doble() and c.get('pasadas_temporada', 1) >= 2):
            continue
        objetivos = seleccionar_productos(productos, nombre, None if nombre == 'preciometro' else a.max_productos)
        if a.plan:
            resumen[nombre] = {'modulo': c['modulo'], 'productos_catalogo': len(objetivos),
                               'limite_prueba': a.max_productos, 'entorno': a.entorno}
            continue
        if ya_intentada(nombre, fecha, a.entorno):
            resumen[nombre] = {'estado': 'omitida', 'motivo': 'ya capturada o bloqueada en este entorno hoy'}
            continue
        if a.solo_si_falta and ya_ok_hoy(nombre, fecha):
            log.info('%s ya está ok hoy; se omite', nombre)
            continue
        inicio = ahora_utc()
        try:
            modulo = importlib.import_module(c['modulo'])
            opciones = {'max_urls': a.max_productos} if nombre == 'preciometro' else {}
            resumen[nombre] = modulo.diario(objetivos, fecha=fecha, entorno=a.entorno, **opciones)
            log.info('%s: %s', nombre, resumen[nombre])
        except Exception as e:  # una fuente caída no detiene a las demás
            log.error('%s falló: %s\n%s', nombre, e, traceback.format_exc())
            registrar_estado(nombre, 'fallo', 0, detalle=f'{type(e).__name__}: {e}', inicio_utc=inicio,
                             fecha=fecha, entorno=a.entorno)
            resumen[nombre] = {'error': str(e)}
    alertas = [] if a.plan else revisar_alertas()
    print(json.dumps({'fecha': fecha, 'entorno': a.entorno, 'pasada': a.pasada, 'resumen': resumen,
                      'alertas': alertas}, ensure_ascii=False, default=str))
    return 1 if any('error' in resultado for resultado in resumen.values()) else 0


if __name__ == '__main__':
    sys.exit(main())
