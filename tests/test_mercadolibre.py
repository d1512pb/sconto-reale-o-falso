"""Pruebas offline de Mercado Libre (sin red)."""
from types import SimpleNamespace

import pandas as pd

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
