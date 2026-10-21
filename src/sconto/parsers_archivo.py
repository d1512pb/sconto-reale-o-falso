"""Parsers de HTML histórico (Wayback Machine y Common Crawl): Amazon, Mercado Libre y tarjetas de tiendas.

Reglas comunes:
- primero datos estructurados (JSON-LD, estado preinyectado), luego selectores;
- `precio_anterior` sólo si la página MUESTRA un precio tachado/anterior; `pct` tal como lo pinta la página
  (Amazon "-31%" → 31; Mercado Libre "47% OFF" → 47), nunca calculado aquí;
- no se extraen reseñas ni nombres de usuarios; del vendedor sólo el nombre comercial que muestra la ficha.
Cada parser devuelve un dict con `estado` ∈ {ok, sin_precio, captcha, no_producto} y los campos encontrados.
"""
from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser

RE_NUM = re.compile(r'\d[\d.,]*')
RE_PRECIO_TXT = re.compile(r'\$\s?(\d{1,3}(?:[,.]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)')
RE_PCT = re.compile(r'(?<![\d.])(\d{1,2}(?:[.,]\d)?)\s?%')
RE_MSI = re.compile(r'(\d{1,2})\s*(?:meses|MSI)\s*(?:sin\s+inter[eé]s(?:es)?)?', re.I)
RE_ASIN_URL = re.compile(r'/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?=[/?#]|$)', re.I)
RE_MLM = re.compile(r'MLM-?(\d{5,})', re.I)


# ------------------------------------------------------------------ utilidades

def a_texto(contenido: bytes | str) -> str:
    if isinstance(contenido, str):
        return contenido
    try:
        return contenido.decode('utf-8')
    except UnicodeDecodeError:
        return contenido.decode('cp1252', errors='replace')


def limpio(texto) -> str | None:
    if texto is None:
        return None
    t = re.sub(r'\s+', ' ', str(texto)).strip()
    return t or None


def a_numero(texto) -> float | None:
    """'$1,439.00' → 1439.0; '1.439,50' → 1439.5; 999 → 999.0. None si no hay número positivo."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto) if texto > 0 else None
    m = RE_NUM.search(str(texto).replace('\xa0', ' '))
    if not m:
        return None
    s = m.group(0).rstrip('.,')
    if ',' in s and '.' in s:
        dec = '.' if s.rfind('.') > s.rfind(',') else ','
        s = s.replace(',' if dec == '.' else '.', '').replace(dec, '.')
    elif ',' in s:
        partes = s.split(',')
        s = s.replace(',', '') if len(partes[-1]) == 3 else s.replace(',', '.')
    elif s.count('.') > 1 or (s.count('.') == 1 and len(s.split('.')[-1]) == 3 and len(s) > 4):
        s = s.replace('.', '')
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def a_pct(texto) -> float | None:
    """Porcentaje tal como se muestra ("-31%", "47% OFF", "Ahorras $440 (31%)") → 31.0 (positivo = descuento)."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        v = abs(float(texto))
    else:
        m = RE_PCT.search(str(texto))
        if not m:
            return None
        v = float(m.group(1).replace(',', '.'))
    return v if 0 < v < 100 else None


def slug(texto: str) -> str:
    t = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')


def _texto(nodo) -> str | None:
    return limpio(nodo.text(separator=' ')) if nodo is not None else None


def _primero(arbol, selectores, raiz=None):
    base = raiz or arbol
    for s in selectores:
        n = base.css_first(s)
        if n is not None and limpio(n.text()):
            return n
    return None


def json_ld(arbol) -> list[dict]:
    """Objetos JSON-LD aplanados (@graph y listas incluidas). Ignora bloques mal formados."""
    salida = []
    for s in arbol.css('script[type="application/ld+json"]'):
        try:
            d = json.loads(s.text(), strict=False)
        except (ValueError, TypeError):
            continue
        pila = [d]
        while pila:
            x = pila.pop()
            if isinstance(x, list):
                pila.extend(x)
            elif isinstance(x, dict):
                salida.append(x)
                if '@graph' in x:
                    pila.append(x['@graph'])
    return salida


def _tipo(d: dict) -> set[str]:
    t = d.get('@type')
    return set(t) if isinstance(t, list) else {t}


