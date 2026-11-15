from datetime import date, datetime, timezone
import gzip
import json

import pytest

from sconto.fuentes.qqp_vigilar import descubrir, vigilar
from sconto.importar_tienda_manual_v2 import importar, normalizar
from sconto.intraday import IntradayStore
from sconto.operacion_profeco_bf_v2 import evaluar


AHORA = datetime(2026, 11, 15, 0, 15, tzinfo=timezone.utc)


@pytest.fixture
def cotizacion():
    return dict(tienda='liverpool', url='https://www.liverpool.com.mx/tienda/pdp/equipo/1900000000?skuid=1900000000',
                producto_id='PRUEBA_AUTOMATIZADA', variante='Prueba 512 GB', sku='1900000000',
                vendedor='Tienda de prueba', condicion='nuevo', disponibilidad='disponible',
                identidad_verificada=True, observado_utc='2026-11-14T17:40:00-06:00',
                precio_publicado_mxn='299.99', envio_mxn='50', otros_cargos_mxn='0',
                costo_total_mxn='349.99', contexto_costo='envio_cdmx', alcance_permiso='interno',
                referencia_permiso='Permiso simulado para prueba', tipo_evidencia='cotizacion_del_vendedor')


def test_importa_cotizacion_con_evidencia_sin_simular_respuesta_http(tmp_path, cotizacion):
    store = IntradayStore(tmp_path / 'almacen')
    evidencia = tmp_path / 'prueba.txt'
    evidencia.write_text('Soporte sintético de prueba', encoding='utf-8')
    resultado = importar(cotizacion, evidencia, store, AHORA)
    assert resultado['nueva'] and not resultado['publicable']
    assert not importar(cotizacion, evidencia, store, AHORA)['nueva']
    [oferta] = store.ofertas(cotizacion['producto_id'])
    assert oferta['observed_at'] == '2026-11-14T23:40:00.000000Z'
    assert oferta['source_updated_at'] is None
    assert oferta['condiciones']['costo_total_confirmado'] == 349.99
    assert oferta['condiciones']['contexto_costo'] == 'envio_cdmx'
    with store._conexion() as conexion:
        fila = conexion.execute('SELECT * FROM capturas').fetchone()
        crudo = json.loads(gzip.decompress((store.root / fila['ruta_cruda']).read_bytes()))
        assert fila['estado_http'] is None and 'sha256_documento' in crudo
        assert 'referencia_permiso' not in oferta['condiciones']
    with pytest.raises(ValueError, match='diferente'):
        importar({**cotizacion, 'alcance_permiso': 'publicacion'}, evidencia, store, AHORA)


@pytest.mark.parametrize('ajuste', [
    {'costo_total_mxn': '299.99'}, {'envio_mxn': None}, {'variante': None}, {'vendedor': None},
    {'contexto_costo': 'Mi dirección particular'}, {'referencia_permiso': ''},
    {'sku': '123'}, {'url': 'https://www.liverpool.com.mx/tienda/pdp/equipo/1900000000?sesion=prueba'},
    {'observado_utc': '2026-11-15T17:40:00-06:00'}, {'observado_utc': '2026-11-14T17:40:00'},
])
def test_rechaza_cotizacion_inconsistente_o_no_documentada(cotizacion, ajuste):
    with pytest.raises(ValueError):
        normalizar({**cotizacion, **ajuste}, AHORA)


def test_envio_desconocido_no_se_infiere_del_precio_visible(cotizacion):
    obs, _ = normalizar({**cotizacion, 'costo_total_mxn': None, 'envio_mxn': None}, AHORA)
    assert obs.condiciones['costo_total_confirmado'] is None
    assert not obs.condiciones['cargos_confirmados']


def test_alerta_distingue_hueco_y_resultado_parcial(tmp_path):
    (tmp_path / '2026-11-16T170000.json').write_text('{"estado":"parcial"}', encoding='utf-8')
    actual = dict(estado='ok', ultimo_dia_precio='2026-11-13')
    avisos = evaluar(tmp_path, date(2026, 11, 17), actual)
    assert len(avisos) == 3 and '2026-11-15' in avisos[0] and '2026-11-16' in avisos[1] and '2026-11-13' in avisos[2]


def test_descubre_solo_enlace_anual_oficial():
    assert descubrir('<a href="/docs/qqp/QQP_2026.rar">2026</a>', 2026) == 'https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar'
    assert descubrir('<a href="https://ejemplo.net/docs/qqp/QQP_2026.rar">2026</a>', 2026) is None


def test_publicacion_mas_corta_no_pisa_archivo_conocido(tmp_path, monkeypatch):
    archivo = tmp_path / 'conservado.rar'
    archivo.write_bytes(b'corte preservado')

    class Consulta:
        content = b'<a href="/docs/qqp/QQP_2026.rar">2026</a>'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def get(self, url):
            return self

    monkeypatch.setattr('sconto.fuentes.qqp_vigilar.huella_remota', lambda *_: dict(bytes_remotos=10, huella_inicio='prefix'))
    monkeypatch.setattr('sconto.fuentes.qqp_vigilar._huella_local', lambda _: 'prefix')
    resultado = vigilar(Consulta(), 2026, tmp_path, archivo, AHORA)
    assert resultado['estado'] == 'publicacion_mas_corta'
    assert archivo.read_bytes() == b'corte preservado'
