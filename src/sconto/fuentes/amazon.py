"""Amazon México: ficha pública de producto https://www.amazon.com.mx/dp/<ASIN> (precio vigente del día).

No hay API gratuita utilizable: PA-API 5 (Product Advertising API) exige una cuenta de Afiliados con ventas
calificadas y la cierra si no las hay; Keepa (historial de precios de Amazon) es de pago. Por eso sólo se
observa la ficha pública, una vez al día, para la lista fija de ASINs (el mapeo producto → ASIN viene de
Preciómetro o de config/productos_objetivo.csv). No hay backfill: Amazon no publica historial.

robots.txt se descarga una vez por día (data/raw/amazon/<fecha>/robots.txt.gz) y se evalúa con RFC 9309
(coincidencia más larga, comodines `*` y `$`) Y con urllib.robotparser; se exige que ambos permitan la ruta.
Si robots.txt responde 401/403/5xx se asume "no rastrear" (RFC 9309).

Reglas de esta fuente:
- una sola petición por ASIN y día (Cliente sin reintentos), pausa 3–8 s, sin login ni cookies propias;
- CAPTCHA / 503 / 403 → `Bloqueado`: la corrida diaria se detiene, se registra 'bloqueado' y no se vuelve a
  intentar ese día (se reintenta al día siguiente);
- precio_anterior_anunciado sólo si la ficha muestra un precio tachado (data-a-strike) visible;
  pct_descuento_anunciado = número que muestra la ficha (Amazon pinta "-33%": se guarda 33, positivo =
  descuento; el texto original queda en condiciones.ahorro_texto). Nada se calcula aquí.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import urllib.robotparser
from urllib.parse import quote_plus, urlsplit

import pandas as pd
from selectolax.lexbor import LexborHTMLParser

from sconto.almacen import ahora_utc, escribir_bronze, guardar_crudo, hoy, leer_crudo, registrar_estado, sha256_bytes
from sconto.cliente import MARCAS_CAPTCHA, USER_AGENT, Bloqueado, Cliente, NoPermitido
from sconto.esquema import CLAVE, a_dataframe, condiciones_json
from sconto.normalizar import compacto
from sconto.rutas import BRONZE, ESTADO_FUENTES, LOGS, RAIZ, RAW, asegurar_directorios

log = logging.getLogger('amazon')

FUENTE = 'amazon'
FUENTE_CAPTURAS = 'amazon_capturas'  # una fila por ASIN pedido: resultado de la petición (auditoría)
BASE = 'https://www.amazon.com.mx'
RE_ASIN = re.compile(r'^[A-Z0-9]{10}$')
RE_ASIN_URL = re.compile(r'/(?:dp|gp/product)/([A-Z0-9]{10})')

# Páginas de verificación propias de Amazon (además de sconto.cliente.MARCAS_CAPTCHA).
MARCAS_AMAZON = ('/errors/validatecaptcha', 'opfcaptcha', 'api-services-support@amazon.com',
                 'introduce los caracteres que ves', 'type the characters you see in this image',
                 'no eres un robot', "make sure you're not a robot", 'para continuar comprando',
                 'to discuss automated access to amazon data')

# Bloques de precio del "buy box" (el precio que paga quien compra). Fuera de ellos hay carruseles y
# patrocinados con precios de OTROS productos: nunca se leen.
BLOQUES_PRECIO = ('#corePriceDisplay_desktop_feature_div', '#corePrice_desktop', '#corePrice_feature_div',
                  '#apex_desktop', '#apex_offerDisplay_desktop')
SEL_PRECIO = ('#corePriceDisplay_desktop_feature_div .priceToPay',
              '#corePriceDisplay_desktop_feature_div .apexPriceToPay',
              '#apex_desktop .priceToPay', '#apex_desktop .apexPriceToPay',
              '#corePrice_desktop .apexPriceToPay',
              '#corePrice_feature_div .a-price:not(.a-text-price)',
              '#priceblock_dealprice', '#priceblock_ourprice', '#price_inside_buybox', '#newBuyBoxPrice')


def cliente_amazon() -> Cliente:
    """Una petición por URL: con reintentos=0 un 503/429 se convierte de inmediato en `Bloqueado`.
    La detección de CAPTCHA genérica de Cliente se reemplaza por `clasificar` (evita falsos positivos en
    fichas que mencionan 'captcha' en sus scripts y añade las marcas de Amazon)."""
    c = Cliente(pausa=(3.0, 8.0), reintentos=0, detectar_captcha=False)
    c.sesion.headers['Accept'] = 'text/html,application/xhtml+xml'
    return c


def url_ficha(asin: str) -> str:
    return f'{BASE}/dp/{asin}'


# ---------------------------------------------------------------- robots.txt

def _grupos_robots(texto: str) -> list[tuple[list[str], list[tuple[bool, str]]]]:
    grupos, actual, en_agentes = [], None, False
    for linea in texto.splitlines():
        linea = linea.split('#', 1)[0].strip()
        if ':' not in linea:
            continue
        campo, valor = (s.strip() for s in linea.split(':', 1))
        campo = campo.lower()
        if campo == 'user-agent':
            if not en_agentes:
                actual = ([], [])
                grupos.append(actual)
            actual[0].append(valor.lower())
            en_agentes = True
        else:
            if campo in ('allow', 'disallow') and actual is not None and valor:
                actual[1].append((campo == 'allow', valor))
            en_agentes = False
    return grupos


def reglas_para(texto: str, agente: str = USER_AGENT) -> list[tuple[bool, str]]:
    """Reglas del grupo que nombra nuestro token de producto; si ninguno lo nombra, las del grupo '*'."""
    token = agente.split('/')[0].strip().lower()
    grupos = _grupos_robots(texto)
    propios = [r for agentes, reglas in grupos if token in agentes for r in reglas]
    if any(token in agentes for agentes, _ in grupos):
        return propios
    return [r for agentes, reglas in grupos if '*' in agentes for r in reglas]


def _coincide(patron: str, ruta: str) -> bool:
    fin = patron.endswith('$')
    cuerpo = re.escape(patron[:-1] if fin else patron).replace(r'\*', '.*')
    return re.match(cuerpo + ('$' if fin else ''), ruta) is not None


def permitido(texto: str, url: str, agente: str = USER_AGENT) -> bool:
    """RFC 9309 (la regla más larga gana; empate → Allow) y además urllib.robotparser: ambos deben permitir."""
    p = urlsplit(url)
    ruta = (p.path or '/') + (f'?{p.query}' if p.query else '')
    if ruta == '/robots.txt':
        return True
    mejor = None
    for allow, patron in reglas_para(texto, agente):
        if _coincide(patron, ruta):
            candidato = (len(patron), allow)
            mejor = candidato if mejor is None or candidato > mejor else mejor
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(texto.splitlines())
    return (mejor is None or mejor[1]) and rp.can_fetch(agente, url)


def leer_robots(cliente: Cliente, fecha: str | None = None) -> str:
    """robots.txt del día (caché en data/raw). Lo entrega también a `cliente` para que no lo pida de nuevo."""
    fecha = fecha or hoy()
    ruta = RAW / FUENTE / fecha / 'robots.txt.gz'
    if ruta.exists():
        texto = leer_crudo(ruta.relative_to(RAIZ).as_posix()).decode('utf-8', 'replace')
    else:
        previo, cliente.respetar_robots = cliente.respetar_robots, False
        try:
            r = cliente.get(BASE + '/robots.txt')
        finally:
            cliente.respetar_robots = previo
        if r.status_code in (401, 403) or r.status_code >= 500:
            raise Bloqueado(f'robots.txt HTTP {r.status_code}: se asume no rastrear (RFC 9309)')
        texto = '' if r.status_code >= 400 else r.text
        guardar_crudo(FUENTE, 'robots.txt', texto, fecha)
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(texto.splitlines())
    cliente._robots[BASE] = rp
    return texto


def resumen_robots(texto: str) -> dict:
    bloqueos_totales = sorted({a for agentes, reglas in _grupos_robots(texto) for a in agentes
                               if a != '*' and (False, '/') in reglas})
    return dict(dp=permitido(texto, url_ficha('B0C29CL98P')),
                busqueda=permitido(texto, f'{BASE}/s?k=bocina+bluetooth'),
                grupo_aplicable='*' if not any(USER_AGENT.split('/')[0].lower() in a
                                               for a, _ in _grupos_robots(texto)) else 'propio',
                reglas_dp=[p for _, p in reglas_para(texto) if p.startswith('/dp/')],
                agentes_bloqueados_totalmente=bloqueos_totales)


# ---------------------------------------------------------------- análisis de la ficha

def _texto(nodo) -> str | None:
    if nodo is None:
        return None
    t = re.sub(r'[\s‎‏]+', ' ', nodo.text(deep=True, separator=' ', strip=True)).strip()
    return t or None


def a_numero(texto: str | None) -> float | None:
    """'$1,299.00' → 1299.0 (formato mexicano: coma de miles, punto decimal)."""
    if not texto:
        return None
    m = re.search(r'\d[\d,]*(?:\.\d+)?', texto.replace('\xa0', ' '))
    if not m:
        return None
    v = float(m.group(0).replace(',', ''))
    return v if v > 0 else None


def _precio_nodo(nodo) -> str | None:
    """Texto del precio. En la ficha real `.a-offscreen` llega vacío (precio a pagar) o con 'null' (precio de
    lista): entonces se usa la parte visible (entero + fracción, o el span aria-hidden)."""
    candidatos = [_texto(nodo.css_first('.a-offscreen'))]
    entero = _texto(nodo.css_first('.a-price-whole'))
    if entero:
        fraccion = _texto(nodo.css_first('.a-price-fraction')) or '00'
        candidatos.append(f"${entero.rstrip('. ')}.{fraccion}")
    candidatos += [_texto(nodo.css_first('[aria-hidden="true"]')), _texto(nodo)]
    return next((c for c in candidatos if a_numero(c)), None)


def _oculto(nodo, niveles=6) -> bool:
    n = nodo
    for _ in range(niveles):
        if n is None:
            return False
        clases = (n.attributes.get('class') or '').split()
        if 'aok-hidden' in clases or 'a-hidden' in clases or 'pricePerUnit' in clases:
            return True
        n = n.parent
    return False


def _etiqueta(nodo, texto_precio: str) -> str | None:
    """Texto que acompaña al precio tachado: 'Precio de lista:', 'Antes:', 'Precio típico:'..."""
    n = nodo.parent
    for _ in range(4):
        if n is None:
            break
        fila = n if n.tag == 'tr' else None
        t = _texto(n.css_first('td')) if fila is not None else _texto(n)
        if t:
            antes = t.split(texto_precio)[0] if texto_precio and texto_precio in t else t.split('$')[0]
            antes = re.sub(r'\bnull\b', '', antes).strip(' :')  # a-offscreen llega como 'null'
            if re.search(r'[A-Za-zÁÉÍÓÚáéíóú]', antes):
                return antes[:60]
        n = n.parent
    return None


def _precio_actual(arbol):
    for sel in SEL_PRECIO:
        for n in arbol.css(sel):
            if _oculto(n):
                continue
            t = _precio_nodo(n)
            v = a_numero(t)
            if v:
                return v, t, sel
    return None, None, None


def _precio_anterior(arbol):
    for bloque in BLOQUES_PRECIO:
        b = arbol.css_first(bloque)
        if b is None:
            continue
        for n in b.css('.a-price[data-a-strike="true"]'):
            if _oculto(n):
                continue
            t = _precio_nodo(n)
            v = a_numero(t)
            if v:
                return v, t, _etiqueta(n, t)
    return None, None, None


def _ahorro(arbol):
    for bloque in BLOQUES_PRECIO:
        b = arbol.css_first(bloque)
        if b is None:
            continue
        n = b.css_first('.savingsPercentage')
        t = _texto(n) if n is not None and not _oculto(n) else None
        if not t:  # diseño antiguo en tabla: "Ahorras: $500.00 (33%)"
            m = re.search(r'Ahorr\w*:?[^()%]{0,40}\((\d{1,3})\s*%\)', _texto(b) or '')
            t = m.group(0) if m else None
        if not t:  # etiqueta accesible del precio a pagar: "$1,299.00 con un ahorro del 35%"
            etiqueta = _texto(b.css_first('#apex-pricetopay-accessibility-label')) or ''
            m = re.search(r'ahorro del\s*\d{1,3}(?:\.\d+)?\s*%', etiqueta)
            t = m.group(0) if m else None
        if t:
            m = re.search(r'(\d{1,3}(?:\.\d+)?)\s*%', t)
            if m:
                return float(m.group(1)), t
    return None, None


def _limpiar_nombre(t: str | None) -> str | None:
    return t.strip(' .') or None if t else None


def _vendedores(arbol):
    vendido = (_texto(arbol.css_first('#merchantInfoFeature_feature_div .offer-display-feature-text-message'))
               or _texto(arbol.css_first('[tabular-attribute-name="Vendido por"] .tabular-buybox-text-message'))
               or _texto(arbol.css_first('#sellerProfileTriggerId')))
    enviado = (_texto(arbol.css_first('#fulfillerInfoFeature_feature_div .offer-display-feature-text-message'))
               or _texto(arbol.css_first('[tabular-attribute-name="Enviado desde"] .tabular-buybox-text-message'))
               or _texto(arbol.css_first('[tabular-attribute-name="Enviado por"] .tabular-buybox-text-message')))
    if not (vendido and enviado):  # diseño antiguo: "Vendido por X y enviado por Amazon."
        info = _texto(arbol.css_first('#merchant-info')) or ''
        m = re.search(r'Vendido y enviado por (.+?)(?:\.|$)', info, re.I)
        if m:
            vendido = vendido or m.group(1)
            enviado = enviado or m.group(1)
        else:
            m1 = re.search(r'Vendido por (.+?)(?: y | Enviado|\.|$)', info, re.I)
            m2 = re.search(r'enviado por (.+?)(?:\.|$)', info, re.I)
            vendido = vendido or (m1.group(1) if m1 else None)
            enviado = enviado or (m2.group(1) if m2 else None)
    return _limpiar_nombre(vendido), _limpiar_nombre(enviado)


def _detalles(arbol) -> dict:
    """Tablas 'Información del producto' y viñetas de detalles → {etiqueta en minúsculas: valor}."""
    d = {}
    for fila in arbol.css('#prodDetails tr, #productDetails_techSpec_section_1 tr, '
                          '#productDetails_detailBullets_sections1 tr, #productOverview_feature_div tr'):
        celdas = fila.css('th, td')
        if len(celdas) >= 2:
            k, v = _texto(celdas[0]), _texto(celdas[-1])
            if k and v:
                d.setdefault(k.lower().strip(' :'), v)
    for li in arbol.css('#detailBullets_feature_div li'):
        t = _texto(li) or ''
        if ':' in t:
            k, v = t.split(':', 1)
            d.setdefault(k.lower().strip(' :'), v.strip())
    return d


def _buscar_texto(arbol, selectores, patron):
    for sel in selectores:
        for n in arbol.css(sel):
            if _oculto(n):
                continue
            t = _texto(n)
            if t and re.search(patron, t, re.I):
                return t
    return None


def parsear_ficha(html: str | bytes, asin_pedido: str | None = None) -> dict:
    """Campos visibles de la ficha. Lo que la página no muestra queda en None (no se imputa)."""
    if isinstance(html, bytes):
        html = html.decode('utf-8', 'replace')
    arbol = LexborHTMLParser(html)
    asin_input = arbol.css_first('input#ASIN') or arbol.css_first('input[name="ASIN"]')
    canonica = arbol.css_first('link[rel="canonical"]')
    m = RE_ASIN_URL.search(canonica.attributes.get('href') or '') if canonica else None
    asin_pagina = (asin_input.attributes.get('value') if asin_input else None) or (m.group(1) if m else None)
    for n in arbol.css('script, style, noscript, template'):
        n.decompose()

    titulo = _texto(arbol.css_first('#productTitle'))
    precio, precio_texto, sel_precio = _precio_actual(arbol)
    anterior, anterior_texto, etiqueta = _precio_anterior(arbol)
    pct, ahorro_texto = _ahorro(arbol)
    vendido, enviado = _vendedores(arbol)
    detalles = _detalles(arbol)

    disponibilidad = (_texto(arbol.css_first('#availability')) or _texto(arbol.css_first('#outOfStock'))
                      or _texto(arbol.css_first('#availabilityInsideBuyBox_feature_div')))
    oferta = _buscar_texto(arbol, ('#dealBadge_feature_div', '#dealBadgeSupportingText', '.dealBadge',
                                   '#corePriceDisplay_desktop_feature_div .a-badge-text'), r'oferta|deal')
    cupon_texto = _buscar_texto(arbol, ('#promoPriceBlockMessage_feature_div', '[id^="couponBadge"]', '#vpcButton',
                                        '.couponLabelText', '[id^="couponText"]'), r'cup[oó]n')
    promocion = _buscar_texto(arbol, ('#promoPriceBlockMessage_feature_div', '#applicablePromotionList_feature_div'),
                              r'\w')
    msi_texto, msi_meses = None, None
    for sel in ('#installmentCalculator_feature_div', '#inemi_feature_div', '#best-offer-string-cc',
                '#corePriceDisplay_desktop_feature_div', '#apex_desktop', '#rightCol'):
        for n in arbol.css(sel):
            t = _texto(n) or ''
            m = re.search(r'(\d{1,2})\s*(?:meses sin intereses|MSI\b)', t, re.I)
            if m and not _oculto(n):
                msi_meses = int(m.group(1))
                inicio = max(0, m.start() - 40)
                msi_texto = t[inicio:m.end() + 60].strip()
                break
        if msi_meses:
            break
    # Pagos a plazos que la ficha NO anuncia como sin intereses ("$573.47 x12 meses"): sólo se describe.
    plazos_texto = None
    for sel in ('#apex_desktop', '#corePriceDisplay_desktop_feature_div', '#installmentCalculator_feature_div'):
        m = re.search(r'(\$\s?[\d,]+\.\d{2})(?:\s*\$\s*[\d,]+\s*\.\s*\d{2})?\s*(x\s*\d{1,2}\s*meses)',
                      _texto(arbol.css_first(sel)) or '')
        if m:
            plazos_texto = f'{m.group(1)} {m.group(2)}'
            break

    marca =(_texto(arbol.css_first('#productOverview_feature_div tr.po-brand td.a-span9'))
             or detalles.get('marca'))
    if not marca:
        byline = _texto(arbol.css_first('#bylineInfo')) or ''
        m = re.search(r'(?:tienda de|Marca:)\s*(.+)', byline, re.I)
        marca = m.group(1).strip() if m else None
    modelo = next((detalles[k] for k in ('número de modelo del producto', 'numero de modelo del producto',
                                          'número de modelo', 'modelo', 'nombre del modelo') if detalles.get(k)), None)

    titulo_l = (titulo or '').lower()
    renovado = arbol.css_first('#renewedProgramDescriptionAtf_feature_div') is not None and \
        bool(_texto(arbol.css_first('#renewedProgramDescriptionAtf_feature_div')))
    if 'reacondicionad' in titulo_l or 'renewed' in titulo_l or renovado:
        condicion = 'reacondicionado'
    elif precio is not None and arbol.css_first('#usedBuySection') is not None and \
            arbol.css_first('#newAccordionRow, #newAccordionRow_0, #buyNewSection') is None and \
            sel_precio is None:
        condicion = 'usado'
    elif precio is not None:
        condicion = 'nuevo'
    else:
        condicion = None
    prime = any(arbol.css_first(f'{b} .a-icon-prime') is not None for b in BLOQUES_PRECIO + ('#deliveryBlockMessage',))
    envio = _texto(arbol.css_first('#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE')) or \
        _texto(arbol.css_first('#deliveryBlockMessage'))
    return dict(asin_pedido=asin_pedido, asin_pagina=asin_pagina, titulo=titulo, precio=precio,
                precio_texto=precio_texto, precio_anterior=anterior, precio_anterior_texto=anterior_texto,
                etiqueta_precio_anterior=etiqueta, pct_ahorro=pct, ahorro_texto=ahorro_texto,
                vendido_por=vendido, enviado_por=enviado,
                disponibilidad=disponibilidad[:200] if disponibilidad else None,
                oferta=oferta[:120] if oferta else None,
                oferta_relampago=bool(oferta and re.search(r'rel[aá]mpago|lightning', oferta, re.I)),
                cupon=cupon_texto[:160] if cupon_texto else None,
                promocion=promocion[:160] if promocion and promocion != cupon_texto else None,
                msi_meses=msi_meses, msi_texto=msi_texto, plazos_texto=plazos_texto, condicion=condicion,
                prime=prime,
                envio=envio[:160] if envio else None, marca=marca, modelo=modelo)


def clasificar(status: int, html: str | bytes, tipo: str = 'ficha') -> str:
    """ficha | busqueda | no_encontrado | captcha | desconocida."""
    if isinstance(html, bytes):
        html = html.decode('utf-8', 'replace')
    t = html.lower()
    if status == 404:
        return 'no_encontrado'
    if tipo == 'ficha' and 'id="producttitle"' in t:
        return 'ficha'
    if tipo == 'busqueda' and 'data-component-type="s-search-result"' in t:
        return 'busqueda'
    if any(m in t for m in MARCAS_AMAZON) or any(m in t[:20000] for m in MARCAS_CAPTCHA):
        return 'captcha'
    if tipo == 'busqueda' and status == 200 and 's-result-list' in t:
        return 'busqueda'  # búsqueda sin resultados
    return 'desconocida'


def fila_observacion(f: dict, asin: str, producto_canonico_id, fecha: str, ruta_raw: str, hash_raw: str) -> dict:
    return dict(
        fuente=FUENTE, metodo='scraping', canal='en_linea', tipo_precio='oferta_vigente',
        fecha_precio=fecha, fecha_captura=fecha, producto_canonico_id=producto_canonico_id,
        id_externo=asin, tipo_id_externo='asin', marca=f['marca'],
        modelo_normalizado=compacto(f['modelo']) or None, descripcion_original=f['titulo'],
        plataforma='Amazon', vendedor_o_cadena=f['vendido_por'], precio=f['precio'],
        precio_anterior_anunciado=f['precio_anterior'], pct_descuento_anunciado=f['pct_ahorro'], moneda='MXN',
        disponibilidad=f['disponibilidad'],
        condiciones=condiciones_json(
            vendido_por=f['vendido_por'], enviado_por=f['enviado_por'], condicion=f['condicion'],
            cupon=f['cupon'], promocion=f['promocion'], msi_meses=f['msi_meses'], msi_texto=f['msi_texto'],
            plazos_texto=f['plazos_texto'],
            oferta=f['oferta'], oferta_relampago=True if f['oferta_relampago'] else None,
            prime=True if f['prime'] else None, envio=f['envio'], precio_texto=f['precio_texto'],
            etiqueta_precio_anterior=f['etiqueta_precio_anterior'], ahorro_texto=f['ahorro_texto'],
            asin_pagina=f['asin_pagina'] if f['asin_pagina'] and f['asin_pagina'] != asin else None),
        url=url_ficha(asin), ruta_raw=ruta_raw, hash_raw=hash_raw,
        asin_pagina=f['asin_pagina'], condicion=f['condicion'])


def validar(df: pd.DataFrame) -> list[str]:
    """Reglas del esquema común; devuelve la lista de problemas (vacía = válido)."""
    problemas = []
    if df.empty:
        return problemas
    if df.duplicated(CLAVE).any():
        problemas.append(f'{int(df.duplicated(CLAVE).sum())} duplicados por CLAVE')
    if not (pd.to_numeric(df.precio, errors='coerce') > 0).all():
        problemas.append('precio no positivo o faltante')
    for c in ('fecha_precio', 'fecha_captura'):
        if pd.to_datetime(df[c], errors='coerce', format='%Y-%m-%d').isna().any():
            problemas.append(f'{c} inválida')
    pct = pd.to_numeric(df.pct_descuento_anunciado, errors='coerce').dropna()
    if not pct.between(-100, 100).all():
        problemas.append('pct fuera de [-100, 100]')
    return problemas


# ---------------------------------------------------------------- descarga

def _ruta_cache(asin: str, fecha: str, sufijo: str = '') -> 'Path':
    return RAW / FUENTE / fecha / f'{asin}{sufijo}.html.gz'


def descargar_ficha(cliente: Cliente, asin: str, fecha: str, solo_cache: bool = False) -> dict:
    """Devuelve dict(clase, contenido, ruta_raw, hash_raw, http, reutilizado, url_final).
    Reutiliza la ficha o el 404 ya guardados ese día (idempotente); las páginas de bloqueo no se reutilizan."""
    for sufijo, clase in (('', 'ficha'), ('.404', 'no_encontrado')):
        ruta = _ruta_cache(asin, fecha, sufijo)
        if ruta.exists():
            rel = ruta.relative_to(RAIZ).as_posix()
            contenido = leer_crudo(rel)
            return dict(clase=clase, contenido=contenido, ruta_raw=rel, hash_raw=sha256_bytes(contenido),
                        http=None, reutilizado=True, url_final=None)
    if solo_cache:
        return dict(clase='sin_cache', contenido=None, ruta_raw=None, hash_raw=None, http=None,
                    reutilizado=False, url_final=None)
    r = cliente.get(url_ficha(asin))
    clase = clasificar(r.status_code, r.content)
    if clase == 'ficha' and r.status_code >= 400:
        clase = 'desconocida'
    sufijo = {'ficha': '', 'no_encontrado': '.404', 'captcha': '.bloqueo'}.get(clase, '.desconocida')
    rel, h = guardar_crudo(FUENTE, f'{asin}{sufijo}.html', r.content, fecha)
    return dict(clase=clase, contenido=r.content, ruta_raw=rel, hash_raw=h, http=r.status_code,
                reutilizado=False, url_final=r.url)


def _bloqueado_hoy(fecha: str, entorno: str) -> bool:
    if not ESTADO_FUENTES.exists():
        return False
    e = pd.read_csv(ESTADO_FUENTES, dtype=str)
    e = e.loc[(e.fuente == FUENTE) & (e.fecha == fecha) & (e.entorno.fillna('local') == entorno)]
    return bool(len(e)) and e.estado.iloc[-1] == 'bloqueado'


def _guardar(fuente: str, df: pd.DataFrame, fecha: str, columna_id: str, clave: list[str]):
    """Como escribir_bronze, pero primero quita del archivo del día los ids re-procesados (si el parser cambió
    el vendedor, la CLAVE cambiaría y quedarían dos filas del mismo ASIN y día)."""
    if df.empty:
        return
    ruta = BRONZE / fuente / f'{fecha}.parquet'
    if ruta.exists():
        previo = pd.read_parquet(ruta)
        resto = previo.loc[~previo[columna_id].isin(df[columna_id])]
        if len(resto) < len(previo):
            if resto.empty:
                ruta.unlink()
            else:
                resto.to_parquet(ruta, index=False)
    escribir_bronze(fuente, df, fecha, clave=clave)


def asins_de_productos(productos: pd.DataFrame | None) -> list[tuple[str, str | None]]:
    """[(ASIN, producto_canonico_id)] sin repetir, en el orden de la lista fija."""
    salida, vistos = [], set()
    if productos is None or productos.empty or 'asins' not in productos.columns:
        return salida
    for fila in productos.to_dict('records'):
        pid = fila.get('producto_canonico_id')
        pid = None if pid is None or (not isinstance(pid, str) and pd.isna(pid)) else str(pid)
        crudo = fila.get('asins')
        crudo = '' if crudo is None or (not isinstance(crudo, str) and pd.isna(crudo)) else str(crudo)
        for a in re.split(r'[;,\s]+', crudo):
            a = a.strip().upper()
            if RE_ASIN.match(a) and a not in vistos:
                vistos.add(a)
                salida.append((a, pid))
    return salida


def correr(objetivos: list[tuple[str, str | None]], fecha: str | None = None, entorno: str = 'local',
           max_bloqueos: int = 1, forzar: bool = False, cliente: Cliente | None = None) -> dict:
    """Recorre la lista fija. `max_bloqueos` = bloqueos/anomalías seguidos tras los que se detiene (diario: 1)."""
    fecha = fecha or hoy()
    inicio = ahora_utc()
    solo_cache = fecha != hoy()  # una fecha pasada sólo se re-procesa desde el crudo guardado
    resumen = dict(fecha=fecha, solicitados=len(objetivos), descargados=0, reutilizados=0, fichas=0, con_precio=0,
                   sin_precio=0, con_precio_anterior=0, con_pct=0, no_encontrados=0, bloqueos=0, anomalias=0,
                   errores=0, sin_cache=0, detenido=None, filas=0)
    if not objetivos:
        resumen['detenido'] = 'lista vacía'
        return resumen
    if not forzar and not solo_cache and _bloqueado_hoy(fecha, entorno):
        resumen['detenido'] = f'ya bloqueado el {fecha}; se reintenta otro día (use --forzar sólo con criterio)'
        log.warning(resumen['detenido'])
        return resumen
    cliente = cliente or cliente_amazon()
    try:
        robots = leer_robots(cliente, fecha) if not solo_cache or (RAW / FUENTE / fecha / 'robots.txt.gz').exists() \
            else ''
    except Bloqueado as e:
        resumen['detenido'] = str(e)
        registrar_estado(FUENTE, 'bloqueado', 0, str(resumen), inicio, fecha, entorno)
        return resumen
    if robots and not permitido(robots, url_ficha(objetivos[0][0])):
        resumen['detenido'] = 'robots.txt no permite /dp/ para nuestro user-agent'
        registrar_estado(FUENTE, 'fallo', 0, str(resumen), inicio, fecha, entorno)
        return resumen

    filas, capturas, seguidos = [], [], 0
    for asin, pid in objetivos:
        cap = dict(asin=asin, producto_canonico_id=pid, fecha_captura=fecha, hora_utc=ahora_utc(),
                   url=url_ficha(asin), clase=None, http=None, reutilizado=False, titulo=None, precio=None,
                   precio_anterior=None, pct_ahorro=None, vendido_por=None, disponibilidad=None,
                   ruta_raw=None, hash_raw=None, detalle=None)
        try:
            d = descargar_ficha(cliente, asin, fecha, solo_cache=solo_cache)
            cap.update(hora_utc=ahora_utc())  # al recibir la respuesta (la pausa de Cliente ocurre antes)
            cap.update(clase=d['clase'], http=d['http'], reutilizado=d['reutilizado'], ruta_raw=d['ruta_raw'],
                       hash_raw=d['hash_raw'], detalle=d['url_final'])
            resumen['reutilizados' if d['reutilizado'] else 'descargados'] += d['clase'] != 'sin_cache'
            if d['clase'] == 'ficha':
                seguidos = 0
                resumen['fichas'] += 1
                f = parsear_ficha(d['contenido'], asin)
                cap.update(titulo=f['titulo'], precio=f['precio'], precio_anterior=f['precio_anterior'],
                           pct_ahorro=f['pct_ahorro'], vendido_por=f['vendido_por'],
                           disponibilidad=f['disponibilidad'])
                if f['precio']:
                    filas.append(fila_observacion(f, asin, pid, fecha, d['ruta_raw'], d['hash_raw']))
                    resumen['con_precio'] += 1
                    resumen['con_precio_anterior'] += f['precio_anterior'] is not None
                    resumen['con_pct'] += f['pct_ahorro'] is not None
                else:
                    resumen['sin_precio'] += 1  # sin buy box / agotado: faltante, no se imputa
            elif d['clase'] == 'no_encontrado':
                seguidos = 0
                resumen['no_encontrados'] += 1
            elif d['clase'] == 'sin_cache':
                resumen['sin_cache'] += 1
            else:
                seguidos += 1
                resumen['bloqueos' if d['clase'] == 'captcha' else 'anomalias'] += 1
                log.error('%s en %s (HTTP %s)', d['clase'], asin, d['http'])
        except Bloqueado as e:  # 503 / 403 / 429 (Cliente sin reintentos)
            seguidos += 1
            resumen['bloqueos'] += 1
            m = re.match(r'(\d{3})', str(e))
            cap.update(clase=f'http_{m.group(1)}' if m else 'bloqueado', http=int(m.group(1)) if m else None,
                       detalle=str(e))
            log.error('BLOQUEADO en %s: %s', asin, e)
        except NoPermitido as e:
            cap.update(clase='no_permitido', detalle=str(e))
            resumen['detenido'] = f'robots.txt no permite {e}'
            capturas.append(cap)
            break
        except Exception as e:  # una ficha rara no detiene la corrida
            resumen['errores'] += 1
            cap.update(clase='error', detalle=f'{type(e).__name__}: {e}'[:300])
            log.exception('error en %s', asin)
        capturas.append(cap)
        if seguidos >= max_bloqueos:
            resumen['detenido'] = f'{seguidos} bloqueo(s)/anomalía(s) seguidos en {asin}; se reintenta otro día'
            log.error(resumen['detenido'])
            break

    df = a_dataframe(filas)
    problemas = validar(df)
    if problemas:
        raise ValueError(f'Filas inválidas para bronze: {problemas}')
    _guardar(FUENTE, df, fecha, 'id_externo', CLAVE)
    # Las capturas reutilizadas no reemplazan la fila original (conserva HTTP y hora de la descarga real).
    _guardar(FUENTE_CAPTURAS, pd.DataFrame([c for c in capturas if not c['reutilizado']]), fecha, 'asin',
             ['asin', 'fecha_captura'])
    resumen['filas'] = len(df)
    procesados = resumen['fichas'] + resumen['no_encontrados']
    if resumen['bloqueos']:
        estado = 'bloqueado'
    elif resumen['detenido'] or resumen['errores'] or resumen['anomalias'] or resumen['sin_cache']:
        estado = 'parcial' if procesados else 'fallo'
    else:
        estado = 'ok' if procesados else 'fallo'
    registrar_estado(FUENTE, estado, len(df), detalle=str(resumen), inicio_utc=inicio, fecha=fecha, entorno=entorno)
    resumen['estado'] = estado
    return resumen


def diario(productos: pd.DataFrame, fecha: str | None = None, entorno: str = 'local', max_asins: int | None = None,
           **kw) -> dict:
    """Colector diario: una ficha por ASIN de la lista fija; al primer bloqueo se detiene ('bloqueado')."""
    kw.setdefault('max_bloqueos', 1)
    objetivos = asins_de_productos(productos)
    return correr(objetivos[:max_asins] if max_asins else objetivos, fecha=fecha, entorno=entorno, **kw)


def reparsear(fecha: str) -> dict:
    """Vuelve a construir bronze del día desde los crudos guardados (sin red), p. ej. tras mejorar el parser."""
    caps = BRONZE / FUENTE_CAPTURAS / f'{fecha}.parquet'
    mapa = {}
    if caps.exists():
        c = pd.read_parquet(caps)
        mapa = dict(zip(c.asin, c.producto_canonico_id))
    objetivos = [(p.name.split('.')[0], mapa.get(p.name.split('.')[0]))
                 for p in sorted((RAW / FUENTE / fecha).glob('*.html.gz'))
                 if RE_ASIN.match(p.name.split('.')[0]) and p.name.count('.') == 2]
    filas = []
    for asin, pid in objetivos:
        d = descargar_ficha(None, asin, fecha, solo_cache=True)
        f = parsear_ficha(d['contenido'], asin)
        if f['precio']:
            filas.append(fila_observacion(f, asin, pid, fecha, d['ruta_raw'], d['hash_raw']))
    df = a_dataframe(filas)
    problemas = validar(df)
    if problemas:
        raise ValueError(problemas)
    _guardar(FUENTE, df, fecha, 'id_externo', CLAVE)
    return dict(fecha=fecha, fichas=len(objetivos), filas=len(df))


# ---------------------------------------------------------------- búsqueda (robots la permite para '*')

def parsear_busqueda(html: str | bytes, maximo: int = 20) -> list[dict]:
    if isinstance(html, bytes):
        html = html.decode('utf-8', 'replace')
    arbol = LexborHTMLParser(html)
    for n in arbol.css('script, style, noscript'):
        n.decompose()
    salida = []
    for n in arbol.css('div[data-component-type="s-search-result"]'):
        asin = (n.attributes.get('data-asin') or '').strip().upper()
        if not RE_ASIN.match(asin):
            continue
        h2 = n.css_first('h2')
        titulo = (h2.attributes.get('aria-label') if h2 else None) or _texto(h2)
        precio_nodo = n.css_first('.a-price:not(.a-text-price)')
        precio_texto = _precio_nodo(precio_nodo) if precio_nodo else None
        tachado = n.css_first('.a-price[data-a-strike="true"]')
        texto = (_texto(n) or '').lower()
        salida.append(dict(posicion=len(salida) + 1, asin=asin, titulo=titulo, precio=a_numero(precio_texto),
                           precio_anterior=a_numero(_precio_nodo(tachado)) if tachado else None,
                           patrocinado='patrocinado' in texto or 'sponsored' in texto))
        if len(salida) >= maximo:
            break
    return salida


def buscar(texto: str, cliente: Cliente | None = None, fecha: str | None = None, maximo: int = 20) -> list[dict]:
    """Primera página de resultados de /s?k=. Sólo para mapear un modelo a candidatos de ASIN (revisión manual);
    no se usa para rastrear catálogos. Caché por día y texto."""
    fecha = fecha or hoy()
    cliente = cliente or cliente_amazon()
    url = f'{BASE}/s?k={quote_plus(texto)}'
    if not permitido(leer_robots(cliente, fecha), url):
        raise NoPermitido(url)
    nombre = 'busqueda_' + (compacto(texto)[:60] or 'vacia')
    ruta = RAW / FUENTE / fecha / f'{nombre}.html.gz'
    if ruta.exists():
        contenido = leer_crudo(ruta.relative_to(RAIZ).as_posix())
    else:
        r = cliente.get(url)
        clase = clasificar(r.status_code, r.content, tipo='busqueda')
        if clase != 'busqueda':
            guardar_crudo(FUENTE, f'{nombre}.{clase}.html', r.content, fecha)
            raise Bloqueado(f'{clase} en búsqueda {url}') if clase == 'captcha' else ValueError(f'{clase}: {url}')
        guardar_crudo(FUENTE, f'{nombre}.html', r.content, fecha)
        contenido = r.content
    return parsear_busqueda(contenido, maximo)


# ---------------------------------------------------------------- fixtures para pruebas sin red

QUITAR_FIXTURE = ('script', 'style', 'noscript', 'template', 'link', 'meta', 'iframe', 'svg', 'img', 'video',
                  'input:not(#ASIN)', 'select', 'textarea', '#customerReviews', '#reviewsMedley',
                  '[data-hook="review"]', '.a-profile-name', '#averageCustomerReviews', '[id*="Ingress"]',
                  '#glow-ingress-block', '#nav-global-location-slot')
# Bloques que lee `parsear_ficha` (zona de título, precio, compra y detalles). Nada más pasa a la fixture.
BLOQUES_FIXTURE = ('#titleSection', '#title_feature_div', '#bylineInfo_feature_div', '#bylineInfo',
                   '#corePriceDisplay_desktop_feature_div', '#corePrice_desktop', '#corePrice_feature_div',
                   '#apex_desktop', '#apex_offerDisplay_desktop', '#dealBadge_feature_div', '#dealBadgeSupportingText',
                   '#promoPriceBlockMessage_feature_div', '#applicablePromotionList_feature_div', '[id^="couponBadge"]',
                   '#vpcButton', '#availability', '#outOfStock', '#availabilityInsideBuyBox_feature_div',
                   '#merchantInfoFeature_feature_div', '#fulfillerInfoFeature_feature_div', '#merchant-info',
                   '#tabular-buybox', '#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE',
                   '#deliveryBlockMessage', '#installmentCalculator_feature_div', '#inemi_feature_div',
                   '#best-offer-string-cc', '#renewedProgramDescriptionAtf_feature_div', '#usedBuySection',
                   '#newAccordionRow', '#buyNewSection', '#productOverview_feature_div', '#prodDetails',
                   '#productDetails_feature_div', '#detailBullets_feature_div')
ATRIBUTOS_FIXTURE = {'id', 'class', 'data-a-strike', 'aria-hidden', 'tabular-attribute-name', 'data-asin',
                     'data-component-type'}


def recortar_ficha(html: str | bytes) -> str:
    """Fixture para pruebas sin red: sólo los bloques que lee el parser, sin scripts, imágenes, reseñas,
    formularios, enlaces ni atributos de sesión (session-id, csrf) y sin la ubicación de entrega estimada por IP."""
    if isinstance(html, bytes):
        html = html.decode('utf-8', 'replace')
    arbol = LexborHTMLParser(html)
    asin_input = arbol.css_first('input#ASIN')
    canonica = arbol.css_first('link[rel="canonical"]')
    cabecera = ''
    if canonica is not None:
        cabecera += f'<link rel="canonical" href="{canonica.attributes.get("href")}">'
    if asin_input is not None:
        cabecera += f'<input type="hidden" id="ASIN" name="ASIN" value="{asin_input.attributes.get("value")}">'
    for sel in QUITAR_FIXTURE:
        for n in arbol.css(sel):
            n.decompose()
    for n in arbol.root.traverse():
        if n.is_element_node:
            for k in [k for k in n.attributes if k not in ATRIBUTOS_FIXTURE]:
                del n.attrs[k]
    elegidos = arbol.css(', '.join(BLOQUES_FIXTURE))
    ids = {n.mem_id for n in elegidos}

    def anidado(n):
        p = n.parent
        while p is not None:
            if p.mem_id in ids:
                return True
            p = p.parent
        return False

    piezas = [n.html for n in elegidos if not anidado(n)]
    cuerpo = re.sub(r'\n\s*\n+', '\n', re.sub(r'[ \t]+', ' ', '\n'.join(piezas)))
    return f'<!doctype html><html><head>{cabecera}</head><body>\n{cuerpo}\n</body></html>\n'


# ---------------------------------------------------------------- CLI

def _objetivos_ofertas(ruta: str, maximo: int, prioridad_max: int = 3) -> list[tuple[str, str | None]]:
    """ASINs de Preciómetro (un ASIN por producto, prioridad 1–3 primero) para pruebas."""
    o = pd.read_parquet(ruta)
    o = o.loc[o.asin.notna(), ['asin', 'preciometro_producto_id']].drop_duplicates('asin')
    lista = pd.read_csv(RAIZ / 'config' / 'preciometro_lista.csv', dtype={'preciometro_id': str})
    o = o.merge(lista[['preciometro_id', 'prioridad']], left_on='preciometro_producto_id',
                right_on='preciometro_id', how='left')
    o['prioridad'] = o.prioridad.fillna(9)
    o = o.loc[o.prioridad.le(prioridad_max)] if o.prioridad.le(prioridad_max).any() else o
    o = o.sort_values(['prioridad', 'preciometro_producto_id']).drop_duplicates('preciometro_producto_id')
    return [(a, None) for a in o.asin.head(maximo)]


def _objetivos_productos(ruta: str, maximo: int, prioridad_max: int = 3) -> list[tuple[str, str | None]]:
    """Un ASIN (el primero listado) por producto de la lista fija, prioridad 1–3 primero, para pruebas."""
    p = pd.read_csv(ruta, dtype=str)
    p = p.loc[p.asins.notna()].copy()
    p['_prio'] = pd.to_numeric(p.get('prioridad'), errors='coerce').fillna(9)
    p = p.loc[p._prio.le(prioridad_max)] if p._prio.le(prioridad_max).any() else p
    salida, vistos = [], set()
    for fila in p.sort_values('_prio', kind='stable').to_dict('records'):
        for a, pid in asins_de_productos(pd.DataFrame([fila])):
            if a not in vistos:
                vistos.add(a)
                salida.append((a, pid))
                break
    return salida[:maximo]


def main(argv=None):
    ap = argparse.ArgumentParser(description='Amazon México: ficha pública por ASIN (lista fija).')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('robots', help='Descarga/lee robots.txt del día e informa si /dp/ y /s?k= están permitidas.')
    d = sub.add_parser('diario', help='Colector diario sobre la lista fija de productos.')
    d.add_argument('--productos', default=str(RAIZ / 'config' / 'productos_objetivo.csv'))
    d.add_argument('--fecha', default=None)
    d.add_argument('--max', type=int, default=None, help='Máximo de ASINs (pruebas).')
    d.add_argument('--forzar', action='store_true', help='Ignora un bloqueo ya registrado hoy (no recomendado).')
    d.add_argument('--entorno', default='local')
    p = sub.add_parser('prueba', help='Corrida acotada: ASINs explícitos, uno por producto de la lista fija '
                                      'o de las ofertas de Preciómetro.')
    p.add_argument('--asins', default=None, help='ASINs separados por coma.')
    p.add_argument('--productos', default=None, help='CSV de la lista fija (un ASIN por producto, prioridad 1–3).')
    p.add_argument('--ofertas', default=None, help='Parquet de preciometro_ofertas.')
    p.add_argument('--max', type=int, default=12)
    p.add_argument('--max-bloqueos', type=int, default=2)
    p.add_argument('--forzar', action='store_true')
    p.add_argument('--entorno', default='local')
    b = sub.add_parser('buscar', help='Primera página de /s?k= (sólo mapeo manual de ASIN).')
    b.add_argument('texto')
    r = sub.add_parser('reparsear', help='Reconstruye bronze del día desde data/raw (sin red).')
    r.add_argument('--fecha', default=None)
    f = sub.add_parser('fixture', help='Recorta una ficha cruda para pruebas offline.')
    f.add_argument('asin')
    f.add_argument('--fecha', default=None)
    f.add_argument('--destino', default=str(RAIZ / 'tests' / 'fixtures' / 'amazon'))
    a = ap.parse_args(argv)

    asegurar_directorios()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(LOGS / f'amazon_{hoy()}.log', encoding='utf-8')])
    if a.cmd == 'robots':
        print(resumen_robots(leer_robots(cliente_amazon())))
    elif a.cmd == 'diario':
        productos = pd.read_csv(a.productos, dtype=str)
        print(diario(productos, fecha=a.fecha, entorno=a.entorno, max_asins=a.max, forzar=a.forzar))
    elif a.cmd == 'prueba':
        if a.asins:
            objetivos = [(x.strip().upper(), None) for x in a.asins.split(',') if RE_ASIN.match(x.strip().upper())]
        elif a.productos:
            objetivos = _objetivos_productos(a.productos, a.max)
        else:
            objetivos = _objetivos_ofertas(a.ofertas or str(BRONZE / "preciometro_ofertas" / f"{hoy()}.parquet"), a.max)
        print(correr(objetivos[:a.max], entorno=a.entorno, max_bloqueos=a.max_bloqueos, forzar=a.forzar))
    elif a.cmd == 'buscar':
        for fila in buscar(a.texto):
            print(fila)
    elif a.cmd == 'reparsear':
        print(reparsear(a.fecha or hoy()))
    elif a.cmd == 'fixture':
        from pathlib import Path
        fecha = a.fecha or hoy()
        d = descargar_ficha(None, a.asin, fecha, solo_cache=True)
        if d['contenido'] is None:
            sys.exit(f'No hay crudo de {a.asin} el {fecha}')
        destino = Path(a.destino)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / f'{a.asin}.html').write_text(recortar_ficha(d['contenido']), encoding='utf-8')
        print(destino / f'{a.asin}.html')


if __name__ == '__main__':
    main()
