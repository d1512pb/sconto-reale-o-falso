import pandas as pd
import pytest

from sconto.validar_mapeos import aplicar_validaciones


def test_solo_validacion_explicita_activa_ids(tmp_path):
    productos = pd.DataFrame([dict(producto_canonico_id='A', asins='', confianza_match='probable', notas='')])
    ruta = tmp_path / 'mapeos.csv'
    pd.DataFrame([dict(producto_canonico_id='A', tipo_id_externo='asin', id_externo='B000000001', validado='0',
                       fecha_validacion='2026-10-20')]).to_csv(ruta, index=False)
    assert aplicar_validaciones(productos, ruta).asins.iloc[0] == ''
    revisiones = pd.read_csv(ruta, dtype=str)
    revisiones['validado'] = '1'
    revisiones.to_csv(ruta, index=False)
    resultado = aplicar_validaciones(productos, ruta)
    assert resultado.asins.iloc[0] == 'B000000001'
    assert resultado.confianza_match.iloc[0] == 'exacto'


def test_un_id_no_se_aprueba_para_dos_variantes(tmp_path):
    productos = pd.DataFrame([dict(producto_canonico_id=pid, asins='', confianza_match='probable', notas='')
                              for pid in ['A', 'B']])
    ruta = tmp_path / 'mapeos.csv'
    pd.DataFrame([dict(producto_canonico_id=pid, tipo_id_externo='asin', id_externo='B000000001', validado='1',
                       fecha_validacion='2026-10-20') for pid in ['A', 'B']]).to_csv(ruta, index=False)
    with pytest.raises(ValueError, match='dos productos'):
        aplicar_validaciones(productos, ruta)
