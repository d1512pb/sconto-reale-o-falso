from datetime import datetime, timezone
import sqlite3

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from sconto.api_v2 import VERSION, crear_api
from sconto.decisiones_v2 import VERSION as VERSION_MOTOR
from sconto.importar_tienda_manual_v2 import importar as importar_cotizacion
from sconto.intraday import IntradayStore, Observacion, Oferta, Trabajo
from sconto.respaldo_v2 import respaldar, restaurar


AHORA = datetime(2026, 11, 14, 23, tzinfo=timezone.utc)
URL = 'https://www.sears.com.mx/producto/1000/'


def conservar(store):
    oferta = Oferta('1000', 'modelo-aplicacion', 'Sears', URL, variante='SKU1000', vendedor='Sears', condicion='nuevo')
    intento = store.tomar(Trabajo('tiendas', URL, AHORA), ahora=AHORA)
    store.registrar(intento, fetched_at=AHORA, estado_http=200, resultado='ok', crudo=b'prueba archivada',
                   observaciones=[Observacion(oferta, 1000, 'MXN', condiciones={'sesion': 'privado'})])
    enlace = 'https://elbuenfin.profeco.gob.mx/api/get/producto/10/4/0/123'
    fisica = Oferta('sucursal-modelo', 'PROFECO-BF26-123', 'Sucursal física', enlace, vendedor='Sucursal')
    intento = store.tomar(Trabajo('profeco_buen_fin', enlace, AHORA), ahora=AHORA)
    store.registrar(intento, fetched_at=AHORA, estado_http=200, resultado='ok', crudo=b'prueba diaria',
                   diario_publicado=True, observaciones=[Observacion(fisica, 950, 'MXN', precision_temporal='dia',
                      fecha_precio=AHORA.date(), condiciones={'marca': 'Marca', 'descripcion': 'Computación',
                                                                  'direccion': 'excluir'})])


def test_precio_diario_y_venta_web_permanecen_separados(tmp_path):
    conservar(IntradayStore(tmp_path))
    with TestClient(crear_api(root=tmp_path, datos_profeco=True, privadas=True, reloj=lambda: AHORA)) as cliente:
        fisicos = cliente.get('/v1/products', params={'q': 'COMPUTACION', 'canal': 'tienda_fisica'}).json()['productos']
        assert fisicos[0]['producto_id'] == 'PROFECO-BF26-123'
        assert cliente.get('/v1/products/PROFECO-BF26-123/offers').json()['ofertas'] == []
        historia = cliente.get('/v1/products/PROFECO-BF26-123/history').json()['precios_diarios']
        assert historia[0]['precision_temporal'] == 'dia'
        assert historia[0]['canal'] == 'tienda_fisica'
        assert historia[0]['precio'] == 950
        assert 'observed_at' not in historia[0] and 'direccion' not in historia[0]
        respuesta = cliente.get('/v1/products/modelo-aplicacion/offers')
        oferta = respuesta.json()['ofertas'][0]
        assert oferta['decision']['estado'] == 'evidencia_insuficiente'
        assert 'sesion' not in respuesta.text and oferta['canal'] == 'en_linea'
        assert cliente.get('/v1/version').json()['version'] == VERSION
        assert cliente.get('/v1/version').json()['motor'] == VERSION_MOTOR
        estado = cliente.get('/v1/products/modelo-aplicacion/decision').json()
        assert estado['evaluado_utc'] == AHORA.isoformat() and estado['motor'] == VERSION_MOTOR
    with TestClient(crear_api(root=tmp_path)) as cliente:
        assert cliente.get('/v1/products/modelo-aplicacion/offers').status_code == 404
        assert cliente.get('/v1/products/PROFECO-BF26-123/history').status_code == 404
        assert cliente.get('/v1/status').json()['fuentes'] == []


def test_presupuesto_y_topes_de_consulta(tmp_path):
    with TestClient(crear_api(root=tmp_path, max_peticiones=2)) as cliente:
        assert cliente.get('/v1/products', params={'limit': 100000}).status_code == 422
        assert cliente.get('/v1/products', params={'q': 'x' * 150}).status_code == 422
        respuesta = cliente.get('/v1/version')
        assert respuesta.status_code == 429 and respuesta.headers['Retry-After'] == '60'
        assert cliente.get('/health').status_code == 200


def test_cotizacion_autorizada_usa_stock_y_referencia_comparable(tmp_path):
    store = IntradayStore(tmp_path / 'datos')
    catalogo = tmp_path / 'catalogo.sqlite'
    with sqlite3.connect(catalogo) as db:
        db.executescript('''
            CREATE TABLE eventos (evento_id, base_inicio, base_fin);
            INSERT INTO eventos VALUES ('BF2026', '2026-09-14', '2026-10-29');
            CREATE TABLE catalogo_consulta (producto_canonico_id, nombre, categoria_app);
            INSERT INTO catalogo_consulta VALUES ('modelo-aplicacion', 'Modelo de prueba', 'computadoras');
        ''')
    soporte = tmp_path / 'prueba.txt'
    soporte.write_text('Permiso sintético')
    cotizacion = dict(tienda='liverpool', url='https://www.liverpool.com.mx/tienda/pdp/equipo/1900000000?skuid=1900000000',
        producto_id='modelo-aplicacion', variante='Prueba 512 GB', sku='1900000000', vendedor='Tienda de prueba',
        condicion='nuevo', disponibilidad='disponible', identidad_verificada=True, envio_mxn='0', otros_cargos_mxn='0',
        contexto_costo='envio_cdmx', alcance_permiso='publicacion', referencia_permiso='Prueba de publicación',
        tipo_evidencia='cotizacion_del_vendedor')
    for dia, precio in [('2026-09-14', '1000'), ('2026-09-22', '1000'), ('2026-10-03', '1000'),
                        ('2026-10-15', '1000'), ('2026-11-14', '900')]:
        importar_cotizacion(dict(cotizacion, precio_publicado_mxn=precio, costo_total_mxn=precio,
                                  observado_utc=dia+'T22:55:00+00:00'), soporte, store, AHORA)
    with TestClient(crear_api(root=store.root, catalogo=catalogo, reloj=lambda: AHORA)) as cliente:
        respuesta = cliente.get('/v1/products/modelo-aplicacion/offers')
        [oferta] = respuesta.json()['ofertas']
        assert oferta['decision']['estado'] == 'precio_favorable'
        assert oferta['disponibilidad'] == 'en_stock' and oferta['decision']['ahorro_pct'] == 10
        assert 'referencia_permiso' not in respuesta.text and 'sha256_documento' not in respuesta.text


def test_respaldo_recupera_crudos_e_historia(tmp_path):
    base = tmp_path / 'original'
    conservar(IntradayStore(base))
    copia = tmp_path / 'respaldo.zip'
    respaldar(base, copia)
    recuperada = tmp_path / 'restaurada'
    restaurar(copia, recuperada)
    with sqlite3.connect(recuperada / 'intradia.sqlite3') as conn:
        for (ruta,) in conn.execute('SELECT ruta_cruda FROM capturas'):
            assert (recuperada / ruta).is_file()
    with TestClient(crear_api(root=recuperada, datos_profeco=True)) as cliente:
        assert cliente.get('/v1/products/PROFECO-BF26-123/history').json()['precios_diarios'][0]['precio'] == 950
    with pytest.raises(FileExistsError):
        restaurar(copia, recuperada)
