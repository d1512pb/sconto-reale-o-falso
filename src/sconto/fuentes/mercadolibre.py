"""Mercado Libre México: API oficial (OAuth opcional) y página pública sólo si no hay muro.

Verificado en vivo el 2026-10-16 (data/cache/mercadolibre/verificacion_2026-10-16.json, crudos en data/raw):
- Sin token, los 11 endpoints probados de api.mercadolibre.com responden 401/403 (`PolicyAgent UNAUTHORIZED`,
  `authorization value not present`, `Missing access token`), incluidos /items, /products, /prices, /sale_price
  y /sites/MLM/search.
- Las páginas públicas (www /p/MLM…, articulo /MLM-…, listado) redirigen a /gz/account-verification. Es un muro
  de verificación de cuenta: no se inicia sesión ni se evade; se registra como `bloqueado`.

Por eso, sin app registrada, `diario()` sólo hace una petición de sondeo al día (para detectar si el muro
desaparece) y registra el estado. Con ML_CLIENT_ID/ML_CLIENT_SECRET/ML_REFRESH_TOKEN en .env usa la API con
refresco automático del token (código listo, NO verificado en vivo porque el equipo no ha registrado la app).
Mientras tanto, los precios de Mercado Libre llegan de forma indirecta por las ofertas que agrupa Preciómetro
(fuente preciometro_ofertas, plataforma 'Mercadolibre') y, para 2024–2025, por Wayback.
"""
from __future__ import annotations

import json
import logging
import os
import time
from urllib.parse import quote, urlsplit

import pandas as pd

from sconto.almacen import ahora_utc, escribir_bronze, guardar_crudo, hoy, registrar_estado
from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.esquema import CLAVE, a_dataframe, condiciones_json
from sconto.rutas import CACHE

log = logging.getLogger('mercadolibre')

FUENTE = 'mercadolibre'
API = 'https://api.mercadolibre.com'
WEB = 'https://www.mercadolibre.com.mx'
ARTICULO = 'https://articulo.mercadolibre.com.mx'
LISTADO = 'https://listado.mercadolibre.com.mx'
DIR_CACHE = CACHE / FUENTE
MUROS = ('/gz/account-verification', '/jms/mlm/lgz/', 'login', '/registration')


def _capturar(cliente: Cliente):
    """Guarda la última respuesta recibida: Cliente lanza Bloqueado ante 403 y así conservamos el mensaje."""
    ultima = {}

    def gancho(r, *a, **k):
        ultima['r'] = r
    cliente.sesion.hooks['response'].append(gancho)
    return ultima


def es_muro(r) -> bool:
    """La página pública redirige a 'ingresa a tu cuenta' (login): se trata como bloqueo, nunca se inicia sesión."""
    return any(m in r.url for m in MUROS) or any(m in (h.headers.get('location') or '') for h in r.history for m in MUROS)