def json_asignado(html: str, variable: str):
    """Objeto JSON asignado en JS: `window.<variable> = {...}` o `<script id="<variable>">{...}</script>`."""
    m = re.search(r'<script[^>]*id=["\']' + re.escape(variable) + r'["\'][^>]*>\s*(\{.*?\})\s*</script>', html, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except ValueError:
            pass
    for m in re.finditer(re.escape(variable) + r'\s*=\s*\{', html):
        try:
            return json.JSONDecoder().raw_decode(html[m.end() - 1:])[0]
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------ Amazon

CONTENEDORES_PRECIO_AMZ = ['#corePriceDisplay_desktop_feature_div', '#corePrice_desktop', '#corePrice_feature_div',
                           '#apex_desktop', '#apex_desktop_newAccordionRow', '#price', '#unifiedPrice_feature_div',
                           '#buybox']
ETIQUETAS_ANTERIOR = ('precio de lista', 'antes', 'precio anterior', 'precio más bajo reciente',
                      'precio mas bajo reciente', 'p.v.p', 'precio regular', 'de:')


def _precio_a_price(nodo) -> float | None:
    """Precio de un `span.a-price`: primero `.a-offscreen`, si está vacío une entero + fracción."""
    if nodo is None:
        return None
    off = nodo.css_first('.a-offscreen')
    v = a_numero(off.text()) if off is not None else None
    if v:
        return v
    entero, frac = nodo.css_first('.a-price-whole'), nodo.css_first('.a-price-fraction')
    if entero is not None:
        e = re.sub(r'\D', '', entero.text())
        f = re.sub(r'\D', '', frac.text()) if frac is not None else ''
        return a_numero(f'{e}.{f or "00"}') if e else None
    return a_numero(nodo.text())


def _tabla_precio_amazon(cont) -> dict:
    """Diseño antiguo en tabla (#corePrice_desktop): filas 'Precio de lista:' / 'Precio:' / 'Ahorras:'."""
    out = {}
    for tr in cont.css('tr'):
        celdas = tr.css('td')
        if len(celdas) < 2:
            continue
        etiqueta = (limpio(celdas[0].text()) or '').lower()
        valor = _precio_a_price(celdas[1].css_first('.a-price')) or a_numero(celdas[1].text())
        if any(e in etiqueta for e in ETIQUETAS_ANTERIOR):
            out.setdefault('precio_anterior', valor)
            out.setdefault('etiqueta_anterior', limpio(celdas[0].text()).rstrip(':'))
        elif 'ahorr' in etiqueta:
            out.setdefault('pct', a_pct(celdas[1].text()))
        elif 'precio' in etiqueta or 'oferta' in etiqueta:
            out.setdefault('precio', valor)
    return out


def parsear_amazon(contenido: bytes | str) -> dict:
    html = a_texto(contenido)
    arbol = LexborHTMLParser(html)
    r = dict(estado='no_producto', plataforma='Amazon')
    titulo = _texto(arbol.css_first('#productTitle'))
    if titulo is None:
        bajo = html[:60000].lower()
        if 'validatecaptcha' in bajo or 'opfcaptcha' in bajo or 'introduce los caracteres' in bajo:
            r['estado'] = 'captcha'
        return r
    for x in arbol.css('script, style, noscript'):  # su texto se cuela en #availability y otros bloques
        x.decompose()
    r['titulo'] = titulo
    n = arbol.css_first('input#ASIN') or arbol.css_first('input[name="ASIN"]')
    asin = n.attributes.get('value') if n is not None else None
    if not asin:
        canon = arbol.css_first('link[rel="canonical"]')
        m = RE_ASIN_URL.search(canon.attributes.get('href', '')) if canon is not None else None
        asin = m.group(1) if m else None
    r['asin'] = asin.upper() if asin else None
    marca = _texto(arbol.css_first('#bylineInfo'))
    if marca:
        m = re.search(r'(?:tienda de|Marca:|Brand:)\s*(.+)', marca, re.I)
        r['marca'] = limpio(m.group(1)) if m else marca

    for sel in CONTENEDORES_PRECIO_AMZ:
        cont = arbol.css_first(sel)
        if cont is None:
            continue
        for x in cont.css('style, script'):
            x.decompose()
        precio = None
        for psel in ('.priceToPay', '.apexPriceToPay', '.reinventPricePriceToPayMargin', '#priceblock_dealprice',
                     '#priceblock_ourprice', '#priceblock_saleprice', '#price_inside_buybox', '#newBuyBoxPrice'):
            p = cont.css_first(psel)
            if p is not None:
                precio = _precio_a_price(p) if 'a-price' in (p.attributes.get('class') or '') else (
                    _precio_a_price(p.css_first('.a-price')) or a_numero(p.text()))
            if precio:
                break
        tabla = _tabla_precio_amazon(cont) if cont.css_first('table') is not None else {}
        precio = precio or tabla.get('precio')
        if not precio:
            continue
        r['precio'] = precio
        base = cont.css_first('.basisPrice')
        tachado = (base.css_first('.a-price[data-a-strike="true"]') if base is not None else None) or \
            cont.css_first('.a-price.a-text-price[data-a-strike="true"]')
        anterior = _precio_a_price(tachado) if tachado is not None else tabla.get('precio_anterior')
        if anterior and anterior != precio:
            r['precio_anterior'] = anterior
            etq = _texto(base) if base is not None else tabla.get('etiqueta_anterior')
            if etq:
                m = re.match(r'([^:$\d]+)', etq)
                r['etiqueta_anterior'] = limpio(m.group(1)) if m else None
        pct = cont.css_first('.savingsPercentage')
        r['pct'] = a_pct(pct.text()) if pct is not None else tabla.get('pct')
        r['contenedor_precio'] = sel
        break

    vend = _primero(arbol, ['#sellerProfileTriggerId', '#merchantInfoFeature_feature_div .offer-display-feature-text-message',
                            '#merchant-info', '#tabular-buybox .tabular-buybox-text[tabular-attribute-name="Vendido por"]'])
    if vend is not None:
        v = _texto(vend)
        m = re.search(r'Vendido por\s+(.+?)(?:\s+y\s+(?:enviado|cumplido)|\.|$)', v or '', re.I)
        r['vendido_por'] = limpio(m.group(1)) if m else v
    env = _primero(arbol, ['#fulfillerInfoFeature_feature_div .offer-display-feature-text-message',
                           '#tabular-buybox .tabular-buybox-text[tabular-attribute-name="Enviado desde"]'])
    r['enviado_por'] = _texto(env)
    r['disponibilidad'] = _texto(arbol.css_first('#availability'))
    insignia = arbol.css_first('#dealBadge_feature_div')
    if insignia is not None:
        for x in insignia.css('.aok-hidden'):  # plantillas del contador ("NO_OF_HOURS horas…")
            x.decompose()
    r['insignia'] = _texto(arbol.css_first('#dealBadgeSupportingText')) or _texto(insignia)
    cupon = _primero(arbol, ['#couponBadgeRegularVpc', '#promoPriceBlockMessage_feature_div', '#vpcButton'])
    if cupon is not None and 'cup' in (_texto(cupon) or '').lower():
        r['cupon'] = _texto(cupon)[:120]
    cuotas = _primero(arbol, ['#installmentCalculator_feature_div', '#inemi_feature_div', '#bestFinancingOffer_feature_div'])
    m = RE_MSI.search(_texto(cuotas) or '') if cuotas is not None else None
    if m and 'sin inter' in m.group(0).lower():
        r['msi'] = int(m.group(1))
    r['estado'] = 'ok' if r.get('precio') else 'sin_precio'
    return r


# ------------------------------------------------------------------ Mercado Libre

def _valor(d, *ruta):
    for k in ruta:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def parsear_mercadolibre(contenido: bytes | str) -> dict:
    """Ficha de catálogo (/p/MLM…) o de artículo (articulo.mercadolibre…/MLM-…)."""
    html = a_texto(contenido)
    arbol = LexborHTMLParser(html)
    r = dict(estado='no_producto', plataforma='Mercadolibre')
    estado = json_asignado(html, '__PRELOADED_STATE__') or {}
    ini = estado.get('initialState') or _valor(estado, 'pageState', 'initialState') or {}
    comp = ini.get('components') or {}
    if ini.get('id'):
        r['mlm'] = str(ini['id']).replace('-', '').upper()
    precio_c = comp.get('price') or {}
    p = precio_c.get('price') or {}
    if a_numero(p.get('value')):
        r['precio'] = float(p['value'])
        if a_numero(p.get('original_value')) and float(p['original_value']) != r['precio']:
            r['precio_anterior'] = float(p['original_value'])
        r['pct'] = a_pct(_valor(precio_c, 'discount_label', 'value'))
        r['moneda'] = p.get('currency_id')
        r['origen_precio'] = 'preloaded_state'
        for sub in precio_c.get('subtitles') or []:
            t = sub.get('text') or ''
            m = re.search(r'(\d{1,2})\s*meses', t)
            if m:
                r['cuotas'] = int(m.group(1))
                r['msi'] = int(m.group(1)) if 'sin inter' in t.lower() else None
    sx = comp.get('seller_experiment') or comp.get('seller') or {}
    r['vendido_por'] = _valor(sx, 'seller', 'name') or sx.get('title_value')
    r['seller_id'] = _valor(sx, 'seller', 'id')
    track = json.dumps(sx.get('seller_link') or {})
    m = re.search(r'"item_id":\s*"(MLM\d+)"', track) or re.search(r'(MLM\d{6,})', json.dumps(_valor(precio_c, 'action') or {}))
    r['item_id'] = m.group(1) if m else None
    tienda = json.dumps(_valor(sx, 'seller_info', 'subtitles') or [], ensure_ascii=False)
    r['tienda_oficial'] = True if 'Tienda oficial' in tienda else None
    r['disponibilidad'] = _valor(comp, 'stock_information', 'title', 'text')
    if _valor(comp, 'no_stock_status', 'state') == 'VISIBLE':
        r['disponibilidad'] = 'sin stock'
    r['titulo'] = _valor(comp, 'header', 'title')

    for d in json_ld(arbol):  # respaldo: JSON-LD de producto (sólo nombre/precio/ofertas; se ignoran reseñas)
        if 'Product' not in _tipo(d) and 'offers' not in d:
            continue
        r['titulo'] = r.get('titulo') or limpio(d.get('name'))
        r['marca'] = _valor(d, 'brand', 'name') if isinstance(d.get('brand'), dict) else d.get('brand')
        of = d.get('offers') or {}
        of = of[0] if isinstance(of, list) and of else of
        if not r.get('precio') and isinstance(of, dict) and a_numero(of.get('price') or of.get('lowPrice')):
            r['precio'] = a_numero(of.get('price') or of.get('lowPrice'))
            r['moneda'] = of.get('priceCurrency')
            r['origen_precio'] = 'json_ld'
        if isinstance(of, dict) and of.get('availability') and not r.get('disponibilidad'):
            r['disponibilidad'] = str(of['availability']).rsplit('/', 1)[-1]
        break

    if not r.get('precio'):  # diseño sin estado: microdatos y andes-money-amount
        meta = arbol.css_first('meta[itemprop="price"]')
        if meta is not None and a_numero(meta.attributes.get('content')):
            r['precio'], r['origen_precio'] = a_numero(meta.attributes.get('content')), 'microdatos'
            tach = arbol.css_first('s.andes-money-amount--previous, .andes-money-amount--previous')
            if tach is not None:
                r['precio_anterior'] = a_numero(tach.attributes.get('aria-label') or tach.text())
            pct = arbol.css_first('.andes-money-amount__discount, .ui-pdp-price__second-line__label')
            r['pct'] = a_pct(pct.text()) if pct is not None else None
    if not r.get('mlm'):
        canon = arbol.css_first('link[rel="canonical"]')
        m = RE_MLM.search(canon.attributes.get('href', '')) if canon is not None else None
        r['mlm'] = f'MLM{m.group(1)}' if m else None
    if not r.get('titulo') and not r.get('precio'):
        return r
    if r.get('precio') and r.get('moneda') in (None, 'MXN'):
        r['estado'] = 'ok'
    else:
        r['estado'] = 'sin_stock' if r.get('disponibilidad') == 'sin stock' else 'sin_precio'
    return r


# ------------------------------------------------------------------ tarjetas de páginas de tiendas

CLAVES_NOMBRE = ('productName', 'name', 'displayName', 'title', 'nombre', 'productTitle')
CLAVES_PRECIO = ('sellingPrice', 'salePrice', 'offerPrice', 'finalPrice', 'bestPrice', 'specialPrice', 'promoPrice',
                 'Price', 'price', 'precio', 'currentPrice', 'priceValue')
CLAVES_ANTERIOR = ('ListPrice', 'listPrice', 'list_price', 'wasPrice', 'originalPrice', 'regularPrice', 'basePrice',
                   'PriceWithoutDiscount', 'strikePrice', 'precioLista', 'oldPrice', 'normalPrice')
CLAVES_PCT = ('discountPercentage', 'discountPercent', 'percentOff', 'savingsPercent', 'porcentajeDescuento')
CLAVES_URL = ('url', 'link', 'linkText', 'productUrl', 'href', 'canonicalUrl', 'pdpUrl')
CLAVES_SKU = ('sku', 'productId', 'productReference', 'skuId', 'itemId', 'id')
MARCAS_TACHADO = ('old', 'list', 'strike', 'tachado', 'before', 'antes', 'regular', 'was', 'previous', 'crossed',
                  'line-through')


def _num_campo(d: dict, claves) -> float | None:
    for k in claves:
        v = d.get(k)
        if isinstance(v, dict):
            v = v.get('value') or v.get('amount') or v.get('price')
        n = a_numero(v) if isinstance(v, (int, float, str)) else None
        if n:
            return n
    return None


def _buscar_precio(d, prof=0):
    """Precio y anterior dentro de un producto (profundidad ≤ 4; listas cortas, p. ej. SKUs/ofertas de VTEX)."""
    if prof > 4:
        return None
    if isinstance(d, dict):
        p = _num_campo(d, CLAVES_PRECIO)
        if p:
            return p, _num_campo(d, CLAVES_ANTERIOR), _num_campo(d, CLAVES_PCT)
        for k, v in d.items():
            if isinstance(v, (dict, list)) and k not in ('breadcrumb', 'categories', 'recommendations'):
                x = _buscar_precio(v, prof + 1)
                if x:
                    return x
    elif isinstance(d, list) and len(d) <= 3:
        for v in d:
            x = _buscar_precio(v, prof + 1)
            if x:
                return x
    return None


def _tarjetas_json(obj, base_url, origen, salida, prof=0):
    if prof > 40:
        return
    if isinstance(obj, dict):
        nombre = next((obj[k] for k in CLAVES_NOMBRE if isinstance(obj.get(k), str) and 3 < len(obj[k]) < 300), None)
        if nombre:
            x = _buscar_precio(obj)
            if x:
                url = next((obj[k] for k in CLAVES_URL if isinstance(obj.get(k), str) and obj[k]), None)
                sku = next((str(obj[k]) for k in CLAVES_SKU if isinstance(obj.get(k), (str, int)) and obj[k]), None)
                anterior = x[1] if x[1] and x[1] > x[0] else None
                salida.append(dict(nombre=limpio(nombre), precio=x[0], precio_anterior=anterior,
                                   pct=a_pct(x[2]) if anterior else None, sku=sku,
                                   url=urljoin(base_url, url) if url and not url.startswith('data:') else None,
                                   origen=origen))
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _tarjetas_json(v, base_url, origen, salida, prof + 1)
    elif isinstance(obj, list):
        for v in obj:
            _tarjetas_json(v, base_url, origen, salida, prof + 1)


def _tarjetas_html(arbol, base_url) -> list[dict]:
    """Respaldo: contenedores mínimos con enlace y precio en texto; tachado si hay <del>/<s> o clase 'old/list…'."""
    salida = []
    vistos = set()
    for nodo in arbol.css('li, article, div'):
        txt = nodo.text(separator=' ')
        if len(txt) > 700 or '$' not in txt:
            continue
        precios = [a_numero(m.group(1)) for m in RE_PRECIO_TXT.finditer(txt)]
        precios = [p for p in precios if p]
        enlace = nodo.css_first('a[href]')
        if not precios or enlace is None:
            continue
        # sólo el contenedor más interno: si un hijo directo ya cumple, se omite este
        if any(len(h.text(separator=' ')) < len(txt) and '$' in h.text() and h.css_first('a[href]') is not None
               and RE_PRECIO_TXT.search(h.text()) for h in nodo.iter() if h.tag in ('li', 'article', 'div')):
            continue
        tach = None
        for t in nodo.css('del, s, strike, [class]'):
            clase = (t.attributes.get('class') or '').lower() if t.tag not in ('del', 's', 'strike') else 'strike'
            if any(mk in clase for mk in MARCAS_TACHADO) and RE_PRECIO_TXT.search(t.text() or ''):
                tach = a_numero(RE_PRECIO_TXT.search(t.text()).group(1))
                break
        otros = [p for p in precios if p != tach]
        if not otros:
            continue
        precio = min(otros)
        nombre = None
        for sel in ('[class*="name"]', '[class*="Name"]', '[class*="title"]', '[class*="Title"]', 'h2', 'h3', 'h4', 'a[title]'):
            n = nodo.css_first(sel)
            if n is not None:
                nombre = limpio(n.attributes.get('title') if sel == 'a[title]' else n.text(separator=' '))
                if nombre and not RE_PRECIO_TXT.search(nombre) and len(nombre) > 3:
                    break
                nombre = None
        if not nombre:
            continue
        url = urljoin(base_url, enlace.attributes.get('href') or '')
        if (nombre, precio, url) in vistos:
            continue
        vistos.add((nombre, precio, url))
        pct = None
        m = re.search(r'-\s?(\d{1,2})\s?%|(\d{1,2})\s?%\s*(?:OFF|de descuento|desc)', txt, re.I)
        if m and tach:
            pct = a_pct(m.group(0))
        salida.append(dict(nombre=nombre, precio=precio, precio_anterior=tach if tach and tach > precio else None,
                           pct=pct, sku=None, url=url, origen='html'))
    return salida


def parsear_tarjetas(contenido: bytes | str, base_url: str = '') -> dict:
    """Tarjetas de producto de una página de ofertas: JSON-LD → estado embebido (Next.js/VTEX/…) → HTML."""
    html = a_texto(contenido)
    arbol = LexborHTMLParser(html)
    tarjetas = []
    for d in json_ld(arbol):
        if 'ItemList' in _tipo(d):
            for el in d.get('itemListElement') or []:
                item = el.get('item', el) if isinstance(el, dict) else None
                if isinstance(item, dict):
                    _tarjetas_json(item, base_url, 'json_ld', tarjetas)
        elif 'Product' in _tipo(d):
            of = d.get('offers') or {}
            of = of[0] if isinstance(of, list) and of else of
            p = a_numero(of.get('price') or of.get('lowPrice')) if isinstance(of, dict) else None
            if p and d.get('name'):
                tarjetas.append(dict(nombre=limpio(d['name']), precio=p, precio_anterior=None, pct=None,
                                     sku=d.get('sku'), url=urljoin(base_url, d.get('url') or '') or None, origen='json_ld'))
    if not tarjetas:
        for s in arbol.css('script#__NEXT_DATA__, script[type="application/json"], template[data-varname] script'):
            try:
                obj = json.loads(s.text())
            except (ValueError, TypeError):
                continue
            _tarjetas_json(obj, base_url, 'estado_embebido', tarjetas)
        for var in ('__PRELOADED_STATE__', '__INITIAL_STATE__', '__APOLLO_STATE__', '__STATE__'):
            obj = json_asignado(html, var) if not tarjetas else None
            if obj:
                _tarjetas_json(obj, base_url, 'estado_embebido', tarjetas)
    if not tarjetas:
        tarjetas = _tarjetas_html(arbol, base_url)
    unicas, vistas = [], set()
    for t in tarjetas:
        k = (t['nombre'], t['precio'], t.get('url'))
        if k not in vistas:
            vistas.add(k)
            unicas.append(t)
    titulo = _texto(arbol.css_first('title'))
    return dict(estado='ok' if unicas else 'sin_precio', titulo=titulo, tarjetas=unicas)


# ------------------------------------------------------------------ despacho

def tipo_pagina(url: str) -> str:
    u = url.lower()
    if 'amazon.com.mx' in u and RE_ASIN_URL.search(url):
        return 'amazon'
    if 'mercadolibre.com.mx' in u and (re.search(r'/p/mlm\d+', u) or 'articulo.mercadolibre' in u):
        return 'mercadolibre'
    return 'tienda'


def parsear(contenido: bytes | str, url: str) -> dict:
    t = tipo_pagina(url)
    if t == 'amazon':
        return dict(parsear_amazon(contenido), tipo='amazon')
    if t == 'mercadolibre':
        return dict(parsear_mercadolibre(contenido), tipo='mercadolibre')
    return dict(parsear_tarjetas(contenido, url), tipo='tienda')
