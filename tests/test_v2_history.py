import pandas as pd

from sconto.eventos import cargar_eventos
from sconto.v2_history import VARIABLES, preparar_series


def test_el_evento_cambia_el_resultado_y_preserva_variables_previas():
    fechas = ['2024-09-16', '2024-09-25', '2024-10-04', '2024-10-17',
              '2024-11-03', '2024-11-14', '2024-11-15']
    datos = pd.DataFrame(dict(
        fuente='qqp_cdmx', serie_id='serie', id_externo='producto', canal='tienda_fisica', moneda='MXN',
        vendedor_serie='sucursal', vendedor_o_cadena='Cadena | Sucursal', descripcion_original='Categoría | Variante',
        fecha_precio=fechas, precio=[110, 120, 130, 140, 130, 150, 110]))
    eventos = cargar_eventos().query("evento_id == 'BF2024'")
    original = preparar_series(datos, eventos, pd.Timestamp('2026-11-14'))
    alterno = preparar_series(datos.assign(precio=datos.precio.mask(datos.fecha_precio.eq(fechas[-1]), 210)),
                             eventos, pd.Timestamp('2026-11-14'))
    antes_de_cierre = preparar_series(datos, eventos, pd.Timestamp('2024-11-16'))

    pd.testing.assert_frame_equal(original[VARIABLES], alterno[VARIABLES])
    assert original.etiqueta_bajo.item() == 1
    assert alterno.etiqueta_bajo.item() == 0
    assert pd.isna(antes_de_cierre.etiqueta_bajo.item())