def verificar(producto: str, item: str, user_product: str, texto: str, fecha: str | None = None) -> list[dict]:
    """Una petición por endpoint (pausa 3–8 s) sin token. Guarda cada respuesta cruda y devuelve la tabla."""
    fecha = fecha or hoy()
    api = Cliente(pausa=(3.0, 8.0), respetar_robots=False, reintentos=1)
    web = Cliente(pausa=(3.0, 8.0), reintentos=1)
    ultima_api, ultima_web = _capturar(api), _capturar(web)
    q = quote(texto)
    pruebas = [
        ('api', '/sites/MLM', f'{API}/sites/MLM'),
        ('api', '/products/{id}', f'{API}/products/{producto}'),
        ('api', '/products/{id}/items', f'{API}/products/{producto}/items'),
        ('api', '/items/{id}', f'{API}/items/{item}'),
        ('api', '/items?ids=...', f'{API}/items?ids={item}'),
        ('api', '/items/{id}/prices', f'{API}/items/{item}/prices'),
        ('api', '/items/{id}/sale_price', f'{API}/items/{item}/sale_price?context=channel_marketplace'),
        ('api', '/sites/MLM/search?q=...', f'{API}/sites/MLM/search?q={q}'),
        ('api', '/products/search?q=...', f'{API}/products/search?status=active&site_id=MLM&q={q}'),
        ('api', '/highlights/MLM/category/{cat}', f'{API}/highlights/MLM/category/MLM1055'),
        ('api', '/user-products/{id}', f'{API}/user-products/{user_product}'),
        ('web', 'www /p/{id}', f'{WEB}/p/{producto}'),
        ('web', 'articulo /MLM-{id}', f'{ARTICULO}/MLM-{item[3:]}'),
        ('web', 'listado /{texto}', f'{LISTADO}/{quote(texto.lower().replace(" ", "-"))}'),
    ]
    tabla = []
    for n, (tipo, nombre, url) in enumerate(pruebas, 1):
        cli, ultima = (api, ultima_api) if tipo == 'api' else (web, ultima_web)
        ultima.clear()
        fila = dict(n=n, tipo=tipo, endpoint=nombre, url=url, verificado_utc=ahora_utc())
        try:
            r = cli.get(url, headers={'Accept': 'application/json'} if tipo == 'api' else {})
            excepcion = None
        except NoPermitido:
            fila.update(http=None, mensaje='robots.txt no lo permite para nuestro user-agent', requiere_token=None)
            tabla.append(fila)
            continue
        except Bloqueado as e:
            r, excepcion = ultima.get('r'), str(e)
        if r is None:
            fila.update(http=None, mensaje=excepcion)
            tabla.append(fila)
            continue
        ruta_raw, hash_raw = guardar_crudo(FUENTE, f'verificacion_{n:02d}_{tipo}', r.content, fecha)
        mensaje = ''
        if 'json' in r.headers.get('content-type', ''):
            try:
                d = r.json()
                if isinstance(d, dict) and ('error' in d or 'message' in d):
                    mensaje = f"{d.get('error', '')}: {d.get('message', '')}".strip(': ')
                else:
                    mensaje = 'JSON con datos (' + ', '.join(list(d)[:8] if isinstance(d, dict) else ['lista']) + ')'
            except ValueError:
                mensaje = 'JSON inválido'
        elif es_muro(r):
            mensaje = f'redirige a muro de inicio de sesión ({urlsplit(r.url).path})'
        else:
            mensaje = f'{r.headers.get("content-type", "")} {len(r.content)} bytes'
        fila.update(http=r.status_code, url_final=r.url, mensaje=mensaje[:300], excepcion=excepcion,
                    redirecciones=[h.status_code for h in r.history], ruta_raw=ruta_raw, hash_raw=hash_raw)
        tabla.append(fila)
        log.info('%s %s → %s %s', n, nombre, r.status_code, mensaje[:120])
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    (DIR_CACHE / f'verificacion_{fecha}.json').write_text(json.dumps(tabla, ensure_ascii=False, indent=2), encoding='utf-8')
    return tabla


class TokenML:
    """OAuth de Mercado Libre con refresh token (developers.mercadolibre.com.mx). El token vive en data/cache/."""
    RUTA = DIR_CACHE / 'token.json'

    def __init__(self):
        self.client_id = os.environ.get('ML_CLIENT_ID', '').strip()
        self.secret = os.environ.get('ML_CLIENT_SECRET', '').strip()
        self.refresh = os.environ.get('ML_REFRESH_TOKEN', '').strip()

    @property
    def configurado(self) -> bool:
        return bool(self.client_id and self.secret and (self.refresh or self.RUTA.exists()))

    def access_token(self, cliente: Cliente) -> str:
        guardado = json.loads(self.RUTA.read_text(encoding='utf-8')) if self.RUTA.exists() else {}
        if guardado.get('expira', 0) > time.time() + 300:
            return guardado['access_token']
        r = cliente.sesion.post(f'{API}/oauth/token', timeout=cliente.timeout, data=dict(
            grant_type='refresh_token', client_id=self.client_id, client_secret=self.secret,
            refresh_token=guardado.get('refresh_token') or self.refresh))
        r.raise_for_status()
        d = r.json()
        DIR_CACHE.mkdir(parents=True, exist_ok=True)
        # ML rota el refresh token en cada uso: se guarda el nuevo para la siguiente corrida.
        self.RUTA.write_text(json.dumps(dict(access_token=d['access_token'], refresh_token=d.get('refresh_token'),
                                             expira=time.time() + int(d.get('expires_in', 21600)))), encoding='utf-8')
        return d['access_token']


