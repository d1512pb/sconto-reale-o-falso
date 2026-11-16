from datetime import datetime, timedelta, timezone
import json
import sqlite3

from sconto.alimentar_api_v2 import exportar_corte, procesar
from sconto.intraday import IntradayStore


def _entrega(buzon, folio, alcance, sku):
    ahora = datetime.now(timezone.utc) - timedelta(minutes=1)
    campos = dict(tienda='liverpool', url=f'https://www.liverpool.com.mx/tienda/pdp/equipo/{sku}?skuid={sku}',
                  producto_id='PRUEBA_E2E', sku=sku, variante='Prueba 512 GB', vendedor='Tienda de prueba',
                  condicion='nuevo', identidad_verificada=True, disponibilidad='disponible',
                  observado_utc=ahora.isoformat(timespec='seconds'), precio_publicado_mxn='100', envio_mxn='25',
                  otros_cargos_mxn='0', costo_total_mxn='125', contexto_costo='envio_cdmx',
                  tipo_evidencia='cotizacion_del_vendedor', referencia_permiso='REFERENCIA_PRIVADA_PRUEBA',
                  promocion_condicionada='TEXTO_PRIVADO_PRUEBA', alcance_permiso=alcance)
    (buzon / f'{folio}.json').write_text(json.dumps(campos), encoding='utf-8')
    (buzon / f'{folio}.txt').write_text('EVIDENCIA_PRIVADA_PRUEBA', encoding='utf-8')


def test_buzon_retiene_cotizaciones_y_proyecta_solo_autorizadas(tmp_path):
    origen = IntradayStore(tmp_path / 'intradia')
    buzon = tmp_path / 'buzon'
    buzon.mkdir()
    _entrega(buzon, 'interna', 'interno', '1900000000')
    _entrega(buzon, 'publicable', 'publicacion', '1900000001')
    (buzon / 'esperando.json').write_text('{}', encoding='utf-8')
    (buzon / 'invalida.json').write_text('{}', encoding='utf-8')
    (buzon / 'invalida.txt').write_text('Soporte de ejemplo', encoding='utf-8')
    assert procesar(buzon, origen) == dict(nuevas=2, repetidas=0, en_espera=1, rechazadas=1, publicables_nuevas=1)
    assert procesar(buzon, origen) == dict(nuevas=0, repetidas=2, en_espera=1, rechazadas=1, publicables_nuevas=0)
    assert len(origen.ofertas('PRUEBA_E2E')) == 2
    destino = tmp_path / 'publico' / 'intradia.sqlite3'
    assert exportar_corte(origen, destino)['observaciones_online'] == 1
    publico = IntradayStore(destino.parent)
    [fila] = publico.ofertas('PRUEBA_E2E')
    assert fila['anuncio_id'] == 'liverpool:1900000001'
    assert fila['condiciones'] == dict(publicable=True, identidad_verificada=True, cargos_confirmados=True,
                                     contexto_costo='envio_cdmx', costo_total_confirmado=125.0,
                                     promocion_condicionada=True)
    with sqlite3.connect(destino) as db:
        assert db.execute('SELECT sha256,ruta_cruda FROM capturas').fetchall() == [(None, None)]
    assert b'PRIVADA_PRUEBA' not in destino.read_bytes() and b'PRIVADO_PRUEBA' not in destino.read_bytes()


def test_exportacion_permanece_vacia_sin_cotizaciones(tmp_path):
    origen = IntradayStore(tmp_path / 'intradia')
    destino = tmp_path / 'revision' / 'intradia.sqlite3'
    assert exportar_corte(origen, destino)['observaciones_online'] == 0
    assert IntradayStore(destino.parent).estado()['observaciones'] == 0
