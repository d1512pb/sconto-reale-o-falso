import pandas as pd
import pytest

from sconto.compra import atributos, Buscador, consultar, evaluar_precio, identidad_oferta


@pytest.mark.parametrize('titulo', ['Apple AirPods 3 Pro inalámbricos Blanco', 'Apple AirPods Pro 3ra Generación'])
def test_orden_generation_airpods(titulo):
    assert atributos(titulo)['airpods'] == 'PRO3'
    assert identidad_oferta('Apple AirPods Pro 3', titulo)[0] == 'compatible_texto'


@pytest.mark.parametrize('titulo', ['Apple AirPods Pro 2', 'Apple AirPods 3'])
def test_no_unir_generaciones(titulo):
    assert identidad_oferta('Apple AirPods Pro 3', titulo)[0] == 'conflicto'


def test_ram_y_paquete():
    assert identidad_oferta('Lenovo 8GB RAM', 'Lenovo 24GB RAM')[0] == 'conflicto'
    assert identidad_oferta('Sony MDR ZX110', 'Sony MDR ZX110 con hervidor')[0] == 'conflicto'
    assert identidad_oferta('Lenovo IdeaPad Slim 3 i3 8GB RAM 512GB SSD', 'HP Pavilion i3 8GB RAM 512GB SSD')[0] == 'pendiente'


def datos():
    oferta = dict(precio=900, fecha_precio='2026-11-07', moneda='MXN', identidad_oferta='compatible_texto',
                  serie_id='vendedor1', pct_descuento_anunciado=40)
    referencia = dict(mediana_base=1000, p25_base=950, p75_base=1050, moneda='MXN', canal='en_linea',
                      cobertura_base=True, base_cerrada=True, contexto='minimo_multitienda', serie_id='mercado')
    return oferta, referencia


def test_mercado_no_es_brecha_vendedor():
    o, r = datos()
    evaluacion = evaluar_precio(o, r, '2026-11-07')
    assert evaluacion['indicador'] == 'precio_favorable'
    assert evaluacion['ahorro_referencia_pct'] == pytest.approx(10)
    assert evaluacion['brecha_pp'] is None
    assert evaluar_precio(o, r, '2026-11-07', umbral=10)['indicador'] == 'precio_favorable'
    r.update(contexto='serie_vendedor', serie_id='otro')
    assert evaluar_precio(o, r, '2026-11-07')['indicador'] == 'evidencia_insuficiente'
    r['serie_id'] = 'vendedor1'
    assert evaluar_precio(o, r, '2026-11-07')['brecha_pp'] == pytest.approx(30)


@pytest.mark.parametrize('fecha', ['2026-11-06', '2026-11-10'])
def test_captura_futura_o_antigua(fecha):
    o, r = datos()
    assert evaluar_precio(o, r, fecha)['indicador'] == 'evidencia_insuficiente'


@pytest.mark.parametrize('cambio', [dict(cobertura_base=False), dict(base_cerrada=False), dict(moneda='USD'), dict(canal='tienda_fisica')])
def test_sin_comparabilidad(cambio):
    o, r = datos()
    r.update(cambio)
    assert evaluar_precio(o, r, '2026-11-07')['indicador'] == 'evidencia_insuficiente'


def test_busqueda_no_mezcla_variantes():
    catalogo = pd.DataFrame({'producto_canonico_id': ['a', 'b', 'c'],
                            'nombre': ['Apple AirPods Pro 3', 'Apple AirPods Pro 2', 'Apple AirPods 3']})
    b = Buscador(catalogo)
    assert b.buscar('airpods pro 3').producto_canonico_id.tolist() == ['a']
    assert b.buscar('zzzzqqq').empty
    assert len(b.buscar('airpods')) == 3


def test_texto_desconocido_y_disco_sin_sigla():
    catalogo = pd.DataFrame({'producto_canonico_id': ['a', 'b'],
                            'nombre': ['Proyector inteligente', 'Lenovo Slim 8GB RAM 128GB Chromebook']})
    b = Buscador(catalogo)
    assert b.buscar('zzzzqqq producto inexistente').empty
    assert b.buscar('Lenovo Slim 8GB RAM 512GB SSD').empty


def test_consulta_no_reutiliza_indicador_obsoleto():
    df = pd.DataFrame([dict(producto_canonico_id='a', fecha_precio='2026-11-07', precio=900,
                           plataforma='Sears', indicador='precio_favorable', motivos='[]')])
    assert consultar('a', {'ofertas_evaluadas': df}, '2026-11-10').iloc[0].indicador == 'evidencia_insuficiente'