def filas_item(d: dict, precio: dict | None, ruta_raw: str, hash_raw: str, fecha: str, producto: str | None) -> dict:
    """Fila de observación desde /items/{id} (+ /items/{id}/sale_price). original_price = precio tachado mostrado."""
    p = precio or {}
    actual = p.get('amount') or d.get('price')
    anterior = p.get('regular_amount') or d.get('original_price')
    return dict(fuente=FUENTE, metodo='api', canal='en_linea', tipo_precio='precio_vigente', fecha_precio=fecha,
                fecha_captura=fecha, id_externo=d.get('id'), tipo_id_externo='mlm_item', plataforma='Mercadolibre',
                vendedor_o_cadena=str(d.get('seller_id') or ''), descripcion_original=d.get('title'),
                precio=float(actual) if actual else None,
                precio_anterior_anunciado=float(anterior) if anterior else None, moneda=d.get('currency_id', 'MXN'),
                disponibilidad='disponible' if d.get('status') == 'active' and d.get('available_quantity', 1) else d.get('status'),
                condiciones=condiciones_json(condicion=d.get('condition'), envio_gratis=(d.get('shipping') or {}).get('free_shipping'),
                                             tienda_oficial=d.get('official_store_id'), catalogo=d.get('catalog_product_id') or producto),
                url=d.get('permalink'), ruta_raw=ruta_raw, hash_raw=hash_raw)


def diario(productos: pd.DataFrame, fecha: str | None = None, entorno: str = 'local') -> dict:
    fecha = fecha or hoy()
    inicio = ahora_utc()
    token = TokenML()
    catalogo = sorted({x for v in productos.get('mlm_ids', pd.Series(dtype=str)).fillna('') for x in str(v).split(';') if x})
    if not token.configurado:
        # Sin app: un solo sondeo diario a la página pública para saber si el muro sigue.
        web = Cliente(pausa=(3.0, 8.0), reintentos=0)
        estado, detalle = 'sin_credenciales', 'API exige token (401/403 verificado 2026-10-16); sin app registrada'
        if catalogo:
            try:
                r = web.get(f'{WEB}/p/{catalogo[0]}')
                if es_muro(r):
                    estado, detalle = 'bloqueado', detalle + '; página pública redirige a account-verification'
                else:
                    detalle += f'; página pública sin muro hoy (HTTP {r.status_code}): revisar habilitar scraping'
                    guardar_crudo(FUENTE, f'sondeo_{catalogo[0]}.html', r.content, fecha)
            except (Bloqueado, NoPermitido) as e:
                estado, detalle = 'bloqueado', f'{detalle}; {e}'
        registrar_estado(FUENTE, estado, 0, detalle=detalle, inicio_utc=inicio, fecha=fecha, entorno=entorno)
        return dict(estado=estado, filas=0, productos_catalogo=len(catalogo))

    api = Cliente(pausa=(1.0, 2.0), respetar_robots=False, reintentos=2)  # API oficial: no aplica robots web
    api.sesion.headers['Authorization'] = f'Bearer {token.access_token(api)}'
    filas, errores = [], 0
    for prod in catalogo:
        try:
            r = api.get(f'{API}/products/{prod}/items')
            ruta, h = guardar_crudo(FUENTE, f'products_{prod}_items.json', r.content, fecha)
            if r.status_code != 200:
                errores += 1
                continue
            for it in (r.json().get('results') or [])[:20]:
                iid = it.get('item_id') or it.get('id')
                ri = api.get(f'{API}/items/{iid}')
                rp = api.get(f'{API}/items/{iid}/sale_price?context=channel_marketplace')
                ruta_i, h_i = guardar_crudo(FUENTE, f'item_{iid}.json', ri.content + b'\n' + rp.content, fecha)
                if ri.status_code == 200:
                    filas.append(filas_item(ri.json(), rp.json() if rp.status_code == 200 else None, ruta_i, h_i,
                                            fecha, prod))
        except Exception as e:
            errores += 1
            log.warning('ML %s: %s', prod, e)
    df = a_dataframe(filas)
    if len(df):
        df = df.loc[df.precio.gt(0)]
        escribir_bronze(FUENTE, df, fecha, clave=CLAVE)
    estado = 'ok' if len(df) and not errores else 'parcial' if len(df) else 'fallo'
    registrar_estado(FUENTE, estado, len(df), detalle=f'catalogo={len(catalogo)} errores={errores}',
                     inicio_utc=inicio, fecha=fecha, entorno=entorno)
    return dict(estado=estado, filas=len(df), errores=errores)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    for f in verificar('MLM41998828', 'MLM2081699241', 'MLMU3275620030', 'samsung galaxy a06'):
        print(f['n'], f['endpoint'], f.get('http'), f.get('mensaje'), f.get('excepcion'))
