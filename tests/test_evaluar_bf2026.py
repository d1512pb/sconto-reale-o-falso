import pandas as pd

from sconto.evaluar_bf2026 import revisar_cobertura
from sconto.eventos import cargar_eventos


def _serie(clave, importe, fuente='qqp_cdmx', fecha_resultado='2026-11-17'):
    fechas = ['2026-09-14', '2026-09-25', '2026-10-05', '2026-10-17', '2026-11-01', '2026-11-10', fecha_resultado]
    return pd.DataFrame(dict(
        fuente=fuente, serie_id=clave, id_externo=clave, canal='tienda_fisica', moneda='MXN',
        vendedor_serie='sucursal', vendedor_o_cadena='Cadena | Sucursal', descripcion_original='Categoría | Variante',
        fecha_precio=fechas, precio=[110, 110, 110, 110, 120, 120, importe]))


def test_evento_abierto_impide_etiquetar_aun_con_cobertura_previa():
    datos = _serie('uno', 100, fecha_resultado='2026-11-13')
    estado, serie = revisar_cobertura(datos, cargar_eventos(), '2026-11-16')
    assert estado['series_con_variables'] == 1
    assert estado['series_con_resultado'] == 0 and pd.isna(serie.etiqueta_bajo.item())
    assert 'evento_abierto' in estado['motivos']


def test_piloto_y_corte_truncado_no_habilitan_qqp_anual():
    datos = pd.concat([_serie('anual', 100, fecha_resultado='2026-11-14'),
                       _serie('piloto', 180, fuente='profeco_buen_fin')])
    estado, _ = revisar_cobertura(datos, cargar_eventos(), '2026-11-18')
    assert estado['series_con_resultado'] == 1
    assert estado['ultimo_precio_QQP'] == '2026-11-14'
    assert 'publicacion_qqp_aun_no_cubre_fin_del_evento' in estado['motivos']


def test_evaluacion_retrospectiva_y_diagnostico_posterior_cierran_por_separado():
    datos = pd.concat([_serie('uno', 100), _serie('dos', 180)])
    estado, _ = revisar_cobertura(datos, cargar_eventos(), '2026-11-18')
    assert estado['estado'] == 'preparado_para_evaluacion_retrospectiva'
    assert estado['clases_con_resultado'] == {'0': 1, '1': 1}
    assert estado['motivos'] == []
    assert not estado['diagnostico_posterior_cerrado'] and not estado['evaluacion_prospectiva']
    posterior, _ = revisar_cobertura(datos, cargar_eventos(), '2026-12-02')
    assert posterior['diagnostico_posterior_cerrado']
