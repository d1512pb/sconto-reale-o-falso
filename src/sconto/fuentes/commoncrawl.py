"""Common Crawl: índice CDX (index.commoncrawl.org) + lectura de registros WARC por rango de bytes con warcio.

Mismos objetivos y parsers que Wayback (sconto.parsers_archivo): fichas de los modelos objetivo y páginas
"Buen Fin" de tiendas, en los crawls que cubren sep–dic de 2024 y de 2025 (se eligen con collinfo.json).

IMPORTANTE (16-oct-2026): el robots.txt de index.commoncrawl.org dice `User-agent: * / Disallow: /` (sólo
permite la portada y collinfo.json) y el de data.commoncrawl.org `Disallow: /`. Como toda petición pasa por
sconto.cliente.Cliente, que respeta robots.txt, la corrida termina en estado 'bloqueado' sin consultar el índice.
El código queda completo para cuando el equipo decida (ver reports/cobertura_commoncrawl.md).

Caché: data/cache/commoncrawl/ (collinfo, consultas al índice); HTML de cada registro en
data/raw/commoncrawl/<fecha de captura>/<timestamp>_<hash url>.html.gz con su WARC/offset/length en condiciones.

Uso:
    python -m sconto.fuentes.commoncrawl backfill [--prioridad-max 3] [--max-crawls 8] [--limite-minutos 30]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import logging
import sys
import time

import pandas as pd
import requests

from sconto.almacen import ahora_utc, guardar_crudo, hoy, leer_crudo, registrar_estado, sha256_bytes
from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.esquema import CLAVE, a_dataframe, condiciones_json
from sconto.fuentes import wayback as wb
from sconto.parsers_archivo import parsear, parsear_tarjetas
from sconto.rutas import BRONZE, CACHE, RAIZ, RAW

log = logging.getLogger('commoncrawl')

FUENTE = 'commoncrawl'
INDICE = 'https://index.commoncrawl.org'
DATOS = 'https://data.commoncrawl.org'
CACHE_CC = CACHE / FUENTE
PERIODOS = (('2024-09-01', '2024-12-31'), ('2025-09-01', '2025-12-31'))


def nuevo_cliente() -> Cliente:
    # ≤1 petición/s, igual que Wayback; robots.txt siempre respetado (lo hace Cliente)
    return Cliente(pausa=(1.0, 1.6), reintentos=3, timeout=(30, 120), detectar_captcha=False)


class CommonCrawl:
    def __init__(self, cliente: Cliente | None = None):
        self.cliente = cliente or nuevo_cliente()
        self.peticiones = 0

    def _get(self, url, **kw):
        self.peticiones += 1
        return self.cliente.get(url, **kw)

    def crawls(self, periodos=PERIODOS) -> list[dict]:
        """Crawls cuyo intervalo [from, to] toca algún periodo (collinfo.json, cacheado por día)."""
        ruta = CACHE_CC / f'collinfo_{hoy()}.json'
        if ruta.exists():
            info = json.loads(ruta.read_text(encoding='utf-8'))
        else:
            r = self._get(f'{INDICE}/collinfo.json')
            r.raise_for_status()
            info = r.json()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps(info), encoding='utf-8')
        return seleccionar_crawls(info, periodos)

    def indice(self, cdx_api: str, url: str, match='prefix', filtros=(), max_paginas=3) -> list[dict]:
        """Consulta al índice CDX de un crawl (JSON por línea). Pagina hasta `max_paginas`."""
        base = [('url', url), ('matchType', match), ('output', 'json'), ('filter', '=status:200'),
                ('filter', '~mime:html')] + [('filter', f) for f in filtros]
        ruta = CACHE_CC / 'cdx' / f'{wb._h(cdx_api + json.dumps(base), 16)}.json'
        if ruta.exists():
            return json.loads(ruta.read_text(encoding='utf-8'))['filas']
        filas, paginas = [], 1
        r = self._get(cdx_api, params=base + [('showNumPages', 'true')])
        if r.status_code == 200:
            try:
                paginas = int(json.loads(r.text).get('pages', 1))
            except (ValueError, AttributeError):
                paginas = 1
        for p in range(min(paginas, max_paginas)):
            r = self._get(cdx_api, params=base + [('page', str(p))])
            if r.status_code == 404:  # "No Captures found"
                break
            r.raise_for_status()
            filas += [json.loads(x) for x in r.text.splitlines() if x.strip().startswith('{')]
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(dict(cdx_api=cdx_api, params=base, consultado_utc=ahora_utc(), filas=filas)),
                        encoding='utf-8')
        return filas

    def registro(self, fila: dict) -> tuple[bytes | None, str | None, str | None, str]:
        """Descarga el registro WARC por rango de bytes y devuelve (html, ruta_raw, hash, estado)."""
        ts, url = fila['timestamp'], fila['original']
        ruta = RAW / FUENTE / wb.fecha_ts(ts) / f'{ts}_{wb._h(url)}.html.gz'
        if ruta.exists():
            rel = ruta.relative_to(RAIZ).as_posix()
            contenido = leer_crudo(rel)
            return contenido, rel, sha256_bytes(contenido), 'cache'
        ini, largo = int(fila['offset']), int(fila['length'])
        r = self._get(f"{DATOS}/{fila['filename']}", headers={'Range': f'bytes={ini}-{ini + largo - 1}'})
        if r.status_code not in (200, 206):
            return None, None, None, f'http_{r.status_code}'
        html, estado_http = carga_warc(r.content)
        if html is None or estado_http != 200:
            return None, None, None, f'warc_{estado_http}'
        rel, h = guardar_crudo(FUENTE, f'{ts}_{wb._h(url)}.html', html, wb.fecha_ts(ts))
        return html, rel, h, 'descargado'


def seleccionar_crawls(info: list[dict], periodos=PERIODOS) -> list[dict]:
    salida = []
    for c in info:
        desde, hasta = str(c.get('from', ''))[:10], str(c.get('to', ''))[:10]
        if desde and hasta and any(desde <= fin and hasta >= ini for ini, fin in periodos):
            salida.append(dict(id=c['id'], nombre=c.get('name'), desde=desde, hasta=hasta, cdx_api=c['cdx-api']))
    return sorted(salida, key=lambda c: c['desde'])


def carga_warc(contenido: bytes) -> tuple[bytes | None, int | None]:
    """Cuerpo HTTP (descomprimido) y estado del primer registro 'response' de un trozo WARC (gzip por registro)."""
    from warcio.archiveiterator import ArchiveIterator
    for rec in ArchiveIterator(io.BytesIO(contenido)):
        if rec.rec_type != 'response':
            continue
        estado = int(rec.http_headers.get_statuscode()) if rec.http_headers else None
        cuerpo = rec.content_stream().read()
        return cuerpo, estado
    return None, None


def a_fila_wayback(f: dict, crawl: str) -> dict:
    """Fila del índice CC → forma de captura de Wayback (para reutilizar selección y parsers)."""
    return dict(urlkey=f.get('urlkey'), timestamp=f['timestamp'], original=f['url'], mimetype=f.get('mime'),
                statuscode=f.get('status'), digest=f.get('digest'), length=f.get('length', 0),
                offset=f.get('offset'), filename=f.get('filename'), crawl=crawl)


def adaptar(fila: dict, snap: dict) -> dict:
    cond = json.loads(fila['condiciones']) if fila.get('condiciones') else {}
    cond.pop('snapshot', None)
    cond.update(warc=snap.get('filename'), warc_offset=snap.get('offset'), warc_length=snap.get('length'),
                crawl=snap.get('crawl'))
    fila = dict(fila, fuente=FUENTE, metodo='commoncrawl', condiciones=condiciones_json(**cond),
                timestamp_cc=snap['timestamp'], crawl=snap.get('crawl'))
    fila.pop('timestamp_wayback', None)
    return fila


def escribir(filas: list[dict], fecha: str) -> int:
    if not filas:
        return 0
    from sconto.almacen import escribir_bronze
    df = a_dataframe(filas)
    df = df[pd.to_numeric(df.precio, errors='coerce') > 0]
    df = df.sort_values('timestamp_cc').drop_duplicates(CLAVE, keep='last')
    otras = [p for p in (BRONZE / FUENTE).glob('*.parquet') if p.stem != fecha]
    if otras and len(df):
        ya = set(map(tuple, pd.concat([pd.read_parquet(p, columns=CLAVE) for p in otras]).astype(str).values))
        df = df[[tuple(x) not in ya for x in df[CLAVE].astype(str).values]]
    if len(df):
        escribir_bronze(FUENTE, df, fecha, clave=CLAVE)
    return len(df)


def backfill(productos: pd.DataFrame | None = None, ids: list[str] | None = None, incluir_tiendas=True,
             max_crawls: int | None = None, max_por_id=None, max_paginas_tienda=2, limite_minutos=None,
             fecha: str | None = None, entorno='local', cc: CommonCrawl | None = None) -> dict:
    fecha = fecha or hoy()
    inicio, t0 = ahora_utc(), time.monotonic()
    cc = cc or CommonCrawl()
    if productos is None and ids is None:
        productos = wb.cargar_productos(3)
    objetivos = wb.objetivos_producto(productos, ids)
    res = dict(objetivos=len(objetivos), crawls=0, consultas=0, consultas_fallidas=0, capturas=0, registros=0,
               con_precio=0, con_tachado=0, filas=0, tiendas_sin_capturas=[], cortado_por_tiempo=False)
    filas = []
    try:
        crawls = cc.crawls()
        crawls = crawls[-max_crawls:] if max_crawls else crawls
        res['crawls'] = len(crawls)
        for obj in objetivos:
            if limite_minutos and (time.monotonic() - t0) / 60 > limite_minutos:
                res['cortado_por_tiempo'] = True
                break
            capturas = []
            for c in crawls:
                for q in wb.consultas_de(obj):
                    res['consultas'] += 1
                    try:
                        capturas += [a_fila_wayback(f, c['id']) for f in cc.indice(c['cdx_api'], q['url'], q['match'], q['filtros'])]
                    except (Bloqueado, requests.RequestException, ValueError) as e:
                        res['consultas_fallidas'] += 1
                        log.warning('índice CC falló %s %s: %s', c['id'], q['url'], e)
            elegidas = wb.seleccionar(obj, capturas, max_por_id=max_por_id)
            res['capturas'] += len(elegidas)
            for snap in elegidas:
                html, ruta_raw, h, est = cc.registro(snap)
                if html is None:
                    continue
                res['registros'] += 1
                fila = wb.filas_producto(obj, snap, parsear(html, snap['original']), ruta_raw, h, fecha)
                if fila:
                    res['con_precio'] += 1
                    res['con_tachado'] += bool(fila.get('precio_anterior_anunciado'))
                    filas.append(adaptar(fila, snap))
        if incluir_tiendas:
            for tienda, dominios in wb.TIENDAS.items():
                capturas = []
                for c in crawls:
                    for dom in dominios:
                        res['consultas'] += 1
                        try:
                            capturas += [dict(a_fila_wayback(f, c['id']), tienda=tienda) for f in
                                         cc.indice(c['cdx_api'], dom, 'domain', ('urlkey:.*buen[-_]?fin.*',))]
                        except (Bloqueado, requests.RequestException, ValueError) as e:
                            res['consultas_fallidas'] += 1
                            log.warning('índice CC falló %s %s: %s', c['id'], dom, e)
                if not capturas:
                    res['tiendas_sin_capturas'].append(tienda)
                for snap in wb.seleccionar_tienda(capturas, max_paginas_tienda):
                    html, ruta_raw, h, est = cc.registro(snap)
                    if html is not None:
                        res['registros'] += 1
                        filas += [adaptar(f, snap) for f in
                                  wb.filas_tienda(snap, parsear_tarjetas(html, snap['original']), ruta_raw, h, fecha)]
        res['filas'] = escribir(filas, fecha)
    except NoPermitido as e:
        res['filas'] = escribir(filas, fecha)
        detalle = (f'robots.txt no permite {e} para nuestro user-agent (index.commoncrawl.org y '
                   'data.commoncrawl.org publican Disallow: /); no se consultó el índice ni los WARC')
        registrar_estado(FUENTE, 'bloqueado', res['filas'], detalle, inicio, fecha, entorno)
        res['bloqueado_robots'] = str(e)
        return res
    except Exception as e:
        res['filas'] = escribir(filas, fecha)
        registrar_estado(FUENTE, 'fallo', res['filas'], f'{type(e).__name__}: {e}', inicio, fecha, entorno)
        raise
    estado = 'parcial' if res['consultas_fallidas'] or res['cortado_por_tiempo'] else 'ok'
    registrar_estado(FUENTE, estado, res['filas'], json.dumps(res), inicio, fecha, entorno)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('backfill')
    b.add_argument('--prioridad-max', type=int, default=3)
    b.add_argument('--ids', help='ids sueltos separados por coma (ASIN, MLM123, MLM-123)')
    b.add_argument('--sin-tiendas', action='store_true')
    b.add_argument('--max-crawls', type=int)
    b.add_argument('--max-snapshots-id', type=int)
    b.add_argument('--max-paginas-tienda', type=int, default=2)
    b.add_argument('--limite-minutos', type=float)
    b.add_argument('--fecha')
    b.add_argument('--entorno', default='local')
    a = ap.parse_args(argv)
    wb._configurar_log(FUENTE)
    productos = None if a.ids else wb.cargar_productos(a.prioridad_max)
    res = backfill(productos, a.ids.split(',') if a.ids else None, not a.sin_tiendas, a.max_crawls,
                   a.max_snapshots_id, a.max_paginas_tienda, a.limite_minutos, a.fecha, a.entorno)
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
