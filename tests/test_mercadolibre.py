"""Pruebas offline de Mercado Libre (sin red)."""
from types import SimpleNamespace
import json

import pandas as pd
import requests

from sconto.esquema import a_dataframe
from sconto.fuentes import mercadolibre as ml


def _resp(url, history_locations=()):
    hist = [SimpleNamespace(headers={'location': loc}) for loc in history_locations]
    return SimpleNamespace(url=url, history=hist, headers={})


def test_muro_de_verificacion_detectado():
    r = _resp('https://www.mercadolibre.com.mx/gz/account-verification?go=https%3A%2F%2Fwww.mercadolibre.com.mx%2Fp%2FMLM1')
    assert ml.es_muro(r)
    r2 = _resp('https://www.mercadolibre.com.mx/p/MLM1', ['https://www.mercadolibre.com.mx/gz/account-verification?go=x'])
    assert ml.es_muro(r2)
    assert not ml.es_muro(_resp('https://www.mercadolibre.com.mx/p/MLM18593745'))


def test_fila_item_usa_precio_tachado_mostrado():
    item = {'id': 'MLM2081699241', 'title': 'Samsung Galaxy A06 64 GB', 'price': 2280, 'original_price': 2999,
            'currency_id': 'MXN', 'seller_id': 123, 'status': 'active', 'available_quantity': 5,
            'condition': 'new', 'shipping': {'free_shipping': True}, 'permalink': 'https://articulo.mercadolibre.com.mx/MLM-2081699241'}
    precio = {'amount': 2199, 'regular_amount': 2999}
    f = ml.filas_item(item, precio, 'data/raw/x.gz', 'abc', '2026-10-16', 'MLM41998828')
    assert f['precio'] == 2199 and f['precio_anterior_anunciado'] == 2999
    df = a_dataframe([f])  # el % no se calcula: sólo se registra si la fuente lo muestra
    assert df.pct_descuento_anunciado.isna().all()
    assert df.tipo_id_externo.iloc[0] == 'mlm_item' and df.metodo.iloc[0] == 'api'


def test_fila_item_sin_tachado_queda_vacio():
    item = {'id': 'MLM1', 'title': 'x', 'price': 100, 'status': 'active'}
    f = ml.filas_item(item, None, 'r', 'h', '2026-10-16', None)
    assert f['precio_anterior_anunciado'] is None and f['precio'] == 100.0


def test_sin_credenciales_no_hace_peticiones(monkeypatch, tmp_path):
    for k in ('ML_CLIENT_ID', 'ML_CLIENT_SECRET', 'ML_REFRESH_TOKEN'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(ml.TokenML, 'RUTA', tmp_path / 'token.json')
    registros = []
    monkeypatch.setattr(ml, 'registrar_estado', lambda *a, **k: registros.append((a, k)))
    res = ml.diario(pd.DataFrame({'mlm_ids': ['']}), fecha='2026-10-16')
    assert res['estado'] == 'sin_credenciales' and res['filas'] == 0
    assert registros and registros[0][0][1] == 'sin_credenciales'


def test_objetivos_solo_exactos_sin_ids_compartidos():
    productos = pd.DataFrame([
        dict(producto_canonico_id='A', mlm_ids='MLM1', confianza_match='exacto'),
        dict(producto_canonico_id='B', mlm_ids='MLM1', confianza_match='exacto'),
        dict(producto_canonico_id='C', mlm_ids='MLM2', confianza_match='probable'),
        dict(producto_canonico_id='D', mlm_ids='MLM3', confianza_match='exacto')])
    assert [objetivo['id'] for objetivo in ml.objetivos(productos)] == ['MLM3']


def test_api_guarda_crudo_valido_y_reutiliza_sin_red(monkeypatch, tmp_path):
    monkeypatch.setenv('ML_ACCESS_TOKEN', 'token_sintetico_sin_validez')
    monkeypatch.setattr(ml, 'RAW', tmp_path / 'data' / 'raw')
    monkeypatch.setattr(ml, 'RAIZ', tmp_path)
    monkeypatch.setattr(ml, 'hoy', lambda: '2026-10-20')
    from sconto import almacen
    monkeypatch.setattr(almacen, 'RAIZ', tmp_path)
    monkeypatch.setattr(almacen, 'RAW', tmp_path / 'data' / 'raw')
    monkeypatch.setattr(ml, 'registrar_estado', lambda *args, **kwargs: None)
    escritas = []
    monkeypatch.setattr(ml, 'escribir_bronze', lambda fuente, tabla, *args, **kwargs: escritas.append(tabla))
    llamadas = []

    class ApiSimulada:
        def __init__(self, **kwargs):
            self.sesion = SimpleNamespace(headers={})

        def get(self, url):
            llamadas.append(url)
            resultado = requests.Response()
            resultado.status_code = 200
            resultado.url = url
            datos = {'amount': 80, 'regular_amount': 100} if '/sale_price' in url else {
                'id': 'MLM123', 'title': 'Fixture sintética', 'price': 80, 'status': 'active', 'seller_id': 15}
            resultado._content = json.dumps(datos).encode()
            return resultado

    monkeypatch.setattr(ml, 'Cliente', ApiSimulada)
    productos = pd.DataFrame([dict(producto_canonico_id='A', mlm_item_ids='MLM123', confianza_match='exacto')])
    assert ml.diario(productos)['filas'] == 1
    assert len(llamadas) == 2
    assert ml.diario(productos)['filas'] == 1
    assert len(llamadas) == 2
    assert escritas[-1].precio.iloc[0] == 80
    cache = tmp_path / 'data/raw/mercadolibre/2026-10-20/objetivo_MLM123.json.gz'
    import gzip
    assert json.loads(gzip.decompress(cache.read_bytes()))['items'][0]['sale_price']['regular_amount'] == 100
