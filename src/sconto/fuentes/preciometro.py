"""Preciómetro (preciometro.com): historial público de 90 días y ofertas vigentes por tienda.

La ficha pública declara datos diferidos (`resultados`, `datosGrafica`) que su propio navegador pide con
cabeceras Inertia. Pedimos lo mismo, sin sesión, una petición por producto. robots.txt no prohíbe /productos/.

Semántica, importante para el análisis:
- `datosGrafica` = UN punto por día: el precio mínimo entre tiendas ese día, con la tienda y el vendedor
  que lo ofrecían. No es la serie de una sola tienda. Ventana móvil de ~90 días.
- `resultados` = ofertas vigentes al momento de la captura (una por tienda/vendedor/listado), con enlaces
  que contienen ASIN de Amazon o ID de catálogo de Mercado Libre.
"""
from __future__ import annotations

import json
import re
from datetime import date

from bs4 import BeautifulSoup

from sconto.cliente import Cliente
from sconto.esquema import a_dataframe, condiciones_json

FUENTE = 'preciometro'
FUENTE_OFERTAS = 'preciometro_ofertas'
BASE = 'https://preciometro.com'
COMPONENTE = 'productos/ProductoDetalle'
PROPS = 'producto,resultados,datosGrafica'

RE_ASIN = re.compile(r'amazon\.com\.mx/(?:[^/]+/)?(?:dp|gp/product)/([A-Z0-9]{10})', re.I)
RE_MLM = re.compile(r'mercadolibre\.com\.mx/(?:[^?#]*/)?p/(MLM\d+)', re.I)
RE_MLM_ITEM = re.compile(r'(MLM-?\d{6,})', re.I)


def id_desde_url(url: str) -> str:
    return str(int(url.rstrip('/').rsplit('-', 1)[-1]))


class Preciometro:
    def __init__(self, cliente: Cliente | None = None):
        self.cliente = cliente or Cliente(pausa=(3.0, 8.0))
        self.version = None

    def _cargar_version(self, url):
        r = self.cliente.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        for s in soup.find_all('script'):
            t = s.get_text().strip()
            if t.startswith('{"component"'):
                self.version = json.loads(t)['version']
                return
        el = soup.find(attrs={'data-page': True})
        if el is None:
            raise ValueError('La estructura pública cambió: no se encontró la página Inertia.')
        self.version = json.loads(el['data-page'])['version']

    def obtener(self, url: str) -> bytes:
        """Respuesta JSON cruda (bytes) con producto, ofertas y gráfico."""
        if self.version is None:
            self._cargar_version(url)
        for _ in range(2):
            r = self.cliente.get(url, headers={
                'X-Inertia': 'true', 'X-Inertia-Version': self.version,
                'X-Inertia-Partial-Component': COMPONENTE, 'X-Inertia-Partial-Data': PROPS,
                'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/html, application/xhtml+xml'})
            if r.status_code == 409:  # el sitio publicó una versión nueva de su frontend
                self._cargar_version(url)
                continue
            if r.status_code == 404:
                raise FileNotFoundError(url)
            r.raise_for_status()
            if 'json' not in r.headers.get('content-type', ''):
                raise ValueError(f'Respuesta no JSON en {url}')
            return r.content
        raise RuntimeError(f'Versión Inertia inestable en {url}')


def parsear(contenido: bytes, url: str, ruta_raw: str, hash_raw: str, fecha_captura: str | None = None):
    """Devuelve (historial_df, ofertas_df, meta_dict)."""
    fecha_captura = fecha_captura or date.today().isoformat()
    d = json.loads(contenido)
    props = d['props']
    p = props.get('producto') or {}
    pid = str(p.get('id') or id_desde_url(url))
    cat = p.get('categoria') or {}
    facetas = p.get('facetas') or {}
    marca = facetas.get('marca') or p.get('marca')
    comunes = dict(metodo='agregador', canal='en_linea', fecha_captura=fecha_captura, moneda='MXN',
                   marca=marca, descripcion_original=p.get('nombre'), url=url, ruta_raw=ruta_raw, hash_raw=hash_raw)

    g = props.get('datosGrafica') or {}
    fechas, precios = g.get('fechas') or [], g.get('precios') or []
    tiendas, vendedores = g.get('tiendas') or [None] * len(fechas), g.get('vendedores') or [None] * len(fechas)
    if not (len(fechas) == len(precios) == len(tiendas) == len(vendedores)):
        raise ValueError(f'Gráfico con longitudes distintas en {url}')
    hist = [dict(comunes, fuente=FUENTE, tipo_precio='minimo_diario_multitienda', fecha_precio=f,
                 id_externo=pid, tipo_id_externo='preciometro', plataforma=t, vendedor_o_cadena=v,
                 precio=float(x) if x is not None else None)
            for f, x, t, v in zip(fechas, precios, tiendas, vendedores)]

    ofertas, asins, mlms = [], set(), set()
    for o in props.get('resultados') or []:
        enlace = o.get('enlace_referencia') or o.get('enlace') or ''
        asin = RE_ASIN.search(enlace)
        mlm = RE_MLM.search(enlace)
        mlm_item = None if mlm else RE_MLM_ITEM.search(enlace)
        if asin:
            asins.add(asin.group(1).upper())
        if mlm:
            mlms.add(mlm.group(1).upper())
        tienda = (o.get('tienda') or {}).get('nombre')
        ofertas.append(dict(
            comunes, fuente=FUENTE_OFERTAS, tipo_precio='oferta_vigente', fecha_precio=fecha_captura,
            id_externo=str(o.get('id')), tipo_id_externo='preciometro_oferta', plataforma=tienda,
            vendedor_o_cadena=o.get('vendedor'), precio=o.get('precio_final'),
            descripcion_original=o.get('nombre'), url=enlace,
            condiciones=condiciones_json(envio=o.get('envio'), prime=o.get('prime'), marketplace=o.get('marketplace'),
                                         pickup=o.get('pickup'), precio_sin_ajuste=o.get('precio')),
            preciometro_producto_id=pid,
            asin=asin.group(1).upper() if asin else None,
            mlm_producto=mlm.group(1).upper() if mlm else None,
            mlm_item=mlm_item.group(1).upper().replace('-', '') if mlm_item else None))

    meta = dict(preciometro_id=pid, url=url, nombre=p.get('nombre'), categoria=cat.get('nombre'),
                categoria_path=cat.get('slug_path'), es_tecnologia=str(cat.get('slug_path') or '').startswith('tecnologia'),
                marca=marca, linea=facetas.get('linea'), color=facetas.get('color'),
                capacidad=facetas.get('capacidad'), caracteristicas=p.get('caracteristicas'),
                palabras_claves=p.get('palabras_claves'), modelo=p.get('modelo'), variante=p.get('variante'),
                fecha_creacion=p.get('fecha_creacion'), tiendas_activas=p.get('tiendas_activas'),
                puntos_grafica=len(fechas), primera_fecha=min(fechas) if fechas else None,
                ultima_fecha=max(fechas) if fechas else None, asins=';'.join(sorted(asins)),
                mlm_ids=';'.join(sorted(mlms)), fecha_captura=fecha_captura, ruta_raw=ruta_raw)
    return a_dataframe(hist), a_dataframe(ofertas), meta
