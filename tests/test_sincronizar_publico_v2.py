"""Pruebas sintéticas con receptores aislados. No abren sesiones Fly ni leen credenciales."""
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys

import pytest

from sconto.importar_tienda_manual_v2 import importar
from sconto.intraday import IntradayStore
from sconto.sincronizar_publico_v2 import _publicables, enviar, lote, recibir


@pytest.fixture
def fuente(tmp_path):
    return IntradayStore(tmp_path / 'sintetico_no_publicar' / 'origen')


def _cotizar(store, sku, alcance='publicacion', precio='100', promocion=None):
    soporte = store.root / 'evidencia_sintetica.txt'
    soporte.write_text('SOPORTE PRIVADO SINTÉTICO')
    observado = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    return importar(
        dict(tienda='liverpool', sku=sku, producto_id='SOLO_PRUEBA', variante='Variante de prueba',
             vendedor='Vendedor de prueba', identidad_verificada=True, disponibilidad='disponible',
             url=f'https://www.liverpool.com.mx/tienda/pdp/test/{sku}?skuid={sku}', condicion='nuevo',
             observado_utc=observado, precio_publicado_mxn=precio, envio_mxn='0', otros_cargos_mxn='0',
             costo_total_mxn=precio, contexto_costo='envio_cdmx', tipo_evidencia='cotizacion_del_vendedor',
             referencia_permiso='REFERENCIA PRIVADA SINTÉTICA', alcance_permiso=alcance, gtin='012345678905',
             promocion_condicionada=promocion),
        soporte, store,
    )


def test_remitente_y_receptor_stdin_persisten_solo_lo_publicable(tmp_path, fuente):
    publico = _cotizar(fuente, '1900000001', promocion=False)
    sin_informacion = _cotizar(fuente, '1900000003', precio='99')
    _cotizar(fuente, '1900000002', alcance='interno')
    destino = tmp_path / 'sintetico_no_publicar' / 'destino'
    llamadas = []

    def local(app, maquina, cuerpo):
        assert app == 'solo-prueba' and maquina == '00000000000000'
        assert 'REFERENCIA' not in cuerpo and 'SOPORTE' not in cuerpo and '1900000002' not in cuerpo
        llamadas.append(cuerpo)
        salida = subprocess.run([sys.executable, '-m', 'sconto.sincronizar_publico_v2',
                                 '--almacen', str(destino), 'recibir'], input=cuerpo, text=True,
                                capture_output=True, check=True, timeout=10)
        return json.loads(salida.stdout)

    with pytest.raises(RuntimeError, match='acuse'):
        enviar(fuente, 'solo-prueba', '00000000000000',
               transporte=lambda *entrega: {**local(*entrega), 'sha256': 'acuse incorrecto'})
    # Simula una segunda ejecución después de que se perdió el primer acuse.
    assert enviar(fuente, 'solo-prueba', '00000000000000', transporte=local) == {
        'confirmadas': 2, 'nuevas': 0, 'por_enviar': 0}
    assert llamadas[0] == llamadas[1]
    assert enviar(fuente, 'solo-prueba', '00000000000000', transporte=local)['confirmadas'] == 0
    assert len(llamadas) == 2

    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from sconto.api_v2 import crear_api

    with TestClient(crear_api(root=destino)) as cliente:
        desconocida, oferta = sorted(cliente.get('/v1/products/SOLO_PRUEBA/offers').json()['ofertas'],
                                      key=lambda fila: fila['precio'])
        assert oferta['costo_total_confirmado'] == 100
        assert oferta['promocion_condicionada'] is False
        assert desconocida['promocion_condicionada'] is None
        assert cliente.get('/v1/products/SOLO_PRUEBA/comparacion-actual').json()['grupos'] == []
    with IntradayStore(destino)._conexion() as conn:
        assert {tuple(f) for f in conn.execute('SELECT capture_id,sha256,ruta_cruda FROM capturas')} == {
            (publico['capture_id'], None, None), (sin_informacion['capture_id'], None, None)}
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert not (destino / 'raw').exists()


@pytest.mark.parametrize('manipulacion', ['permiso', 'crudo', 'fisica', 'huella', 'exceso'])
def test_lote_no_autorizado_o_malformado_no_cambia_destino(tmp_path, fuente, manipulacion):
    _cotizar(fuente, '1900000001')
    _cotizar(fuente, '1900000002')
    primera, segunda = _publicables(fuente)
    if manipulacion == 'permiso':
        segunda['condiciones']['publicable'] = False
    elif manipulacion == 'crudo':
        segunda['condiciones']['ruta_cruda'] = 'RUTA-PRIVADA'
    elif manipulacion == 'fisica':
        segunda['precision_temporal'] = 'dia'
    contenido = lote([primera, segunda])
    if manipulacion == 'huella':
        contenido = contenido.replace('"precio":100.0', '"precio":99')
    elif manipulacion == 'exceso':
        contenido += ' ' * 32_768
    destino = IntradayStore(tmp_path / 'sintetico_no_publicar' / 'destino')
    with pytest.raises(ValueError):
        recibir(destino, contenido)
    assert destino.estado()['observaciones'] == 0


def test_conflicto_en_captura_revierte_todo_el_lote(tmp_path, fuente):
    _cotizar(fuente, '1900000001')
    destino = IntradayStore(tmp_path / 'sintetico_no_publicar' / 'destino')
    [anterior] = _publicables(fuente)
    assert recibir(destino, lote([anterior]))['nuevas'] == 1
    _cotizar(fuente, '1900000002')
    [nueva] = [f for f in _publicables(fuente) if f['capture_id'] != anterior['capture_id']]
    with pytest.raises(ValueError, match='difiere'):
        recibir(destino, lote([nueva, {**anterior, 'precio': 99}]))
    assert destino.estado()['observaciones'] == 1
