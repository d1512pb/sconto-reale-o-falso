import pandas as pd

from sconto.auditar_recoleccion import comprobar, cobertura_diaria
from sconto.esquema import a_dataframe


def datos():
    return a_dataframe([dict(fuente='prueba', id_externo='A', vendedor_o_cadena='Tienda',
                             fecha_precio='2026-10-21', fecha_captura='2026-10-21', precio=100,
                             producto_canonico_id='P1')])


def test_cobertura_no_inventa_el_dia_ausente():
    original = datos()
    posterior = original.copy().assign(fecha_precio='2026-10-23', fecha_captura='2026-10-23')
    cobertura = cobertura_diaria(pd.concat([original, posterior], ignore_index=True))
    assert cobertura.fecha_precio.tolist() == ['2026-10-21', '2026-10-23']
    assert cobertura.filas.tolist() == [1, 1]
    assert comprobar(original) == []


def test_auditoria_detecta_duplicados_y_precio_cero():
    original = datos()
    assert 'claves_duplicadas' in comprobar(pd.concat([original, original], ignore_index=True))
    assert 'precios_invalidos' in comprobar(original.assign(precio=0))
