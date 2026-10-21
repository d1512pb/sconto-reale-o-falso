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

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import pandas as pd

from sconto.almacen import ahora_utc, escribir_bronze, guardar_crudo, hoy, leer_crudo, registrar_estado, sha256_bytes
from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.esquema import CLAVE, a_dataframe, condiciones_json
from sconto.rutas import CACHE, CONFIG, RAW, RAIZ

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
        self.access = os.environ.get('ML_ACCESS_TOKEN', '').strip()
        self.client_id = os.environ.get('ML_CLIENT_ID', '').strip()
        self.secret = os.environ.get('ML_CLIENT_SECRET', '').strip()
        self.refresh = os.environ.get('ML_REFRESH_TOKEN', '').strip()

    @property
    def configurado(self) -> bool:
        return bool(self.access or (self.client_id and self.secret and (self.refresh or self.RUTA.exists())))

    def access_token(self, cliente: Cliente) -> str:
        if self.access:
            return self.access
        guardado = json.loads(self.RUTA.read_text(encoding='utf-8')) if self.RUTA.exists() else {}
        if guardado.get('expira', 0) > time.time() + 300:
            return guardado['access_token']
        cliente._esperar(urlsplit(API).netloc)
        r = cliente.sesion.post(f'{API}/oauth/token', timeout=cliente.timeout, allow_redirects=False, data=dict(
            grant_type='refresh_token', client_id=self.client_id, client_secret=self.secret,
            refresh_token=guardado.get('refresh_token') or self.refresh))
        if r.status_code != 200:
            raise ValueError(f'No se pudo refrescar el token ML: HTTP {r.status_code}; revisar .env')
        d = r.json()
        DIR_CACHE.mkdir(parents=True, exist_ok=True)
        # ML rota el refresh token en cada uso: se guarda el nuevo para la siguiente corrida.
        self.RUTA.write_text(json.dumps(dict(access_token=d['access_token'], refresh_token=d.get('refresh_token') or guardado.get('refresh_token') or self.refresh,
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


def objetivos(productos: pd.DataFrame) -> list[dict]:
    salida = {}
    for fila in productos.to_dict('records'):
        if fila.get('confianza_match') != 'exacto':
            continue
        for columna, tipo in [('mlm_ids', 'producto'), ('mlm_item_ids', 'item')]:
            for identificador in str(fila.get(columna) or '').split(';'):
                identificador = identificador.strip().upper().replace('-', '')
                if re.fullmatch(r'MLM\d+', identificador):
                    pid = fila.get('producto_canonico_id')
                    if identificador in salida and salida[identificador]['producto_canonico_id'] != pid:
                        salida[identificador]['producto_canonico_id'] = None
                    else:
                        salida[identificador] = dict(id=identificador, tipo=tipo, producto_canonico_id=pid)
    return [fila for fila in salida.values() if fila['producto_canonico_id']]


def diario(productos: pd.DataFrame, fecha: str | None = None, entorno: str = 'local', max_items: int = 3) -> dict:
    fecha = fecha or hoy()
    inicio = ahora_utc()
    token = TokenML()
    lista = objetivos(productos)
    catalogo = [fila['id'] for fila in lista]
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

    api = Cliente(pausa=(3.0, 8.0), respetar_robots=False, reintentos=0)
    filas, errores, bloqueado = [], 0, False
    for objetivo in lista:
        prod = objetivo['id']
        try:
            cache = RAW / FUENTE / fecha / f'objetivo_{prod}.json.gz'
            if cache.exists():
                ruta = cache.relative_to(RAIZ).as_posix()
                contenido = leer_crudo(ruta)
                paquete = json.loads(contenido)
                digest = sha256_bytes(contenido)
            else:
                if fecha != hoy():
                    errores += 1
                    continue
                if 'Authorization' not in api.sesion.headers:
                    api.sesion.headers['Authorization'] = f'Bearer {token.access_token(api)}'
                ids = [prod]
                if objetivo['tipo'] == 'producto':
                    response = api.get(f'{API}/products/{prod}/items')
                    guardar_crudo(FUENTE, f'products_{prod}_items.json', response.content, fecha)
                    if response.status_code == 401:
                        raise Bloqueado('401: revisar autorización de la API ML', response)
                    response.raise_for_status()
                    ids = [item.get('item_id') or item.get('id') for item in response.json().get('results', [])][:max_items]
                paquete = {'capturado_utc': ahora_utc(), 'items': []}
                for identificador in ids:
                    response = api.get(f'{API}/items/{identificador}')
                    guardar_crudo(FUENTE, f'item_{identificador}.json', response.content, fecha)
                    if response.status_code == 401:
                        raise Bloqueado('401: revisar autorización de la API ML', response)
                    response.raise_for_status()
                    precio = api.get(f'{API}/items/{identificador}/sale_price?context=channel_marketplace')
                    guardar_crudo(FUENTE, f'sale_price_{identificador}.json', precio.content, fecha)
                    if precio.status_code == 401:
                        raise Bloqueado('401: revisar autorización de precios ML', precio)
                    paquete['items'].append({'item': response.json(), 'sale_price': precio.json() if precio.status_code == 200 else None})
                contenido = json.dumps(paquete, ensure_ascii=False).encode('utf-8')
                ruta, digest = guardar_crudo(FUENTE, f'objetivo_{prod}.json', contenido, fecha)
            for registro in paquete['items']:
                fila = filas_item(registro['item'], registro['sale_price'], ruta, digest, fecha, prod)
                fila['producto_canonico_id'] = objetivo['producto_canonico_id']
                filas.append(fila)
        except (Bloqueado, NoPermitido) as error:
            respuesta = getattr(error, 'respuesta', None)
            if respuesta is not None:
                guardar_crudo(FUENTE, f'bloqueo_{prod}.json', respuesta.content, fecha)
            bloqueado = True
            break
        except Exception as e:
            errores += 1
            log.warning('ML %s: %s', prod, e)
    df = a_dataframe(filas)
    if len(df):
        df = df.loc[df.precio.gt(0)]
        escribir_bronze(FUENTE, df, fecha, clave=CLAVE)
    estado = 'bloqueado' if bloqueado else 'ok' if len(df) and not errores else 'parcial' if len(df) else 'fallo'
    registrar_estado(FUENTE, estado, len(df), detalle=f'catalogo={len(catalogo)} errores={errores}',
                     inicio_utc=inicio, fecha=fecha, entorno=entorno)
    return dict(estado=estado, filas=len(df), errores=errores, bloqueado=bloqueado)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mercado Libre: lista fija, API oficial y caché diaria; no ofrece historial retroactivo público.')
    parser.add_argument('--productos', type=Path, default=CONFIG / 'productos_objetivo.csv')
    parser.add_argument('--max', type=int, default=10)
    parser.add_argument('--plan', action='store_true', help='Ver objetivos sin red ni credenciales.')
    argumentos = parser.parse_args(argv)
    if argumentos.max < 1:
        parser.error('--max debe ser positivo')
    productos = pd.read_csv(argumentos.productos, dtype=str, keep_default_na=False).head(argumentos.max)
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(objetivos(productos) if argumentos.plan else diario(productos), ensure_ascii=False))


if __name__ == '__main__':
    main()
