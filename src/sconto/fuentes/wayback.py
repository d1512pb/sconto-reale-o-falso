"""Internet Archive · Wayback Machine (CDX API): precio anunciado y tachado retroactivo de BF2024 y BF2025.

(a) Fichas de producto de los modelos objetivo: amazon.com.mx/dp/<ASIN>, mercadolibre.com.mx/<slug>/p/MLM<id>
    y articulo.mercadolibre.com.mx/MLM-<id>.
(b) Páginas "Buen Fin" de tiendas con tecnología (descubiertas con CDX por dominio y filtro de urlkey).

Ritmo: ≤1 petición/s a web.archive.org (pausa 1.0–1.6 s), backoff de Cliente ante 429/503 y corte tras varios
bloqueos seguidos. Caché: consultas CDX en data/cache/wayback/cdx/, HTML crudo en data/raw/wayback/<fecha del
snapshot>/<timestamp>_<hash url>.html.gz (ruta determinista: re-ejecutar no repite descargas).
fecha_precio = fecha del snapshot; fecha_captura = día de la corrida.

Uso:
    python -m sconto.fuentes.wayback backfill [--prioridad-max 3] [--solo-ventanas] [--limite-minutos 35]
    python -m sconto.fuentes.wayback diario [--dias 10]
    python -m sconto.fuentes.wayback cobertura
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests

from sconto.almacen import ahora_utc, escribir_bronze, guardar_crudo, hoy, leer_crudo, registrar_estado, sha256_bytes
from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.esquema import CLAVE, a_dataframe, condiciones_json
from sconto.eventos import cargar_eventos
from sconto.parsers_archivo import RE_ASIN_URL, parsear, parsear_tarjetas, slug
from sconto.rutas import BRONZE, CACHE, CONFIG, LOGS, RAIZ, RAW, asegurar_directorios

log = logging.getLogger('wayback')

FUENTE = 'wayback'
CDX_URL = 'https://web.archive.org/cdx/search/cdx'
CAMPOS = ['urlkey', 'timestamp', 'original', 'mimetype', 'statuscode', 'digest', 'length']
DESDE, HASTA = '20240901', '20251231'
CACHE_WB = CACHE / FUENTE
LARGO_MIN_PRODUCTO = 15000   # capturas comprimidas menores suelen ser CAPTCHA/redirecciones (Amazon ~2–7 KB)
EVENTOS_ARCHIVO = ('BF2024', 'BF2025')
MAX_BLOQUEOS_SEGUIDOS = 4

TIENDAS = {
    'Liverpool': ['liverpool.com.mx'], 'Coppel': ['coppel.com'], 'Walmart': ['walmart.com.mx'],
    'Elektra': ['elektra.mx', 'elektra.com.mx'], 'Sears': ['sears.com.mx'], 'Sanborns': ['sanborns.com.mx'],
    'Bodega Aurrera': ['bodegaaurrera.com.mx'], 'Soriana': ['soriana.com'], 'Amazon': ['amazon.com.mx'],
    'Mercadolibre': ['mercadolibre.com.mx'], 'Office Depot': ['officedepot.com.mx'],
}
RE_TECNO = re.compile(r'tecnolog|electr[oó]nic|pantalla|televis|smart-?tv|/tv|celular|smartphone|telefon|computo|'
                      r'computa|laptop|tablet|audio|bocina|videojueg|gamer|consola|apple|iphone|samsung|xiaomi|'
                      r'motorola|hisense|sony|/lg|linea-blanca|electro')
RE_NO_PAGINA = re.compile(r'\.(jpe?g|png|gif|webp|svg|ico|css|js|json|xml|pdf|woff2?|ttf|mp4|txt)(\?|$)')


# ------------------------------------------------------------------ utilidades

def _h(texto: str, n=12) -> str:
    return hashlib.sha1(texto.encode('utf-8')).hexdigest()[:n]


def fecha_ts(ts: str) -> str:
    return f'{ts[:4]}-{ts[4:6]}-{ts[6:8]}'


def url_snapshot(ts: str, original: str) -> str:
    return f'https://web.archive.org/web/{ts}id_/{original}'


_VENTANAS = None


def ventanas() -> list[tuple[str, str, pd.Timestamp, pd.Timestamp]]:
    """[(evento_id, ventana, inicio, fin)] de config/eventos.yaml (base, previo, evento, posterior)."""
    global _VENTANAS
    if _VENTANAS is None:
        ev = cargar_eventos()
        _VENTANAS = [(e['evento_id'], v, e[f'{v}_inicio'], e[f'{v}_fin'])
                     for e in ev.to_dict('records') for v in ('base', 'previo', 'evento', 'posterior')]
    return _VENTANAS


def ventana_de_fecha(fecha) -> str | None:
    f = pd.Timestamp(fecha)
    for ev, v, ini, fin in ventanas():
        if ini <= f <= fin:
            return f'{ev}:{v}'
    return None


def _leer_parquet(ruta):
    """Lee un parquet que otro proceso puede estar reescribiendo (copia temporal si falla)."""
    try:
        return pd.read_parquet(ruta)
    except Exception:  # noqa: BLE001 - archivo a medio escribir
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            copia = shutil.copy(ruta, f'{d}/copia.parquet')
            return pd.read_parquet(copia)


def _upsert_cache(nombre: str, df: pd.DataFrame, clave: list[str]):
    ruta = CACHE_WB / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists() and len(df):
        df = pd.concat([pd.read_parquet(ruta), df], ignore_index=True)
    if len(df):
        df.drop_duplicates(clave, keep='last').to_parquet(ruta, index=False)


# ------------------------------------------------------------------ cliente Wayback

class Wayback:
    def __init__(self, cliente: Cliente | None = None):
        self.cliente = cliente or Cliente(pausa=(1.0, 1.6), reintentos=3, timeout=(30, 150), detectar_captcha=False)
        self.bloqueos_seguidos = 0
        self.peticiones = 0

    def _get(self, url, **kw):
        self.peticiones += 1
        try:
            r = self.cliente.get(url, **kw)
        except Bloqueado:
            self.bloqueos_seguidos += 1
            raise
        self.bloqueos_seguidos = 0
        return r

    def cdx(self, url: str, match: str = 'prefix', filtros=(), desde=DESDE, hasta=HASTA, collapse='digest',
            limite=3000, solo_html=True) -> list[dict]:
        params = [('url', url), ('matchType', match), ('output', 'json'), ('fl', ','.join(CAMPOS)),
                  ('from', desde), ('to', hasta), ('filter', 'statuscode:200')]
        if solo_html:
            params.append(('filter', 'mimetype:text/html'))
        params += [('filter', f) for f in filtros] + [('collapse', collapse), ('limit', str(limite))]
        ruta = CACHE_WB / 'cdx' / f'{_h(json.dumps(params), 16)}.json'
        if ruta.exists():
            return json.loads(ruta.read_text(encoding='utf-8'))['filas']
        r = self._get(CDX_URL, params=params)
        r.raise_for_status()
        texto = r.text.strip()
        datos = json.loads(texto) if texto else []
        filas = [dict(zip(datos[0], f)) for f in datos[1:]] if datos else []
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(dict(params=params, consultado_utc=ahora_utc(), filas=filas), ensure_ascii=False),
                        encoding='utf-8')
        return filas

    def descargar(self, ts: str, original: str) -> tuple[bytes | None, str | None, str | None, str]:
        """(contenido, ruta_raw, hash_raw, estado) con estado ∈ {cache, descargado, 404, redireccion, error}."""
        ruta = RAW / FUENTE / fecha_ts(ts) / f'{ts}_{_h(original)}.html.gz'
        if ruta.exists():
            rel = ruta.relative_to(RAIZ).as_posix()
            contenido = leer_crudo(rel)
            return contenido, rel, sha256_bytes(contenido), 'cache'
        fallidas = CACHE_WB / 'descargas_fallidas.json'
        previas = json.loads(fallidas.read_text(encoding='utf-8')) if fallidas.exists() else {}
        clave = f'{ts} {original}'
        if clave in previas:
            return None, None, None, previas[clave]
        url = url_snapshot(ts, original)
        r = self._get(url, allow_redirects=False)
        if r.is_redirect and '/web/' in r.headers.get('location', ''):
            # el archivo apunta a la captura vecina; se sigue un solo salto dentro de web.archive.org
            destino = requests.compat.urljoin(url, r.headers['location'])
            m = re.search(r'/web/(\d{14})id_/', destino)
            if destino.startswith('https://web.archive.org/') and m and fecha_ts(m.group(1)) == fecha_ts(ts):
                r = self._get(destino, allow_redirects=False)
        if r.status_code != 200:
            estado = '404' if r.status_code == 404 else ('redireccion' if r.is_redirect else f'http_{r.status_code}')
            previas[clave] = estado
            fallidas.parent.mkdir(parents=True, exist_ok=True)
            fallidas.write_text(json.dumps(previas, ensure_ascii=False), encoding='utf-8')
            return None, None, None, estado
        rel, h = guardar_crudo(FUENTE, f'{ts}_{_h(original)}.html', r.content, fecha_ts(ts))
        return r.content, rel, h, 'descargado'


# ------------------------------------------------------------------ objetivos (a): fichas de producto

def _ids(valor) -> list[str]:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return []
    return [x.strip() for x in str(valor).replace(',', ';').split(';') if x.strip()]


def cargar_productos(prioridad_max: int | None = 3) -> pd.DataFrame:
    df = pd.read_csv(CONFIG / 'productos_objetivo.csv', dtype=str)
    if prioridad_max is not None and 'prioridad' in df:
        df = df[pd.to_numeric(df.prioridad, errors='coerce').fillna(99) <= prioridad_max]
    return df


def nombres_mlm_desde_ofertas() -> dict[str, str]:
    """Nombre de catálogo por MLM (para el slug de la URL), tomado de las ofertas que agrupa Preciómetro."""
    nombres = {}
    for ruta in sorted((BRONZE / 'preciometro_ofertas').glob('*.parquet')):
        df = _leer_parquet(ruta)
        if 'mlm_producto' not in df:
            continue
        for mlm, desc in df[['mlm_producto', 'descripcion_original']].dropna().itertuples(index=False):
            nombres.setdefault(str(mlm).upper(), desc)
    return nombres


def ids_desde_ofertas(prioridad_max: int | None = 3) -> pd.DataFrame:
    """Productos sintéticos (uno por producto de Preciómetro) con asins/mlm_ids/mlm_items de sus ofertas."""
    filas = []
    lista = pd.read_csv(CONFIG / 'preciometro_lista.csv', dtype=str)
    if prioridad_max is not None:
        lista = lista[pd.to_numeric(lista.prioridad, errors='coerce').fillna(99) <= prioridad_max]
    validos = set(lista.preciometro_id)
    for ruta in sorted((BRONZE / 'preciometro_ofertas').glob('*.parquet')):
        df = _leer_parquet(ruta)
        df = df[df.preciometro_producto_id.astype(str).isin(validos)]
        for pid, g in df.groupby('preciometro_producto_id'):
            filas.append(dict(producto_canonico_id=f'PM-{pid}',
                              asins=';'.join(sorted(set(g.asin.dropna()))),
                              mlm_ids=';'.join(sorted(set(g.mlm_producto.dropna()))),
                              mlm_items=';'.join(sorted(set(g.mlm_item.dropna())))))
    return pd.DataFrame(filas)


def objetivos_producto(productos: pd.DataFrame | None = None, ids: list[str] | None = None,
                       nombres: dict[str, str] | None = None) -> list[dict]:
    """Lista de objetivos {tipo, id, producto_canonico_id, nombre}. Acepta productos y/o ids sueltos."""
    nombres = nombres if nombres is not None else nombres_mlm_desde_ofertas()
    vistos, salida = set(), []

    def agregar(tipo, id_, pcid):
        id_ = id_.upper().replace('MLM-', 'MLM')
        if (tipo, id_) not in vistos:
            vistos.add((tipo, id_))
            salida.append(dict(tipo=tipo, id=id_, producto_canonico_id=pcid, nombre=nombres.get(id_)))

    if productos is not None:
        for p in productos.to_dict('records'):
            pcid = p.get('producto_canonico_id')
            for a in _ids(p.get('asins')):
                agregar('asin', a, pcid)
            for m in _ids(p.get('mlm_ids')):
                agregar('mlm_item' if '-' in m else 'mlm', m, pcid)
            for m in _ids(p.get('mlm_items')):
                agregar('mlm_item', m, pcid)
    for i in ids or []:
        i = i.strip()
        if re.fullmatch(r'[A-Z0-9]{10}', i, re.I) and not i.upper().startswith('MLM'):
            agregar('asin', i, None)
        elif re.fullmatch(r'MLM-\d+', i, re.I):
            agregar('mlm_item', i, None)
        elif re.fullmatch(r'MLM\d+', i, re.I):
            agregar('mlm', i, None)
    return salida


def consultas_de(obj: dict) -> list[dict]:
    i = obj['id']
    if obj['tipo'] == 'asin':
        return [dict(url=f'amazon.com.mx/dp/{i}', match='prefix', filtros=())]
    if obj['tipo'] == 'mlm_item':
        return [dict(url=f'articulo.mercadolibre.com.mx/MLM-{i[3:]}', match='prefix', filtros=())]
    cons = [dict(url=f'mercadolibre.com.mx/p/{i}', match='prefix', filtros=())]
    tokens = slug(obj.get('nombre') or '').split('-')
    if len(tokens) >= 2 and tokens[0]:
        cons.append(dict(url='mercadolibre.com.mx/' + '-'.join(tokens[:3]), match='prefix',
                         filtros=(f'urlkey:.*/p/{i.lower()}.*',)))
    return cons


def captura_valida(obj: dict, fila: dict) -> bool:
    """Descarta recursos que no son la ficha (imágenes, '/dp/ASIN/"+t.src+"', otra ASIN anidada, /s, /seller-info)."""
    o = fila['original']
    if RE_NO_PAGINA.search(o.lower()):
        return False
    i = obj['id']
    if obj['tipo'] == 'asin':
        return re.search(rf'/dp/{i}(?:/(?:ref=[^/?]*)?)?(?:[?#].*)?$', o, re.I) is not None
    if obj['tipo'] == 'mlm':
        return re.search(rf'/p/{i}(?:[?#].*)?$', o, re.I) is not None
    return re.search(rf'/MLM-{i[3:]}(?:[-_?#].*)?$', o, re.I) is not None


def seleccionar(obj: dict, filas: list[dict], solo_ventanas=False, max_por_id=None,
                largo_min=LARGO_MIN_PRODUCTO) -> list[dict]:
    """Una captura por día (la más pesada = ficha completa), priorizando evento > previo > base > posterior."""
    por_dia = {}

    def peso(f):  # el CDX a veces trae `length` negativo (desbordado): tamaño desconocido, se conserva
        n = int(f.get('length') or 0)
        return (n >= largo_min, n)

    for f in filas:
        if not captura_valida(obj, f) or 0 <= int(f.get('length') or 0) < largo_min:
            continue
        d = fecha_ts(f['timestamp'])
        if d not in por_dia or peso(f) > peso(por_dia[d]):
            por_dia[d] = dict(f, fecha=d, ventana=ventana_de_fecha(d))
    sel = list(por_dia.values())
    if solo_ventanas:
        sel = [s for s in sel if s['ventana'] and s['ventana'].split(':')[0] in EVENTOS_ARCHIVO]
    orden = {'evento': 0, 'previo': 1, 'base': 2, 'posterior': 3}
    sel.sort(key=lambda s: (orden.get((s['ventana'] or ':z').split(':')[1], 4), s['fecha']))
    return sel[:max_por_id] if max_por_id else sel


def filas_producto(obj: dict, snap: dict, r: dict, ruta_raw: str, hash_raw: str, fecha_captura: str) -> dict | None:
    if r.get('estado') != 'ok':
        return None
    if obj['tipo'] == 'asin' and r.get('asin') and r['asin'] != obj['id']:
        r['estado'] = 'otro_id'
        return None
    if obj['tipo'] in ('mlm', 'mlm_item') and r.get('mlm') and r['mlm'] != obj['id']:
        r['estado'] = 'otro_id'
        return None
    return dict(
        fuente=FUENTE, metodo='wayback', canal='en_linea', tipo_precio='oferta_vigente',
        fecha_precio=snap['fecha'], fecha_captura=fecha_captura, producto_canonico_id=obj.get('producto_canonico_id'),
        id_externo=obj['id'], tipo_id_externo=obj['tipo'], marca=r.get('marca'),
        descripcion_original=r.get('titulo'), plataforma=r.get('plataforma'), vendedor_o_cadena=r.get('vendido_por'),
        precio=r['precio'], precio_anterior_anunciado=r.get('precio_anterior'),
        pct_descuento_anunciado=r.get('pct') if r.get('precio_anterior') or r.get('pct') else None,
        moneda='MXN', disponibilidad=r.get('disponibilidad'),
        condiciones=condiciones_json(
            snapshot=url_snapshot(snap['timestamp'], snap['original']), etiqueta_anterior=r.get('etiqueta_anterior'),
            vendido_por=r.get('vendido_por'), enviado_por=r.get('enviado_por'), msi=r.get('msi'),
            cuotas=r.get('cuotas'), cupon=r.get('cupon'), insignia=r.get('insignia'),
            tienda_oficial=r.get('tienda_oficial'), item_ganador=r.get('item_id'), seller_id=r.get('seller_id'),
            origen_precio=r.get('origen_precio') or r.get('contenedor_precio')),
        url=snap['original'], ruta_raw=ruta_raw, hash_raw=hash_raw,
        timestamp_wayback=snap['timestamp'], evento_ventana=snap.get('ventana'), objetivo='producto',
        pagina_listado=None)


# ------------------------------------------------------------------ objetivos (b): páginas Buen Fin de tiendas

def descubrir_tienda(wb: Wayback, tienda: str, dominios: list[str], desde='20241001', hasta='20251130') -> list[dict]:
    filas = []
    for dom in dominios:
        for f in wb.cdx(dom, match='domain', filtros=('urlkey:.*buen[-_]?fin.*',), desde=desde, hasta=hasta, limite=5000):
            filas.append(dict(f, tienda=tienda))
    return filas


def seleccionar_tienda(filas: list[dict], max_paginas=3) -> list[dict]:
    """Por tienda y año: hasta `max_paginas` URLs (tecnología y portada primero) y una captura por ventana."""
    validas = [f for f in filas if not RE_NO_PAGINA.search(f['urlkey']) and f['timestamp'][4:6] in ('09', '10', '11')]
    salida = []
    for anio in ('2024', '2025'):
        grupo = {}
        for f in validas:
            if f['timestamp'][:4] == anio:
                grupo.setdefault(f['urlkey'], []).append(f)

        def puntaje(item):
            k, caps = item
            ruta = k.split(')', 1)[-1]
            return (3 * bool(RE_TECNO.search(ruta)) + 2 * (ruta.strip('/').count('/') <= 1)
                    - ('?' in ruta) + math.log1p(len(caps)))

        for k, caps in sorted(grupo.items(), key=puntaje, reverse=True)[:max_paginas]:
            por_ventana = {}
            for f in caps:
                v = ventana_de_fecha(fecha_ts(f['timestamp']))
                if v and v.split(':')[1] in ('base', 'previo', 'evento'):
                    if v not in por_ventana or f['timestamp'] > por_ventana[v]['timestamp']:
                        por_ventana[v] = dict(f, fecha=fecha_ts(f['timestamp']), ventana=v)
            salida.extend(sorted(por_ventana.values(), key=lambda s: s['timestamp']))
    return salida


def filas_tienda(snap: dict, r: dict, ruta_raw: str, hash_raw: str, fecha_captura: str, max_tarjetas=300) -> list[dict]:
    salida = []
    for t in r.get('tarjetas', [])[:max_tarjetas]:
        u = t.get('url')
        m_asin = RE_ASIN_URL.search(u or '') if u and 'amazon.' in u else None
        m_mlm = re.search(r'/p/(MLM\d+)', u or '', re.I)
        if m_asin:
            id_, tipo = m_asin.group(1).upper(), 'asin'
        elif m_mlm:
            id_, tipo = m_mlm.group(1).upper(), 'mlm'
        else:
            id_, tipo = (u or f"{snap['original']}#{slug(t['nombre'])[:80]}"), 'url'
        salida.append(dict(
            fuente=FUENTE, metodo='wayback', canal='en_linea', tipo_precio='tarjeta_listado',
            fecha_precio=snap['fecha'], fecha_captura=fecha_captura, producto_canonico_id=None,
            id_externo=id_, tipo_id_externo=tipo, descripcion_original=t['nombre'], plataforma=snap['tienda'],
            vendedor_o_cadena=snap['tienda'], precio=t['precio'], precio_anterior_anunciado=t.get('precio_anterior'),
            pct_descuento_anunciado=t.get('pct'), moneda='MXN',
            condiciones=condiciones_json(snapshot=url_snapshot(snap['timestamp'], snap['original']),
                                         origen_precio=t.get('origen'), sku=t.get('sku')),
            url=u or snap['original'], ruta_raw=ruta_raw, hash_raw=hash_raw, timestamp_wayback=snap['timestamp'],
            evento_ventana=snap.get('ventana'), objetivo='tienda', pagina_listado=snap['original']))
    return salida


# ------------------------------------------------------------------ escritura

def escribir(filas: list[dict], fecha: str) -> int:
    """Bronze del día sin repetir claves ya guardadas en particiones de otros días (backfill re-ejecutable)."""
    if not filas:
        return 0
    df = a_dataframe(filas)
    df = df[pd.to_numeric(df.precio, errors='coerce') > 0]
    df = df.sort_values('timestamp_wayback').drop_duplicates(CLAVE, keep='last')
    otras = [p for p in (BRONZE / FUENTE).glob('*.parquet') if p.stem != fecha]
    if otras and len(df):
        viejas = pd.concat([pd.read_parquet(p, columns=CLAVE) for p in otras], ignore_index=True)
        ya = set(map(tuple, viejas.astype(str).values))
        df = df[[tuple(x) not in ya for x in df[CLAVE].astype(str).values]]
    if len(df):
        escribir_bronze(FUENTE, df, fecha, clave=CLAVE)
    return len(df)


# ------------------------------------------------------------------ corridas

def _procesar_snapshot(wb, snap, fecha, registro, es_tienda, obj=None):
    contenido, ruta_raw, h, est_desc = wb.descargar(snap['timestamp'], snap['original'])
    reg = dict(objetivo='tienda' if es_tienda else 'producto', tipo=obj['tipo'] if obj else 'tienda',
               objetivo_id=obj['id'] if obj else snap['tienda'],
               producto_canonico_id=obj.get('producto_canonico_id') if obj else None,
               timestamp=snap['timestamp'], fecha=snap['fecha'], original=snap['original'],
               length=int(snap.get('length') or 0), ventana=snap.get('ventana'), ruta_raw=ruta_raw,
               estado_descarga=est_desc, estado_parseo=None, precio=None, precio_anterior=None, pct=None, n_tarjetas=0,
               n_tachado=0)
    filas = []
    if contenido is not None:
        try:
            r = parsear_tarjetas(contenido, snap['original']) if es_tienda else parsear(contenido, snap['original'])
        except Exception as e:  # noqa: BLE001 - HTML corrupto no detiene la corrida
            log.warning('parseo falló %s: %s', snap['original'], e)
            r = dict(estado='error')
        if es_tienda:
            filas = filas_tienda(snap, r, ruta_raw, h, fecha)
            reg.update(estado_parseo=r.get('estado'), n_tarjetas=len(filas),
                       n_tachado=sum(1 for f in filas if f.get('precio_anterior_anunciado')))
        else:
            fila = filas_producto(obj, snap, r, ruta_raw, h, fecha)
            reg.update(estado_parseo=r.get('estado'), precio=r.get('precio'), precio_anterior=r.get('precio_anterior'),
                       pct=r.get('pct'))
            filas = [fila] if fila else []
    registro.append(reg)
    return filas


def backfill(productos: pd.DataFrame | None = None, ids: list[str] | None = None, incluir_productos=True,
             incluir_tiendas=True, tiendas: list[str] | None = None, solo_ventanas=False, max_por_id=None,
             max_paginas_tienda=3, limite_minutos: float | None = None, fecha: str | None = None,
             desde=DESDE, hasta=HASTA, entorno='local', wb: Wayback | None = None, estado_fuente=FUENTE) -> dict:
    fecha = fecha or hoy()
    inicio, t0 = ahora_utc(), time.monotonic()
    wb = wb or Wayback()
    if productos is None and ids is None and incluir_productos:
        productos = cargar_productos(3)
    objetivos = objetivos_producto(productos, ids) if incluir_productos else []
    res = dict(objetivos=len(objetivos), consultas_cdx=0, consultas_fallidas=0, capturas_validas=0,
               snapshots=0, descargados=0, reutilizados=0, con_precio=0, con_tachado=0, filas=0,
               tiendas=0, paginas_tienda=0, tarjetas=0, cortado_por_tiempo=False, bloqueado=False)
    filas, registro, cobertura = [], [], []

    def tiempo_agotado():
        if limite_minutos and (time.monotonic() - t0) / 60 > limite_minutos:
            res['cortado_por_tiempo'] = True
        return res['cortado_por_tiempo']

    def volcar():
        res['filas'] += escribir(filas, fecha)
        _upsert_cache('snapshots.parquet', pd.DataFrame(registro), ['objetivo_id', 'timestamp', 'original'])
        _upsert_cache('objetivos.parquet', pd.DataFrame(cobertura), ['tipo', 'objetivo_id'])
        filas.clear(); registro.clear(); cobertura.clear()

    try:
        for n, obj in enumerate(objetivos, 1):
            if tiempo_agotado() or res['bloqueado']:
                break
            capturas, ok, mal = [], 0, 0
            for c in consultas_de(obj):
                res['consultas_cdx'] += 1
                try:
                    capturas += wb.cdx(c['url'], c['match'], c['filtros'], desde=desde, hasta=hasta)
                    ok += 1
                except (Bloqueado, requests.RequestException, ValueError) as e:
                    mal += 1
                    res['consultas_fallidas'] += 1
                    log.warning('CDX falló %s: %s', c['url'], e)
                    if wb.bloqueos_seguidos >= MAX_BLOQUEOS_SEGUIDOS:
                        res['bloqueado'] = True
                        break
            todas = seleccionar(obj, capturas)
            ventanas_obj = {}
            for s in todas:
                if s['ventana']:
                    ventanas_obj[s['ventana']] = ventanas_obj.get(s['ventana'], 0) + 1
            cobertura.append(dict(tipo=obj['tipo'], objetivo_id=obj['id'],
                                  producto_canonico_id=obj.get('producto_canonico_id'), consultas_ok=ok,
                                  consultas_fallidas=mal, capturas_cdx=len(capturas), dias_validos=len(todas),
                                  ventanas=json.dumps(ventanas_obj, sort_keys=True), consultado=fecha))
            elegidas = seleccionar(obj, capturas, solo_ventanas, max_por_id)
            res['capturas_validas'] += len(todas)
            for snap in elegidas:
                if tiempo_agotado():
                    break
                try:
                    nuevas = _procesar_snapshot(wb, snap, fecha, registro, False, obj)
                except (Bloqueado, requests.RequestException) as e:
                    log.warning('descarga falló %s: %s', snap['original'], e)
                    if wb.bloqueos_seguidos >= MAX_BLOQUEOS_SEGUIDOS:
                        res['bloqueado'] = True
                        break
                    continue
                res['snapshots'] += 1
                est = registro[-1]['estado_descarga']
                res['descargados'] += est == 'descargado'
                res['reutilizados'] += est == 'cache'
                res['con_precio'] += bool(nuevas)
                res['con_tachado'] += bool(nuevas and nuevas[0].get('precio_anterior_anunciado'))
                filas.extend(nuevas)
            log.info('[%s/%s] %s %s: %s capturas, %s días válidos, %s elegidas', n, len(objetivos), obj['tipo'],
                     obj['id'], len(capturas), len(todas), len(elegidas))
            if n % 10 == 0:
                volcar()
        volcar()

        if incluir_tiendas and not res['bloqueado']:
            for tienda, dominios in TIENDAS.items():
                if (tiendas and tienda not in tiendas) or tiempo_agotado() or res['bloqueado']:
                    continue
                res['tiendas'] += 1
                try:
                    encontradas = descubrir_tienda(wb, tienda, dominios)
                    res['consultas_cdx'] += len(dominios)
                except (Bloqueado, requests.RequestException, ValueError) as e:
                    res['consultas_fallidas'] += 1
                    log.warning('CDX tienda %s falló: %s', tienda, e)
                    cobertura.append(dict(tipo='tienda', objetivo_id=tienda, consultas_ok=0, consultas_fallidas=1,
                                          capturas_cdx=0, dias_validos=0, ventanas='{}', consultado=fecha))
                    if wb.bloqueos_seguidos >= MAX_BLOQUEOS_SEGUIDOS:
                        res['bloqueado'] = True
                    continue
                elegidas = seleccionar_tienda(encontradas, max_paginas_tienda)
                vent = {}
                for s in elegidas:
                    vent[s['ventana']] = vent.get(s['ventana'], 0) + 1
                cobertura.append(dict(tipo='tienda', objetivo_id=tienda, consultas_ok=len(dominios),
                                      consultas_fallidas=0, capturas_cdx=len(encontradas),
                                      dias_validos=len({f['urlkey'] for f in encontradas}),
                                      ventanas=json.dumps(vent, sort_keys=True), consultado=fecha))
                for snap in elegidas:
                    if tiempo_agotado():
                        break
                    try:
                        nuevas = _procesar_snapshot(wb, snap, fecha, registro, True)
                    except (Bloqueado, requests.RequestException) as e:
                        log.warning('descarga falló %s: %s', snap['original'], e)
                        if wb.bloqueos_seguidos >= MAX_BLOQUEOS_SEGUIDOS:
                            res['bloqueado'] = True
                            break
                        continue
                    res['paginas_tienda'] += 1
                    res['tarjetas'] += len(nuevas)
                    filas.extend(nuevas)
                log.info('tienda %s: %s capturas buen-fin, %s snapshots elegidos', tienda, len(encontradas), len(elegidas))
                volcar()
        volcar()
    except NoPermitido as e:
        volcar()
        registrar_estado(estado_fuente, 'bloqueado', res['filas'], f'robots.txt: {e}', inicio, fecha, entorno)
        return res
    except Exception as e:
        volcar()
        registrar_estado(estado_fuente, 'fallo', res['filas'], f'{type(e).__name__}: {e}', inicio, fecha, entorno)
        raise
    if res['bloqueado'] and not res['filas']:
        estado = 'bloqueado'
    elif res['bloqueado'] or res['consultas_fallidas'] or res['cortado_por_tiempo']:
        estado = 'parcial'
    else:
        estado = 'ok'
    res['peticiones'] = wb.peticiones
    res['minutos'] = round((time.monotonic() - t0) / 60, 1)
    registrar_estado(estado_fuente, estado, res['filas'], json.dumps(res), inicio, fecha, entorno)
    return res


def diario(productos: pd.DataFrame, fecha: str | None = None, entorno='local', dias=10,
           limite_minutos: float | None = 30) -> dict:
    """Capturas nuevas de los últimos `dias` para las fichas objetivo (sirve para BF2026 a posteriori)."""
    fecha = fecha or hoy()
    d = date.fromisoformat(fecha)
    return backfill(productos=productos, incluir_tiendas=False, desde=(d - timedelta(days=dias)).strftime('%Y%m%d'),
                    hasta=d.strftime('%Y%m%d'), fecha=fecha, entorno=entorno, limite_minutos=limite_minutos)


# ------------------------------------------------------------------ cobertura (cifras del reporte)

def cobertura() -> dict:
    """Cifras calculadas de la caché (CDX/descargas) y del bronze; no se estiman."""
    out = {}
    obj = pd.read_parquet(CACHE_WB / 'objetivos.parquet') if (CACHE_WB / 'objetivos.parquet').exists() else pd.DataFrame()
    snaps = pd.read_parquet(CACHE_WB / 'snapshots.parquet') if (CACHE_WB / 'snapshots.parquet').exists() else pd.DataFrame()
    partes = sorted((BRONZE / FUENTE).glob('*.parquet'))
    bz = pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True) if partes else pd.DataFrame()
    if len(obj):
        prod = obj[obj.tipo != 'tienda']
        out['objetivos_consultados'] = prod.groupby('tipo').size().to_dict()
        out['objetivos_con_consulta_fallida'] = int((prod.consultas_fallidas > 0).sum())
        out['objetivos_con_capturas_validas'] = prod[prod.dias_validos > 0].groupby('tipo').size().to_dict()
        v = prod.ventanas.map(json.loads)
        for ev, nombre, _, _ in ventanas():
            if ev in EVENTOS_ARCHIVO and nombre != 'posterior':
                k = f'{ev}:{nombre}'
                out[f'objetivos_con_snapshot_{k}'] = int(v.map(lambda x: x.get(k, 0) > 0).sum())
        out['objetivos_con_snapshot_algun_evento_BF'] = int(v.map(
            lambda x: any(k.endswith(':evento') and k.split(':')[0] in EVENTOS_ARCHIVO for k in x)).sum())
        ti = obj[obj.tipo == 'tienda']
        out['tiendas'] = {r.objetivo_id: dict(capturas_buen_fin=int(r.capturas_cdx), urls_distintas=int(r.dias_validos),
                                              consulta_fallida=bool(r.consultas_fallidas), ventanas=json.loads(r.ventanas))
                          for r in ti.itertuples()}
    if len(snaps):
        sp = snaps[snaps.objetivo == 'producto']
        out['snapshots_producto'] = dict(total=len(sp), por_estado_descarga=sp.estado_descarga.value_counts().to_dict(),
                                         por_estado_parseo=sp.estado_parseo.fillna('sin_descarga').value_counts().to_dict(),
                                         con_precio=int(sp.precio.notna().sum()),
                                         con_tachado=int(sp.precio_anterior.notna().sum()))
        st = snaps[snaps.objetivo == 'tienda']
        out['snapshots_tienda'] = dict(total=len(st), con_tarjetas=int((st.n_tarjetas > 0).sum()),
                                       tarjetas=int(st.n_tarjetas.sum()), tarjetas_con_tachado=int(st.n_tachado.sum()),
                                       por_estado_parseo=st.estado_parseo.fillna('sin_descarga').value_counts().to_dict())
    if len(bz):
        out['bronze_filas'] = len(bz)
        out['bronze_rango_fechas'] = [str(bz.fecha_precio.min()), str(bz.fecha_precio.max())]
        out['bronze_duplicados_clave'] = int(bz.duplicated(CLAVE).sum())
        out['bronze_precio_no_positivo'] = int((pd.to_numeric(bz.precio) <= 0).sum())
        pct = pd.to_numeric(bz.pct_descuento_anunciado, errors='coerce')
        out['bronze_pct_fuera_rango'] = int(((pct < -100) | (pct > 100)).sum())
        p = bz[bz.objetivo == 'producto']
        if len(p):
            pts = p.groupby('id_externo').size()
            dias = p.groupby('id_externo').fecha_precio.nunique()
            out['producto'] = dict(
                filas=len(p), ids=int(p.id_externo.nunique()), productos_canonicos=int(p.producto_canonico_id.nunique()),
                por_plataforma=p.plataforma.value_counts().to_dict(),
                con_tachado=int(p.precio_anterior_anunciado.notna().sum()),
                con_pct=int(p.pct_descuento_anunciado.notna().sum()),
                puntos_por_id_mediana=float(pts.median()), puntos_por_id_max=int(pts.max()),
                dias_con_dato=int(p.fecha_precio.nunique()), dias_por_id_mediana=float(dias.median()),
                rango_fechas=[str(p.fecha_precio.min()), str(p.fecha_precio.max())],
                por_ventana=p.evento_ventana.fillna('fuera_de_ventana').value_counts().to_dict(),
                ids_con_evento=p[p.evento_ventana.fillna('').str.endswith(':evento')].groupby(
                    p.evento_ventana.str[:6]).id_externo.nunique().to_dict())
        t = bz[bz.objetivo == 'tienda']
        if len(t):
            out['tienda'] = dict(filas=len(t), por_tienda=t.plataforma.value_counts().to_dict(),
                                 con_tachado=int(t.precio_anterior_anunciado.notna().sum()),
                                 dias_con_dato=int(t.fecha_precio.nunique()),
                                 rango_fechas=[str(t.fecha_precio.min()), str(t.fecha_precio.max())])
    return out


# ------------------------------------------------------------------ CLI

def _configurar_log(nombre):
    asegurar_directorios()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s',
                        handlers=[logging.StreamHandler(sys.stderr),
                                  logging.FileHandler(LOGS / f'{nombre}.log', encoding='utf-8')])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('backfill', help='fichas objetivo y páginas Buen Fin (2024-09-01..2025-12-31)')
    b.add_argument('--productos', help='CSV con producto_canonico_id, asins, mlm_ids (def. config/productos_objetivo.csv)')
    b.add_argument('--prioridad-max', type=int, default=3)
    b.add_argument('--desde-ofertas', action='store_true', help='agrega ASIN/MLM de las ofertas de Preciómetro')
    b.add_argument('--ids', help='ids sueltos separados por coma (ASIN, MLM123, MLM-123)')
    b.add_argument('--sin-productos', action='store_true')
    b.add_argument('--sin-tiendas', action='store_true')
    b.add_argument('--tiendas', help='subconjunto de tiendas separadas por coma')
    b.add_argument('--solo-ventanas', action='store_true', help='sólo descargar capturas en ventanas BF2024/BF2025')
    b.add_argument('--max-snapshots-id', type=int)
    b.add_argument('--max-paginas-tienda', type=int, default=3)
    b.add_argument('--limite-minutos', type=float)
    b.add_argument('--fecha')
    b.add_argument('--entorno', default='local')
    d = sub.add_parser('diario', help='capturas recientes de las fichas objetivo')
    d.add_argument('--prioridad-max', type=int, default=3)
    d.add_argument('--dias', type=int, default=10)
    d.add_argument('--fecha')
    d.add_argument('--entorno', default='local')
    sub.add_parser('cobertura', help='cifras de cobertura calculadas de caché y bronze')
    a = ap.parse_args(argv)
    if a.cmd == 'cobertura':
        print(json.dumps(cobertura(), ensure_ascii=False, indent=2, default=str))
        return 0
    _configurar_log(FUENTE)
    if a.cmd == 'diario':
        res = diario(cargar_productos(a.prioridad_max), a.fecha, a.entorno, a.dias)
    else:
        productos = pd.read_csv(a.productos, dtype=str) if a.productos else cargar_productos(a.prioridad_max)
        if a.productos and a.prioridad_max is not None and 'prioridad' in productos:
            productos = productos[pd.to_numeric(productos.prioridad, errors='coerce').fillna(99) <= a.prioridad_max]
        if a.desde_ofertas:
            productos = pd.concat([productos, ids_desde_ofertas(a.prioridad_max)], ignore_index=True)
        if a.ids and not a.productos and not a.desde_ofertas:
            productos = None  # --ids solo: sólo esos ids
        res = backfill(productos=productos, ids=a.ids.split(',') if a.ids else None,
                       incluir_productos=not a.sin_productos, incluir_tiendas=not a.sin_tiendas,
                       tiendas=a.tiendas.split(',') if a.tiendas else None, solo_ventanas=a.solo_ventanas,
                       max_por_id=a.max_snapshots_id, max_paginas_tienda=a.max_paginas_tienda,
                       limite_minutos=a.limite_minutos, fecha=a.fecha, entorno=a.entorno)
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
