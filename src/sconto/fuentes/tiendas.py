"""Liverpool/Sears: fichas públicas de una lista fija, sin descubrimiento ni login.

CSV: producto_canonico_id,tienda,url,habilitado,confianza. Sólo habilitado
1/true/si/sí y confianza alta/exacto/verificado autorizan una URL de ficha HTTPS.
diario(productos, fecha=None, entorno='local') acepta ese DataFrame o selecciona
los IDs de productos en config/tiendas_objetivo.csv. No configura el runner.

Sólo se leen Product/Offer identificados por URL/SKU, el producto principal de
__NEXT_DATA__/__INITIAL_STATE__ y markup del Product principal. No se recorren
recomendaciones, variantes ni catálogos. Estados desconocidos quedan parciales;
los selectores no implican compatibilidad verificada en producción. ListPrice
de JSON-LD es explícito; en estado embebido se exige showListPrice. Nunca se
calcula el porcentaje ni se usan lowPrice/highPrice como precio anterior.

Crudos, metadatos HTTP y robots se conservan gzip por día. --sin-red sólo usa
esa caché; los errores HTTP no se reinterpretan como fichas. El primer bloqueo
detiene TODA la lista y se conserva un cerrojo diario, incluso entre corridas.
No se siguen redirecciones, ni siquiera dentro de la allowlist.

Uso: .venv/Scripts/python.exe -m sconto.fuentes.tiendas --max 2 --sin-red
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.robotparser
from datetime import date
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import pandas as pd
import requests
from bs4 import BeautifulSoup

from sconto.almacen import (ahora_utc, escribir_bronze, guardar_crudo, hoy, leer_crudo,
                           registrar_estado, sha256_bytes)
from sconto.cliente import MARCAS_CAPTCHA, USER_AGENT, Bloqueado, Cliente, NoPermitido
from sconto.esquema import CLAVE, a_dataframe, condiciones_json
from sconto.rutas import CONFIG, RAW, RAIZ

FUENTE = 'tiendas'
HOSTS = {'liverpool.com.mx': 'liverpool', 'www.liverpool.com.mx': 'liverpool',
         'sears.com.mx': 'sears', 'www.sears.com.mx': 'sears'}
TIENDAS = ('liverpool', 'sears')
CONFIANZAS = {'alta', 'exacto', 'verificado'}


class SinCache(Exception):
    """No hay respuesta de ese día: no autoriza usar la red en --sin-red."""


def _texto(valor):
    if valor is None or isinstance(valor, (dict, list)):
        return ''
    return '' if pd.isna(valor) else str(valor).strip()


def validar_url(url: str, tienda: str | None = None) -> str:
    """Allowlist exacta, sin credenciales, puertos alternos ni rutas de catálogo."""
    partes = urlsplit(url)
    cadena = HOSTS.get(partes.hostname)
    if (partes.scheme != 'https' or not cadena or partes.username or partes.password
            or partes.port not in (None, 443) or (tienda and tienda != cadena)
            or re.search(r'[\s\\\x00-\x1f]', url)):
        raise ValueError('URL fuera de allowlist HTTPS Liverpool/Sears')
    ruta = unquote(partes.path)
    patron = r'/tienda/pdp/[^/]+(?:/[^/]+)?/?' if cadena == 'liverpool' else r'/producto/\d+(?:/[^/]+)?/?'
    if (not re.fullmatch(patron, ruta) or re.search(r'[\\\x00-\x1f]', ruta)
            or any(segmento in {'.', '..'} for segmento in ruta.split('/'))):
        raise ValueError('URL no es una ficha pública admitida')
    return urlunsplit(('https', partes.hostname, partes.path, partes.query, ''))


def _misma_url(primera, segunda):
    try:
        primera, segunda = urlsplit(primera), urlsplit(segunda)
        return (HOSTS.get(primera.hostname) is not None
                and HOSTS.get(primera.hostname) == HOSTS.get(segunda.hostname)
                and unquote(primera.path).rstrip('/') == unquote(segunda.path).rstrip('/'))
    except (ValueError, TypeError):
        return False


def _numero(valor, porcentaje=False):
    if isinstance(valor, bool) or valor is None:
        return None
    texto = _texto(valor)
    patron = r'-?(?:\d+(?:\.\d+)?)\s*%?' if porcentaje else r'(?:(?:MXN|MX\$|\$)\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?'
    if not re.fullmatch(patron, texto, flags=re.I):
        return None
    numero = float(re.sub(r'[^\d.\-]', '', texto))
    if porcentaje:
        numero = abs(numero)
    return numero if math.isfinite(numero) and (0 <= numero <= 100 if porcentaje else numero > 0) else None


def _tipo(nodo, tipo):
    tipos = nodo.get('@type', [])
    return tipo in [str(valor).rsplit('/', 1)[-1] for valor in (tipos if isinstance(tipos, list) else [tipos])]


def _identificado(nodo, url):
    for clave in ('url', '@id', 'mainEntityOfPage'):
        valor = nodo.get(clave)
        if isinstance(valor, dict):
            valor = valor.get('@id') or valor.get('url')
        if isinstance(valor, str) and _misma_url(urljoin(url, valor), url):
            return True
    ruta = unquote(urlsplit(url).path).rstrip('/').split('/')
    return any(_texto(nodo.get(clave)) in ruta for clave in ('sku', 'productID', 'productId', 'id')
               if _texto(nodo.get(clave)))


def _nombre(valor):
    return _texto(valor.get('name')) if isinstance(valor, dict) else _texto(valor)


def _oferta(producto):
    ofertas = producto.get('offers', [])
    ofertas = ofertas if isinstance(ofertas, list) else [ofertas]
    ofertas = [oferta for oferta in ofertas if isinstance(oferta, dict) and _tipo(oferta, 'Offer')]
    if len(ofertas) != 1:
        return None
    oferta = ofertas[0]
    precio = _numero(oferta.get('price'))
    moneda = _texto(oferta.get('priceCurrency')).upper()
    if precio is None or not re.fullmatch(r'[A-Z]{3}', moneda):
        return None
    anteriores = set()
    especificaciones = oferta.get('priceSpecification', [])
    especificaciones = especificaciones if isinstance(especificaciones, list) else [especificaciones]
    for especificacion in especificaciones:
        if not isinstance(especificacion, dict):
            continue
        if (_texto(especificacion.get('priceType')).rsplit('/', 1)[-1] in {'ListPrice', 'StrikethroughPrice'}
                and especificacion.get('priceCurrency', moneda) == moneda):
            anterior = _numero(especificacion.get('price'))
            if anterior is not None:
                anteriores.add(anterior)
    return dict(precio=precio, precio_anterior=next(iter(anteriores)) if len(anteriores) == 1 else None,
                pct=None, moneda=moneda,
                vendedor=_nombre(oferta.get('seller')) or None,
                disponibilidad=_texto(oferta.get('availability')) or None,
                descripcion=_nombre(producto.get('name')) or None,
                marca=_nombre(producto.get('brand')) or None, modelo=_nombre(producto.get('model')) or None,
                evidencia='json-ld Product/Offer')


def _productos_ld(nodo):
    if isinstance(nodo, list):
        for elemento in nodo:
            yield from _productos_ld(elemento)
    elif isinstance(nodo, dict):
        if _tipo(nodo, 'Product'):
            yield nodo
        for clave in ('@graph', 'mainEntity'):
            if clave in nodo:
                yield from _productos_ld(nodo[clave])


def _estado_producto(datos):
    for ruta in (('props', 'pageProps', 'product'), ('props', 'pageProps', 'productDetails'),
                 ('props', 'pageProps', 'initialState', 'product', 'productDetails'),
                 ('product',), ('productDetails',)):
        nodo = datos
        for clave in ruta:
            nodo = nodo.get(clave) if isinstance(nodo, dict) else None
        if isinstance(nodo, dict):
            yield nodo


def _desde_estado(producto):
    precios = producto.get('price')
    precios = precios if isinstance(precios, dict) else producto
    precio = _numero(precios.get('sellingPrice') or precios.get('salePrice') or precios.get('price'))
    moneda = _texto(precios.get('currency') or producto.get('priceCurrency')).upper()
    if precio is None or not re.fullmatch(r'[A-Z]{3}', moneda):
        return None
    return dict(precio=precio, moneda=moneda,
                precio_anterior=_numero(precios.get('listPrice')) if precios.get('showListPrice') is True else None,
                pct=_numero(precios.get('discountPercentage'), True) if precios.get('showDiscountPercentage') is True else None,
                vendedor=_nombre(producto.get('seller')) or None,
                disponibilidad=_texto(producto.get('availability')) or None,
                descripcion=_nombre(producto.get('name') or producto.get('productName')) or None,
                marca=_nombre(producto.get('brand')) or None, modelo=_nombre(producto.get('model')) or None,
                evidencia='estado público producto identificado')


def _limpiar_markup(arbol):
    for nodo in list(arbol.select('script, style, template, noscript, [hidden], [aria-hidden="true"]')):
        if nodo.parent is not None:
            nodo.decompose()
    for nodo in list(arbol.find_all(True)):
        if nodo.attrs is None:
            continue
        pistas = ' '.join(nodo.get('class', [])) + ' ' + nodo.get('id', '')
        estilo = re.sub(r'\s', '', nodo.get('style', '')).lower()
        if (re.search(r'carousel|carrusel|recommend|related|sugerid|recomendad', pistas, re.I)
                or 'display:none' in estilo or 'visibility:hidden' in estilo):
            nodo.decompose()


def _valor(nodo):
    return nodo.get('content') or nodo.get('href') or nodo.get_text(' ', strip=True)


def _contexto_excluido(nodo):
    for padre in nodo.parents:
        pistas = ' '.join(padre.get('class', [])) + ' ' + padre.get('id', '')
        estilo = re.sub(r'\s', '', padre.get('style', '')).lower()
        if (re.search(r'carousel|carrusel|recommend|related|sugerid|recomendad', pistas, re.I)
                or padre.has_attr('hidden') or padre.get('aria-hidden') == 'true'
                or 'display:none' in estilo or 'visibility:hidden' in estilo):
            return True
    return False


def _unico_valor(raiz, selector):
    valores = {_valor(nodo) for nodo in raiz.select(selector)}
    return next(iter(valores)) if len(valores) == 1 else None


def _desde_markup(raiz):
    ofertas = [nodo for nodo in raiz.select('[itemtype$="/Offer"]')
               if nodo.find_parent(attrs={'itemtype': re.compile(r'/Product$')}) is raiz]
    if len(ofertas) != 1:
        return None
    oferta = ofertas[0]
    precio = _numero(_unico_valor(oferta, '[itemprop="price"]'))
    moneda = _texto(_unico_valor(oferta, '[itemprop="priceCurrency"]')).upper()
    if precio is None or not re.fullmatch(r'[A-Z]{3}', moneda):
        return None
    anterior = _numero(_unico_valor(oferta, 'del, s, [data-price-type="list"], .a-product__paragraphDiscountPrice, .precio-anterior'))
    etiqueta = _unico_valor(oferta, '[data-discount-percent], .a-product__discount, .porcentaje-descuento')
    coincidencia = re.fullmatch(r'-?\d+(?:\.\d+)?\s*%', etiqueta or '')
    return dict(precio=precio, moneda=moneda, precio_anterior=anterior,
                pct=_numero(coincidencia.group(), True) if coincidencia else None,
                vendedor=_unico_valor(oferta, '[itemprop="seller"]'),
                disponibilidad=_unico_valor(oferta, '[itemprop="availability"]'),
                descripcion=_unico_valor(raiz, '[itemprop="name"]'),
                marca=_unico_valor(raiz, '[itemprop="brand"]'),
                modelo=_unico_valor(raiz, '[itemprop="model"]'), evidencia='microdatos Product/Offer')


def _desde_liverpool(arbol, url):
    if HOSTS.get(urlsplit(url).hostname) != 'liverpool':
        return None
    canonica = arbol.select_one('link[rel="canonical"]')
    if canonica is None or not _misma_url(canonica.get('href', ''), url):
        return None
    identificador = urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1]
    precios = arbol.select(f'[data-testid="{identificador}-configurator-price"]')
    titulos = arbol.select('h1')
    if len(precios) != 1 or len(titulos) != 1:
        return None
    actuales = precios[0].select('[data-testid="discounted"]')
    if len(actuales) != 1:
        return None
    actual = _numero(actuales[0].get_text('', strip=True))
    if actual is None:
        return None
    anteriores = precios[0].select('[data-testid="original"]')
    anterior = None
    if len(anteriores) == 1 and anteriores[0].select_one('.line-through, del, s'):
        anterior = _numero(anteriores[0].get_text('', strip=True))
    return dict(precio=actual, precio_anterior=anterior, pct=None, moneda='MXN', vendedor=None,
                disponibilidad=None, descripcion=titulos[0].get_text(' ', strip=True), marca=None, modelo=None,
                evidencia='configurador Liverpool del SKU; MXN normalizado por contexto del sitio mexicano')


def parsear_ficha(html: str | bytes, url: str) -> dict | None:
    """Sin producto principal inequívoco o precio/currency explícitos, no emite fila."""
    validar_url(url)
    arbol = BeautifulSoup(html, 'html.parser')
    candidatos = []
    for script in arbol.select('script[type="application/ld+json"]'):
        if _contexto_excluido(script):
            continue
        try:
            productos = _productos_ld(json.loads(script.string or script.get_text()))
            candidatos.extend(resultado for producto in productos if _identificado(producto, url)
                              if (resultado := _oferta(producto)))
        except (ValueError, TypeError):
            continue
    if not candidatos:
        for script in arbol.select('script#__NEXT_DATA__, script#__INITIAL_STATE__'):
            if _contexto_excluido(script):
                continue
            try:
                productos = _estado_producto(json.loads(script.string or script.get_text()))
                candidatos.extend(resultado for producto in productos if _identificado(producto, url)
                                  if (resultado := _desde_estado(producto)))
            except (ValueError, TypeError):
                continue
    _limpiar_markup(arbol)
    raices = []
    for raiz in arbol.select('[itemtype$="/Product"]'):
        if raiz.find_parent(attrs={'itemtype': re.compile(r'/Product$')}):
            continue
        identidad = dict(url=_unico_valor(raiz, '[itemprop="url"]'), sku=_unico_valor(raiz, '[itemprop="sku"]'))
        if _identificado(identidad, url):
            raices.append(raiz)
    markup = _desde_markup(raices[0]) if len(raices) == 1 else None
    if not candidatos:
        principal = markup or _desde_liverpool(arbol, url)
        candidatos = [principal] if principal else []
    unicos = {json.dumps(resultado, sort_keys=True, ensure_ascii=False): resultado for resultado in candidatos}
    if len(unicos) != 1:
        return None
    resultado = dict(next(iter(unicos.values())))
    vendedores_compatibles = (not markup or not markup['vendedor'] or not resultado['vendedor']
                              or markup['vendedor'] == resultado['vendedor'])
    if (markup and vendedores_compatibles
            and (markup['precio'], markup['moneda']) == (resultado['precio'], resultado['moneda'])):
        for clave in ('precio_anterior', 'pct', 'vendedor', 'disponibilidad'):
            if resultado.get(clave) is None:
                resultado[clave] = markup.get(clave)
    if resultado['precio_anterior'] is not None and resultado['precio_anterior'] <= resultado['precio']:
        resultado['precio_anterior'] = None
    return resultado


def permitido(texto: str, url: str) -> bool:
    """urllib más denegaciones con comodines; ante dudas se niega la ruta."""
    grupos, agentes, reglas = [], [], []
    en_reglas = False
    for linea in texto.splitlines():
        campo, separador, valor = linea.split('#', 1)[0].partition(':')
        if not separador:
            continue
        campo, valor = campo.strip().lower(), valor.strip()
        if campo == 'user-agent':
            if en_reglas:
                grupos.append((agentes, reglas))
                agentes, reglas, en_reglas = [], [], False
            agentes.append(valor.lower())
        elif agentes:
            en_reglas = True
            if campo == 'disallow' and valor:
                reglas.append(valor)
    grupos.append((agentes, reglas))
    token = USER_AGENT.split('/')[0].lower()
    propios = [grupo for grupo in grupos if any(agente != '*' and agente in token for agente in grupo[0])]
    aplicables = propios or [grupo for grupo in grupos if '*' in grupo[0]]
    partes = urlsplit(url)
    ruta = unquote(partes.path + ('?' + partes.query if partes.query else ''))
    for _, patrones in aplicables:
        for patron in patrones:
            fin = patron.endswith('$')
            expresion = re.escape(unquote(patron[:-1] if fin else patron)).replace(r'\*', '.*')
            if re.match(expresion + ('$' if fin else ''), ruta):
                return False
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(texto.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def _bloqueo(http, contenido):
    if http in (401, 403, 429, 503) or 300 <= http < 400:
        return f'HTTP {http}; sin reintentos ni redirecciones'
    texto = contenido.decode('utf-8', 'replace').lower()
    marcas = (*MARCAS_CAPTCHA, 'access denied', 'verify you are human', 'inicia sesión para continuar')
    if any(marca in texto for marca in marcas) or re.search(r'<input\b[^>]*type=[\"\']password', texto):
        return 'CAPTCHA/login/bloqueo público; sin evasión'
    return None


def _ruta(nombre, fecha):
    return RAW / FUENTE / fecha / (nombre + '.gz')


def _leer_json(nombre, fecha):
    return json.loads(leer_crudo(_ruta(nombre, fecha).relative_to(RAIZ).as_posix()))


def _guardar_respuesta(respuesta, nombre, fecha):
    ruta_raw, hash_raw = guardar_crudo(FUENTE, nombre + '.body', respuesta.content, fecha)
    datos = dict(http=respuesta.status_code, url=respuesta.url, ruta_raw=ruta_raw,
                 hash_raw=hash_raw, fecha_captura=ahora_utc())
    guardar_crudo(FUENTE, nombre + '.json', json.dumps(datos), fecha)
    return datos


def _obtener(cliente, url, nombre, fecha, sin_red):
    if _ruta(nombre + '.json', fecha).exists():
        datos = _leer_json(nombre + '.json', fecha)
    else:
        if sin_red:
            raise SinCache(url)
        recibidas = []

        def capturar(respuesta, *args, **kwargs):
            recibidas.append(respuesta)
            if 300 <= respuesta.status_code < 400:
                raise Bloqueado(f'Redirección no seguida: {url}', respuesta)

        try:
            respuesta = cliente.get(url, allow_redirects=False, hooks={'response': capturar})
        except Bloqueado as error:
            respuesta = getattr(error, 'respuesta', None)
            if respuesta is None and recibidas:
                respuesta = recibidas[-1]
            if respuesta is not None:
                _guardar_respuesta(respuesta, nombre, fecha)
            raise
        datos = _guardar_respuesta(respuesta, nombre, fecha)
    contenido = leer_crudo(datos['ruta_raw'])
    if sha256_bytes(contenido) != datos['hash_raw']:
        raise ValueError('hash_raw de caché no coincide')
    motivo = _bloqueo(datos['http'], contenido)
    if motivo:
        raise Bloqueado(f'{motivo}: {url}')
    return datos, contenido


def _robots(cliente, url, fecha, sin_red):
    partes = urlsplit(url)
    origen = f'{partes.scheme}://{partes.netloc}'
    nombre = 'robots_' + partes.netloc
    previo = cliente.respetar_robots if cliente else None
    try:
        if cliente:
            cliente.respetar_robots = False
        datos, contenido = _obtener(cliente, origen + '/robots.txt', nombre, fecha, sin_red)
    finally:
        if cliente:
            cliente.respetar_robots = previo
    texto = contenido.decode('utf-8-sig', 'replace')
    if datos['http'] != 200 or '<html' in texto.lower() or not re.search(r'^\s*user-agent\s*:', texto, re.I | re.M):
        raise ValueError(f'robots.txt no verificable (HTTP {datos["http"]}); no se solicita ficha')
    if not permitido(texto, url):
        raise NoPermitido(f'robots.txt no permite {url}')
    if cliente:
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(texto.splitlines())
        cliente._robots[origen] = parser
    return dict(url=origen + '/robots.txt', http=datos['http'], permitido=True,
                ruta_raw=datos['ruta_raw'], hash_raw=datos['hash_raw'])


def _objetivos(productos):
    if productos is None:
        return pd.read_csv(CONFIG / 'tiendas_objetivo.csv', dtype=str).fillna('')
    if 'url' in productos.columns:
        return productos.copy().fillna('')
    lista = pd.read_csv(CONFIG / 'tiendas_objetivo.csv', dtype=str).fillna('')
    ids = set(productos.get('producto_canonico_id', pd.Series(dtype=str)).map(_texto))
    return lista[lista.producto_canonico_id.isin(ids)]


def _fila(objetivo, ficha, datos, fecha):
    return dict(fuente=FUENTE, metodo='scraping', canal='en_linea', tipo_precio='publicado',
                fecha_precio=fecha, fecha_captura=fecha,
                producto_canonico_id=objetivo['producto_canonico_id'],
                id_externo=objetivo['url'], tipo_id_externo='url',
                marca=ficha['marca'], modelo_normalizado=ficha['modelo'], descripcion_original=ficha['descripcion'],
                plataforma=objetivo['tienda'], vendedor_o_cadena=ficha['vendedor'],
                precio=ficha['precio'], precio_anterior_anunciado=ficha['precio_anterior'],
                pct_descuento_anunciado=ficha['pct'], moneda=ficha['moneda'], disponibilidad=ficha['disponibilidad'],
                condiciones=condiciones_json(evidencia=ficha['evidencia'], confianza=objetivo['confianza'],
                                             captura_utc=datos['fecha_captura'],
                                             vendedor_no_publicado=not bool(ficha['vendedor'])),
                url=objetivo['url'], ruta_raw=datos['ruta_raw'], hash_raw=datos['hash_raw'])


def _correr(productos, fecha=None, entorno='local', *, maximo=None, sin_red=False):
    fecha = date.fromisoformat(fecha or hoy()).isoformat()
    if not re.fullmatch(r'[\w-]+', entorno) or (maximo is not None and maximo < 0):
        raise ValueError('entorno o máximo inválido')
    inicio = ahora_utc()
    resultado = dict(estado='parcial', filas=0, fecha=fecha, sin_red=sin_red,
                     objetivos=0, procesados=0, incidencias=[], robots=[], tiendas={})
    filas, objetivos = [], []
    cliente = None
    bloqueo = None
    try:
        lista = _objetivos(productos)
        for registro in lista.to_dict('records'):
            if _texto(registro.get('habilitado')).lower() not in {'1', 'true', 'si', 'sí'}:
                continue
            try:
                objetivo = {clave: _texto(registro.get(clave)) for clave in
                            ('producto_canonico_id', 'tienda', 'url', 'confianza')}
                objetivo['tienda'] = objetivo['tienda'].lower()
                objetivo['confianza'] = objetivo['confianza'].lower()
                if (not objetivo['producto_canonico_id'] or objetivo['tienda'] not in TIENDAS
                        or objetivo['confianza'] not in CONFIANZAS):
                    raise ValueError('ID, tienda o confianza no verificados')
                objetivo['url'] = validar_url(objetivo['url'], objetivo['tienda'])
                objetivos.append(objetivo)
            except ValueError as error:
                resultado['incidencias'].append(str(error))
        por_url = {}
        for objetivo in objetivos:
            por_url.setdefault(objetivo['url'], []).append(objetivo)
        objetivos = []
        for grupo in por_url.values():
            if len({objetivo['producto_canonico_id'] for objetivo in grupo}) != 1:
                resultado['incidencias'].append('URL asignada a varios productos; no integrado')
            else:
                objetivos.append(grupo[0])
        if maximo is not None and len(objetivos) > maximo:
            resultado['incidencias'].append('lista limitada por --max')
            objetivos = objetivos[:maximo]
        resultado['objetivos'] = len(objetivos)
        for tienda in TIENDAS:
            tiene_urls = any(objetivo['tienda'] == tienda for objetivo in objetivos)
            resultado['tiendas'][tienda] = dict(estado='parcial', filas=0,
                                               motivo='pendiente' if tiene_urls else 'no integrado: sin URL objetivo habilitada y confiable')
        if _ruta('bloqueo.json', fecha).exists():
            bloqueo = _leer_json('bloqueo.json', fecha)['motivo']
        elif objetivos:
            if not sin_red:
                cliente = Cliente(reintentos=0, detectar_captcha=False)
            for objetivo in objetivos:
                url = objetivo['url']
                try:
                    evidencia = _robots(cliente, url, fecha, sin_red)
                    if evidencia not in resultado['robots']:
                        resultado['robots'].append(evidencia)
                    nombre = sha256_bytes(url.encode())[:24]
                    datos, contenido = _obtener(cliente, url, nombre, fecha, sin_red)
                    resultado['procesados'] += 1
                    if datos['http'] != 200:
                        raise ValueError(f'HTTP {datos["http"]}: sin ficha {url}')
                    ficha = parsear_ficha(contenido, url)
                    if not ficha:
                        raise ValueError(f'no integrado: formato/identidad/precio no inequívoco {url}')
                    filas.append(_fila(objetivo, ficha, datos, fecha))
                    resultado['tiendas'][objetivo['tienda']]['filas'] += 1
                except (Bloqueado, NoPermitido) as error:
                    bloqueo = str(error)
                    guardar_crudo(FUENTE, 'bloqueo.json', json.dumps(dict(motivo=bloqueo, inicio_utc=inicio)), fecha)
                    break
                except (SinCache, requests.RequestException, ValueError, OSError) as error:
                    resultado['incidencias'].append(f'{type(error).__name__}: {error}')
        if filas:
            dataframe = a_dataframe(filas).drop_duplicates(CLAVE, keep='last')
            escribir_bronze(FUENTE, dataframe, fecha, clave=CLAVE)
            resultado['filas'] = len(dataframe)
        for tienda, resumen in resultado['tiendas'].items():
            cantidad = sum(objetivo['tienda'] == tienda for objetivo in objetivos)
            if bloqueo and cantidad:
                resumen.update(estado='bloqueado', motivo=bloqueo)
            elif cantidad and resumen['filas'] == cantidad:
                resumen.update(estado='ok', motivo='fichas públicas observadas')
            elif cantidad:
                resumen['motivo'] = 'no integrado: faltan fichas verificables; ver incidencias'
        if bloqueo:
            resultado.update(estado='bloqueado', motivo=bloqueo)
        elif not resultado['incidencias'] and objetivos and resultado['filas'] == len(objetivos):
            resultado['estado'] = 'ok'
        else:
            resultado['motivo'] = 'no integrado: sin URL objetivo o cobertura parcial; ver tiendas/incidencias'
    except (ValueError, OSError, KeyError) as error:
        resultado.update(estado='parcial', motivo=f'no integrado: {type(error).__name__}: {error}')
    finally:
        if cliente:
            cliente.sesion.close()
    detalle = resultado.get('motivo') or 'fichas verificadas para la lista fija'
    if resultado['incidencias']:
        detalle += '; ' + '; '.join(resultado['incidencias'])
    registrar_estado(FUENTE, resultado['estado'], resultado['filas'], detalle=detalle,
                     inicio_utc=inicio, fecha=fecha, entorno=entorno)
    return resultado


def diario(productos, fecha=None, entorno='local') -> dict:
    """Colecta exclusivamente URLs habilitadas y confiables de Liverpool y Sears."""
    return _correr(productos, fecha, entorno)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('comando', nargs='?', choices=['diario'], default='diario')
    parser.add_argument('--productos', default=str(CONFIG / 'tiendas_objetivo.csv'), help='CSV de URLs fijas, no catálogo')
    parser.add_argument('--fecha', help='Día ISO de captura/caché')
    parser.add_argument('--entorno', default='local')
    parser.add_argument('--max', type=int, dest='maximo', help='Máximo de URLs habilitadas (0: ninguna)')
    parser.add_argument('--sin-red', action='store_true', help='Sólo crudos del día; nunca hace peticiones HTTP')
    argumentos = parser.parse_args(argv)
    if argumentos.maximo is not None and argumentos.maximo < 0:
        parser.error('--max debe ser >= 0')
    try:
        productos = pd.read_csv(argumentos.productos, dtype=str).fillna('')
        resultado = _correr(productos, argumentos.fecha, argumentos.entorno,
                            maximo=argumentos.maximo, sin_red=argumentos.sin_red)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(resultado, ensure_ascii=False))
    return 0 if resultado['estado'] == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
