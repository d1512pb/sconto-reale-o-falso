"""Servicios del modelo final en la API: tarjeta, predicción, evaluación de precio, historial propio y app estática."""
import json

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from sconto.api_v2 import crear_api

ARBOL = {'version': 't', 'tipo': 'arbol_decision', 'variables': ['cambio_previo_pct'], 'tasa_general': .6,
         'nombres': {'cambio_previo_pct': 'Cambio previo (%)'},
         'nodos': [{'izq': 1, 'der': 2, 'variable': 'cambio_previo_pct', 'umbral': -0.5, 'prob_bajada': .6, 'casos': 10, 'bajaron': 6},
                   {'izq': -1, 'der': -1, 'variable': None, 'umbral': None, 'prob_bajada': .9, 'casos': 4, 'bajaron': 4},
                   {'izq': -1, 'der': -1, 'variable': None, 'umbral': None, 'prob_bajada': .3, 'casos': 6, 'bajaron': 2}]}
TARJETA = {'version': 'sconto-modelo-app-v1', 'modelo': {'familia': 'Árbol de decisión', 'variante': 'prueba'},
           'reglas': {'umbral_pct': 5, 'min_fechas_base': 4, 'min_amplitud_dias': 21},
           'predicciones': {'P1': {'prob_bajada': .9, 'prediccion': 1, 'bajo': 1, 'bajada_pct': 6.0, 'acierto': True}}}


@pytest.fixture
def cliente(tmp_path):
    modelo, sitio = tmp_path / 'modelo', tmp_path / 'sitio'
    modelo.mkdir(); sitio.mkdir()
    (modelo / 'modelo.json').write_text(json.dumps(TARJETA), encoding='utf-8')
    (modelo / 'arbol.json').write_text(json.dumps(ARBOL), encoding='utf-8')
    evento = {'evento_id': 'BF2026', 'base_inicio': '2026-09-14', 'base_fin': '2026-10-29'}
    puntos = [{'serie_id': 's', 'fecha_precio': f'2026-09-{d:02d}', 'precio_mediano': p}
              for d, p in ((14, 1000), (20, 1000), (26, 1100), (30, 900))]
    ficha = {'series': [{'serie_id': 's', 'contexto': 'minimo_multitienda'}],
             'referencias': [{'serie_id': 's', 'evento_id': 'BF2026', 'cobertura_base': True, 'n_fechas_base': 4,
                              'amplitud_base_dias': 30, 'mediana_base': 1000, 'p25_base': 975, 'p75_base': 1025,
                              'base_inicio': '2026-09-14', 'base_fin': '2026-10-29'}],
             'precios_diarios': puntos}
    (sitio / 'producto.json').write_text(json.dumps(ficha), encoding='utf-8')
    feed = {'fecha_corte': '2026-11-26', 'evento_actual': 'BF2026', 'ventanas': [evento],
            'detalles': {'P1': {'archivo': 'producto.json'}}, 'productos': [{'producto_canonico_id': 'P1', 'nombre': 'Laptop'}]}
    (sitio / 'datos.json').write_text(json.dumps(feed), encoding='utf-8')
    (sitio / 'snapshot.json').write_text(json.dumps({'archivo': 'datos.json'}), encoding='utf-8')
    (sitio / 'index.html').write_text('<!doctype html><title>Sconto</title>', encoding='utf-8')
    with TestClient(crear_api(root=tmp_path / 'intradia', sitio=sitio, modelo=modelo, docs=True)) as c:
        yield c


def test_tarjeta_y_prediccion(cliente):
    assert cliente.get('/v1/modelo').json()['productos_con_prediccion'] == 1
    assert cliente.get('/v1/products/P1/prediccion').json()['acierto'] is True
    assert cliente.get('/v1/products/P9/prediccion').status_code == 404
    assert cliente.get('/v1/modelo/predicciones').json()['predicciones'][0]['nombre'] == 'Laptop'


def test_evaluar_precio(cliente):
    assert cliente.get('/v1/products/P1/evaluar-precio', params={'precio': 900}).json()['estado'] == 'precio_favorable'
    assert cliente.get('/v1/products/P1/evaluar-precio', params={'precio': 1100}).json()['estado'] == 'precio_alto'
    assert cliente.get('/v1/products/P1/evaluar-precio', params={'precio': 990}).json()['estado'] == 'sin_senal_clara'
    assert cliente.get('/v1/products/P1/evaluar-precio', params={'precio': 0}).status_code == 422


def test_predecir_con_historial_propio(cliente):
    precios = [{'fecha': f, 'precio': p} for f, p in (('2026-09-15', 1000), ('2026-09-25', 1000), ('2026-10-05', 1000),
                                                      ('2026-10-20', 1000), ('2026-10-31', 1000), ('2026-11-10', 900))]
    r = cliente.post('/v1/predecir', json={'precios': precios, 'precio_actual': 900}).json()
    assert r['completo'] and r['prediccion']['bajara'] and r['prediccion']['casos_parecidos'] == 4
    assert r['evaluacion_precio']['estado'] == 'precio_favorable'
    incompleto = cliente.post('/v1/predecir', json={'precios': precios[:2]}).json()
    assert not incompleto['completo'] and incompleto['prediccion'] is None and incompleto['faltan']


def test_app_estatica_y_documentacion(cliente):
    assert 'Sconto' in cliente.get('/').text
    assert cliente.get('/docs').status_code == 200
    assert cliente.get('/v1/modelo').headers['Cache-Control'] == 'no-store'
