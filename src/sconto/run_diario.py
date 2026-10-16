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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--entorno', choices=['github', 'local'], default='local')
    ap.add_argument('--fuentes', nargs='*', help='Subconjunto de fuentes (por defecto, las del entorno).')
    ap.add_argument('--solo-si-falta', action='store_true',
                    help='Omite fuentes que ya tienen estado ok hoy en cualquier entorno.')
    ap.add_argument('--pasada', type=int, default=1, help='1 o 2 (la 2 sólo corre del 10 al 20 de noviembre).')
    a = ap.parse_args(argv)
    asegurar_directorios()
    fecha = hoy()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOGS / f'run_diario_{fecha}_{a.entorno}.log', encoding='utf-8')])
    cfg = yaml.safe_load((CONFIG / 'fuentes.yaml').read_text(encoding='utf-8'))['fuentes']
    productos = cargar_productos()
    resumen = {}
    for nombre, c in cfg.items():
        if a.fuentes and nombre not in a.fuentes:
            continue
        if not a.fuentes and a.entorno not in c['entornos']:
            continue
        if a.pasada == 2 and not (en_temporada_doble() and c.get('pasadas_temporada', 1) >= 2):
            continue
        if a.solo_si_falta and ya_ok_hoy(nombre, fecha):
            log.info('%s ya está ok hoy; se omite', nombre)
            continue
        inicio = ahora_utc()
        try:
            modulo = importlib.import_module(c['modulo'])
            resumen[nombre] = modulo.diario(productos, fecha=fecha, entorno=a.entorno)
            log.info('%s: %s', nombre, resumen[nombre])
        except Exception as e:  # una fuente caída no detiene a las demás
            log.error('%s falló: %s\n%s', nombre, e, traceback.format_exc())
            registrar_estado(nombre, 'fallo', 0, detalle=f'{type(e).__name__}: {e}', inicio_utc=inicio,
                             fecha=fecha, entorno=a.entorno)
            resumen[nombre] = {'error': str(e)}
    alertas = revisar_alertas()
    print({'fecha': fecha, 'entorno': a.entorno, 'pasada': a.pasada, 'resumen': resumen, 'alertas': alertas})


if __name__ == '__main__':
    main()
