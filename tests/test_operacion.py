import pandas as pd
import pytest

from sconto import almacen, operacion
from sconto.objetivos_diarios import seleccionar


def test_lista_fija_equilibrada_no_modifica_catalogo():
    productos = pd.DataFrame({'origen': ['preciometro'] * 8, 'preciometro_ids': list('12345678'),
                              'producto_canonico_id': ['P' + str(numero) for numero in range(8)], 'prioridad': ['4'] * 8})
    lista = pd.DataFrame({'preciometro_id': list('12345678'), 'familia': ['a'] * 4 + ['b'] * 4,
                         'prioridad': ['4'] * 8, 'url': ['https://test/' + str(numero) for numero in range(8)]})
    original = productos.copy(deep=True)
    resultado = seleccionar(productos, lista, 4)
    assert resultado.preciometro_id.tolist() == ['1', '5', '2', '6']
    assert resultado.producto_canonico_id.is_unique
    pd.testing.assert_frame_equal(productos, original)
    pd.testing.assert_frame_equal(resultado, seleccionar(productos, lista, 4))


@pytest.mark.parametrize('estados,entorno,esperado', [
    ([], 'github', False),
    ([('preciometro', 'ok', 'github')], 'github', True),
    ([('preciometro', 'parcial', 'github')], 'github', False),
    ([('preciometro', 'ok', 'local'), ('mercadolibre', 'sin_credenciales', 'github')], 'github', True),
    ([('preciometro', 'ok', 'github')], 'local', False),
    ([('preciometro', 'ok', 'github'), ('tiendas', 'ok', 'local')], 'local', True),
])
def test_salud_exige_cobertura_real_no_credenciales_opcionales(tmp_path, monkeypatch, estados, entorno, esperado):
    ruta = tmp_path / 'estado.csv'
    pd.DataFrame([dict(fuente=fuente, fecha='2026-10-21', estado=estado, entorno=origen)
                  for fuente, estado, origen in estados], columns=['fuente', 'fecha', 'estado', 'entorno']).to_csv(ruta, index=False)
    monkeypatch.setattr(operacion, 'ESTADO_FUENTES', ruta)
    monkeypatch.setattr(operacion, 'combinar_estados', lambda: None)
    assert operacion.salud(entorno, '2026-10-21')['ok'] is esperado
    assert not operacion.salud(entorno, '2026-10-22')['ok']


def test_candado_se_libera_incluso_ante_excepcion(tmp_path):
    ruta = tmp_path / 'ciclo'
    with pytest.raises(RuntimeError):
        with almacen._Candado(ruta, espera_max=0):
            raise RuntimeError('interrupcion sintetica')
    with almacen._Candado(ruta, espera_max=0):
        with pytest.raises(TimeoutError):
            with almacen._Candado(ruta, espera_max=0):
                pytest.fail('No debe admitir dos ciclos simultaneos')


@pytest.mark.parametrize('segundo,estado,esperado', [
    ('2026-10-21', 'parcial', True), ('2026-10-22', 'parcial', False), ('2026-10-21', 'ok', False)])
def test_alerta_cobertura_parcial_dos_dias_consecutivos(tmp_path, monkeypatch, segundo, estado, esperado):
    ruta = tmp_path / 'estados.csv'
    pd.DataFrame([dict(fuente='preciometro', entorno='github', fecha=fecha, estado=valor, detalle='prueba')
                  for fecha, valor in [('2026-10-20', 'parcial'), (segundo, estado)]]).to_csv(ruta, index=False)
    alerta = tmp_path / 'ALERTA.md'
    monkeypatch.setattr(almacen, 'ESTADO_FUENTES', ruta)
    monkeypatch.setattr(almacen, 'ALERTA', alerta)
    assert bool(almacen.revisar_alertas()) is esperado
    assert alerta.exists() is esperado
