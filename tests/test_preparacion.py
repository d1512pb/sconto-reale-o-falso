import pandas as pd

from sconto.dataset import _explotar, asignar_series, consolidar, series_evento
from sconto.esquema import a_dataframe
from sconto.eventos import cargar_eventos


def test_mapeos_ambiguos_no_se_resuelven_por_prioridad():
    productos = pd.DataFrame([
        {'producto_canonico_id': 'A', 'prioridad': 1, 'asins': 'B000000001', 'confianza_match': 'exacto'},
        {'producto_canonico_id': 'B', 'prioridad': 2, 'asins': 'B000000001', 'confianza_match': 'exacto'},
        {'producto_canonico_id': 'C', 'prioridad': 1, 'asins': 'B000000002', 'confianza_match': 'probable'},
    ])
    assert _explotar(productos, 'asins') == {}


def test_mediana_del_evento_da_mismo_peso_a_cada_fecha():
    filas = []
    for fecha, precio in [('2025-09-14', 100), ('2025-09-21', 100), ('2025-10-05', 100),
                           ('2025-10-20', 100), ('2025-11-13', 80), ('2025-11-13', 80),
                           ('2025-11-14', 60)]:
        filas.append(dict(fuente='amazon', metodo='scraping', canal='en_linea', tipo_precio='precio_vigente',
                          fecha_precio=fecha, id_externo='B000000001', tipo_id_externo='asin',
                          vendedor_o_cadena='Tienda', moneda='MXN', precio=precio, serie_id=None))
    observaciones = asignar_series(a_dataframe(filas))
    observaciones['fecha_precio'] = pd.to_datetime(observaciones.fecha_precio)
    resultado = series_evento(observaciones, cargar_eventos())
    serie = resultado.loc[resultado.evento_id.eq('BF2025')].iloc[0]
    assert serie.n_evento == 2
    assert serie.mediana_evento == 70
    assert abs(serie.ahorro_historico_pct - 30) < 1e-9


def test_sin_vendedor_no_une_fuentes_distintas():
    observaciones = a_dataframe([
        dict(fuente=fuente, precio=100, id_externo='B000000001', tipo_id_externo='asin',
             url='https://www.amazon.com.mx/dp/B000000001', moneda='MXN', canal='en_linea', serie_id=None)
        for fuente in ['amazon', 'wayback']])
    resultado = asignar_series(observaciones)
    assert resultado.serie_id.nunique() == 2


def test_minimo_multitienda_revisado_conserva_solo_ultima_captura():
    observaciones = a_dataframe([
        dict(fuente='preciometro', id_externo='1', fecha_precio='2026-10-16', fecha_captura=fecha,
             vendedor_o_cadena=vendedor, tipo_precio='minimo_diario_multitienda', precio=precio, ruta_raw=fecha)
        for fecha, vendedor, precio in [('2026-10-16', 'A', 100), ('2026-10-20', 'B', 90)]])
    resultado = consolidar(observaciones)
    assert len(resultado) == 1
    assert resultado.precio.iloc[0] == 90
    assert resultado.n_capturas.iloc[0] == 2
