"""Pruebas offline de Amazon México (sin red). Fixtures en tests/fixtures/amazon/:
- B0CLF3VPMV.html: ficha real del 2026-10-16 recortada con `recortar_ficha` (sin sesión, reseñas ni ubicación);
- captcha.html: página real de verificación de Amazon (tokens reemplazados por X);
- robots.txt: robots.txt real del 2026-10-16;
- sintetica_descuento.html: estructura real con números inventados (precio de lista, % de ahorro, cupón, MSI).
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from sconto import almacen
from sconto.cliente import Bloqueado
from sconto.esquema import COLUMNAS, a_dataframe
from sconto.fuentes import amazon as az

FIX = Path(__file__).parent / 'fixtures' / 'amazon'


def _leer(nombre):
    return (FIX / nombre).read_text(encoding='utf-8')


def test_robots_permite_ficha_y_busqueda_para_agente_generico():
    robots = _leer('robots.txt')
    assert az.permitido(robots, 'https://www.amazon.com.mx/dp/B0CLF3VPMV')
    assert az.permitido(robots, 'https://www.amazon.com.mx/s?k=bocina+sony')
    assert not az.permitido(robots, 'https://www.amazon.com.mx/gp/offer-listing/B0CLF3VPMV')
    assert not az.permitido(robots, 'https://www.amazon.com.mx/dp/product-availability/B0CLF3VPMV')
    assert not az.permitido(robots, 'https://www.amazon.com.mx/dp/B0CLF3VPMV', 'ClaudeBot/1.0')
    r = az.resumen_robots(robots)
    assert r['dp'] and r['busqueda'] and r['grupo_aplicable'] == '*'
    assert 'claude-user' in r['agentes_bloqueados_totalmente']


def test_robots_conservador_con_comodines():
    assert not az.permitido('User-agent: *\nDisallow: /x/*/y\n',
                            'https://www.amazon.com.mx/x/a/y/z')  # comodín RFC 9309 (urllib no lo ve)
    propio = 'User-agent: *\nDisallow: /dp/\nUser-agent: ScontoRealeOFalso\nDisallow: /s\n'
    assert az.permitido(propio, 'https://www.amazon.com.mx/dp/B0CLF3VPMV')  # el grupo que nos nombra manda
    assert not az.permitido(propio, 'https://www.amazon.com.mx/s?k=tv')
    # Allow más largo que gana en RFC 9309 pero urllib lo niega (primera regla): se exige que ambos permitan.
    assert not az.permitido('User-agent: *\nDisallow: /dp/\nAllow: /dp/B0*$\n', 'https://www.amazon.com.mx/dp/B0')


def test_parsear_ficha_real():
    f = az.parsear_ficha(_leer('B0CLF3VPMV.html'), 'B0CLF3VPMV')
    assert f['asin_pagina'] == 'B0CLF3VPMV'
    assert f['titulo'].startswith('Samsung Galaxy Tab A9 Plus')
    assert f['precio'] == 5650.0
    assert f['precio_anterior'] is None and f['pct_ahorro'] is None  # la ficha no muestra tachado ese día
    assert f['vendido_por'].startswith('Tekno Electronicos') and f['enviado_por'] == 'Amazon'
    assert f['condicion'] == 'nuevo' and f['msi_meses'] is None
    assert f['plazos_texto'] == '$573.47 x12 meses'  # plazos sin "sin intereses": sólo se describen
    assert f['marca'] == 'Samsung' and f['modelo'] == 'Galaxy Tab A9+'


def test_parsear_ficha_sintetica_con_descuento():
    f = az.parsear_ficha(_leer('sintetica_descuento.html'))
    assert f['precio'] == 649.0
    assert f['precio_anterior'] == 999.0  # ni el tachado oculto (5,000) ni el del carrusel (1,999)
    assert f['etiqueta_precio_anterior'] == 'Precio de lista'
    assert f['pct_ahorro'] == 35.0 and f['ahorro_texto'] == '-35%'
    assert f['oferta_relampago'] and f['cupon'].startswith('Aplica cupón')
    assert f['msi_meses'] == 12
    assert f['vendido_por'] == f['enviado_por'] == 'Amazon México'
    assert f['condicion'] == 'reacondicionado'
    assert f['marca'] == 'Sony' and f['modelo'] == 'SRS-XB100'


def test_ahorro_desde_etiqueta_accesible():
    html = ('<div id="corePriceDisplay_desktop_feature_div"><span id="apex-pricetopay-accessibility-label">'
            '$1,299.00 con un ahorro del 28%</span><span class="a-price priceToPay"><span class="a-offscreen">'
            '$1,299.00</span></span></div><span id="productTitle">x</span>')
    f = az.parsear_ficha(html)
    assert f['precio'] == 1299.0 and f['pct_ahorro'] == 28.0 and f['precio_anterior'] is None


def test_clasificar():
    assert az.clasificar(200, _leer('captcha.html')) == 'captcha'
    assert az.clasificar(200, _leer('B0CLF3VPMV.html')) == 'ficha'
    assert az.clasificar(404, '<html>no existe</html>') == 'no_encontrado'
    assert az.clasificar(200, '<html>otra cosa</html>') == 'desconocida'


def test_a_numero():
    assert az.a_numero('$1,299.00') == 1299.0
    assert az.a_numero('null') is None and az.a_numero('$0.00') is None and az.a_numero(None) is None


def test_fila_cumple_esquema():
    f = az.parsear_ficha(_leer('sintetica_descuento.html'))
    fila = az.fila_observacion(f, 'B000TEST01', 'P-1', '2026-10-16', 'data/raw/amazon/x.gz', 'abc')
    df = a_dataframe([fila])
    assert list(df.columns[:len(COLUMNAS)]) == COLUMNAS
    assert az.validar(df) == []
    r = df.iloc[0]
    assert (r.metodo, r.canal, r.tipo_id_externo, r.moneda) == ('scraping', 'en_linea', 'asin', 'MXN')
    assert r.precio_anterior_anunciado == 999.0 and r.pct_descuento_anunciado == 35.0
    c = json.loads(r.condiciones)
    assert c['vendido_por'] == 'Amazon México' and c['msi_meses'] == 12 and c['oferta_relampago'] is True


def test_asins_de_productos():
    p = pd.DataFrame({'producto_canonico_id': ['A', 'B', 'C'],
                      'asins': ['B0CLF3VPMV;b0c1nrf7y6', 'B0CLF3VPMV', None], 'mlm_ids': [None, None, 'MLM1']})
    assert az.asins_de_productos(p) == [('B0CLF3VPMV', 'A'), ('B0C1NRF7Y6', 'A')]
    assert az.asins_de_productos(pd.DataFrame({'producto_canonico_id': ['A']})) == []


def test_recortar_ficha_quita_sesion_y_ubicacion():
    html = ('<html><head><link rel="canonical" href="https://www.amazon.com.mx/x/dp/B000TEST01"></head><body>'
            '<input id="ASIN" value="B000TEST01"><input id="attach-sessionId" value="147-0000000-0000000">'
            '<div id="contextualIngressPt">Se entregará a Ciudad X 00000</div>'
            '<div id="titleSection" data-session-id="147-0000000-0000000"><span id="productTitle">T</span></div>'
            '<div id="customerReviews"><span class="a-profile-name">Persona</span></div></body></html>')
    t = az.recortar_ficha(html)
    for prohibido in ('147-0000000', 'Ciudad X', 'Persona', 'session'):
        assert prohibido not in t
    assert 'productTitle' in t and 'B000TEST01' in t


# ---------------------------------------------------------------- corrida sin red con cliente falso

class ClienteFalso:
    """Responde robots.txt y fichas desde fixtures; cuenta las peticiones a /dp/."""
    def __init__(self, respuestas):
        self.respuestas, self.pedidas = respuestas, []
        self.respetar_robots, self._robots = True, {}

    def get(self, url, **kw):
        if url.endswith('/robots.txt'):
            return SimpleNamespace(status_code=200, text=_leer('robots.txt'), content=b'', url=url)
        self.pedidas.append(url)
        r = self.respuestas[url.rsplit('/', 1)[-1]]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(status_code=200, content=r.encode('utf-8'), url=url)


@pytest.fixture
def aislado(monkeypatch, tmp_path):
    for mod in (almacen, az):
        monkeypatch.setattr(mod, 'RAIZ', tmp_path)
        monkeypatch.setattr(mod, 'RAW', tmp_path / 'data' / 'raw')
        monkeypatch.setattr(mod, 'BRONZE', tmp_path / 'data' / 'bronze')
    monkeypatch.setattr(az, 'ESTADO_FUENTES', tmp_path / 'data' / 'estado_fuentes.csv')
    estados = []
    monkeypatch.setattr(az, 'registrar_estado', lambda *a, **k: estados.append((a, k)))
    return SimpleNamespace(ruta=tmp_path, estados=estados)


def _productos():
    return pd.DataFrame({'producto_canonico_id': ['P1', 'P2', 'P3'],
                         'asins': ['B0CLF3VPMV', 'B0C1NRF7Y6', 'B0DTC17BX1'], 'mlm_ids': [None] * 3})


def test_diario_se_detiene_al_primer_captcha(aislado):
    c = ClienteFalso({'B0CLF3VPMV': _leer('B0CLF3VPMV.html'), 'B0C1NRF7Y6': _leer('captcha.html'),
                      'B0DTC17BX1': _leer('B0CLF3VPMV.html')})
    r = az.diario(_productos(), cliente=c)
    assert r['estado'] == 'bloqueado' and r['bloqueos'] == 1 and r['filas'] == 1
    assert len(c.pedidas) == 2  # el tercer ASIN no se pide: se reintenta otro día
    assert aislado.estados[-1][0][1] == 'bloqueado'
    hoy = almacen.hoy()
    b = pd.read_parquet(aislado.ruta / 'data' / 'bronze' / 'amazon' / f'{hoy}.parquet')
    assert b.id_externo.tolist() == ['B0CLF3VPMV'] and b.producto_canonico_id.tolist() == ['P1']
    assert (aislado.ruta / 'data' / 'raw' / 'amazon' / hoy / 'B0C1NRF7Y6.bloqueo.html.gz').exists()
    caps = pd.read_parquet(aislado.ruta / 'data' / 'bronze' / 'amazon_capturas' / f'{hoy}.parquet')
    assert caps.clase.tolist() == ['ficha', 'captcha']


def test_503_es_bloqueo_sin_reintento(aislado):
    c = ClienteFalso({'B0CLF3VPMV': Bloqueado('503 persistente https://www.amazon.com.mx/dp/B0CLF3VPMV')})
    r = az.diario(_productos(), cliente=c)
    assert r['estado'] == 'bloqueado' and len(c.pedidas) == 1 and r['filas'] == 0


def test_rejecutar_el_mismo_dia_reutiliza_crudos(aislado):
    fichas = {a: _leer('B0CLF3VPMV.html') for a in ('B0CLF3VPMV', 'B0C1NRF7Y6', 'B0DTC17BX1')}
    c1 = ClienteFalso(fichas)
    assert az.diario(_productos(), cliente=c1)['estado'] == 'ok' and len(c1.pedidas) == 3
    c2 = ClienteFalso({})  # sin respuestas: cualquier petición a /dp/ fallaría
    r = az.diario(_productos(), cliente=c2)
    assert c2.pedidas == [] and r['reutilizados'] == 3 and r['filas'] == 3
    b = pd.read_parquet(aislado.ruta / 'data' / 'bronze' / 'amazon' / f'{almacen.hoy()}.parquet')
    assert len(b) == 3 and not b.duplicated(['fuente', 'id_externo', 'fecha_precio', 'vendedor_o_cadena']).any()
