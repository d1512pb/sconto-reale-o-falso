import pandas as pd
import pytest

from sconto import dataset
from sconto.cuaderno import auditoria_limpieza
from sconto.esquema import a_dataframe


def test_corte_fijo_y_contabilidad():
    fila = dict(fuente='preciometro', metodo='agregador', canal='en_linea', tipo_id_externo='preciometro',
                id_externo='1', precio=100, fecha_precio='2026-11-07', fecha_captura='2026-11-07',
                tipo_precio='minimo_diario_multitienda', vendedor_o_cadena='Tienda', ruta_raw='prueba')
    datos = a_dataframe([fila, fila, dict(fila, precio=-1), dict(fila, fecha_precio='2026-11-08', fecha_captura='2026-11-08')])
    validas, excl = dataset.validar(datos, fecha_referencia='2026-11-07')
    assert len(validas) == 2
    assert set(excl.motivo_exclusion) == {'precio_no_positivo', 'fecha_futura'}
    consolidadas = dataset.consolidar(validas)
    assert len(consolidadas) == 1
    assert int(consolidadas.n_capturas.sum()) == 2
    auditoria_limpieza(datos, validas, consolidadas, excl)
    with pytest.raises(ValueError, match='perdió capturas'):
        auditoria_limpieza(datos, validas, consolidadas, excl.iloc[:1])
