"""Descarga por lotes de Preciómetro (backfill y actualización diaria). Idempotente por día de captura.

Uso:
    python -m sconto.fuentes.preciometro_lote --lista config/preciometro_lista.csv [--prioridad-max 3] [--max 10]
"""
from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from sconto.almacen import (ahora_utc, escribir_bronze, guardar_crudo, hoy, leer_crudo, registrar_estado,
                            revisar_alertas, sha256_bytes)
from sconto.cliente import Bloqueado, NoPermitido
from sconto.esquema import CLAVE
from sconto.fuentes.preciometro import FUENTE, FUENTE_OFERTAS, Preciometro, id_desde_url, parsear
from sconto.rutas import LOGS, RAIZ, RAW, asegurar_directorios

log = logging.getLogger('preciometro')


def correr(urls: list[str], fecha: str | None = None, lote: int = 25, entorno: str = 'local') -> dict:
    fecha = fecha or hoy()
    inicio = ahora_utc()
    pm = Preciometro()
    hist, ofertas, metas = [], [], []
    resumen = dict(solicitados=len(urls), descargados=0, reutilizados=0, no_encontrados=0, errores=0,
                   bloqueado=False, puntos=0, ofertas=0)

    def volcar():
        if hist:
            escribir_bronze(FUENTE, pd.concat(hist, ignore_index=True), fecha, clave=CLAVE)
        if ofertas:
            escribir_bronze(FUENTE_OFERTAS, pd.concat(ofertas, ignore_index=True), fecha, clave=CLAVE)
        if metas:
            escribir_bronze('preciometro_productos', pd.DataFrame(metas), fecha, clave=['preciometro_id'])
        hist.clear(); ofertas.clear(); metas.clear()

    for i, url in enumerate(urls, 1):
        pid = id_desde_url(url)
        ruta = RAW / FUENTE / fecha / f'{pid}.json.gz'
        try:
            if ruta.exists():
                ruta_rel = ruta.relative_to(RAIZ).as_posix()
                contenido = leer_crudo(ruta_rel)
                h = sha256_bytes(contenido)
                resumen['reutilizados'] += 1
            else:
                contenido = pm.obtener(url)
                ruta_rel, h = guardar_crudo(FUENTE, f'{pid}.json', contenido, fecha)
                resumen['descargados'] += 1
            hdf, odf, meta = parsear(contenido, url, ruta_rel, h, fecha)
            hist.append(hdf); ofertas.append(odf); metas.append(meta)
            resumen['puntos'] += len(hdf); resumen['ofertas'] += len(odf)
        except FileNotFoundError:
            resumen['no_encontrados'] += 1
            log.warning('404 %s', url)
        except (Bloqueado, NoPermitido) as e:
            resumen['bloqueado'] = True
            log.error('BLOQUEADO en %s: %s. Se detiene la corrida; se reintenta otro día.', url, e)
            break
        except Exception as e:  # una ficha rota no detiene el lote
            resumen['errores'] += 1
            log.exception('error en %s: %s', url, e)
        if i % lote == 0:
            volcar()
            log.info('%s/%s productos | %s', i, len(urls), resumen)
    volcar()
    procesados = resumen['descargados'] + resumen['reutilizados']
    estado = 'bloqueado' if resumen['bloqueado'] else ('ok' if procesados and not resumen['errores'] else
                                                         'parcial' if procesados else 'fallo')
    registrar_estado(FUENTE, estado, resumen['puntos'] + resumen['ofertas'], detalle=str(resumen),
                     inicio_utc=inicio, fecha=fecha, entorno=entorno)
    revisar_alertas()
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--lista', default=str(RAIZ / 'config' / 'preciometro_lista.csv'))
    ap.add_argument('--prioridad-max', type=int, default=None)
    ap.add_argument('--rotacion', type=int, default=None,
                    help='Para la lista amplia: sólo el 1/N del día (cada producto se refresca cada N días).')
    ap.add_argument('--max', type=int, default=None)
    ap.add_argument('--entorno', default='local')
    a = ap.parse_args(argv)
    asegurar_directorios()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOGS / f'preciometro_{hoy()}.log', encoding='utf-8')])
    lista = pd.read_csv(a.lista, dtype={'preciometro_id': str})
    if a.prioridad_max is not None:
        lista = lista.loc[lista.prioridad.le(a.prioridad_max)]
    if a.rotacion:
        dia = pd.Timestamp(hoy()).dayofyear % a.rotacion
        lista = lista.loc[lista.prioridad.le(3) | (lista.preciometro_id.astype(int) % a.rotacion == dia)]
    lista = lista.sort_values(['prioridad', 'preciometro_id'])
    urls = lista.url.tolist()[:a.max] if a.max else lista.url.tolist()
    print(correr(urls, entorno=a.entorno))


if __name__ == '__main__':
    main()
