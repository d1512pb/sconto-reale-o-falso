import gzip
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from sconto.intraday import IntradayStore, Observacion, Oferta, Trabajo


HORA = datetime(2026, 11, 14, 15, tzinfo=timezone.utc)
OFERTA = Oferta('1234', 'P4-10', 'Liverpool', 'https://example.com/producto/1234',
                variante='LAPTOP-16GB', vendedor='Tienda oficial', condicion='Nueva')


def registrar(store, hora, precio, oferta=OFERTA, **campos):
    captura = store.tomar(Trabajo('tiendas', oferta.enlace, hora), ahora=hora)
    assert captura is not None
    assert store.registrar(captura, fetched_at=hora, resultado='ok', estado_http=200, crudo=b'contenido',
                           observaciones=[Observacion(oferta, precio, 'MXN', **campos)])
    return captura


def test_capturas_iguales_se_conservan_y_reprocesar_no_duplica(tmp_path):
    store = IntradayStore(tmp_path)
    primera = registrar(store, HORA, 100)
    segunda = registrar(store, HORA + timedelta(minutes=30), 100)
    assert primera.capture_id != segunda.capture_id
    assert store.tomar(primera.trabajo, ahora=HORA) is None
    assert not store.registrar(primera, fetched_at=HORA, resultado='sin_oferta', estado_http=200)
    archivos = list((tmp_path / 'raw').rglob('*.gz'))
    assert len(archivos) == 2
    assert all(gzip.decompress(archivo.read_bytes()) == b'contenido' for archivo in archivos)
    assert store.estado()['observaciones'] == 2
    assert store.ofertas(OFERTA.producto_id)[0]['capture_id'] == segunda.capture_id


def test_fallo_reintentable_y_trabajos_paralelos(tmp_path):
    store = IntradayStore(tmp_path)
    trabajo = Trabajo('tiendas', OFERTA.enlace, HORA, max_intentos=2)
    with ThreadPoolExecutor(max_workers=4) as grupo:
        capturas = list(grupo.map(lambda _: store.tomar(trabajo, ahora=HORA), range(4)))
    primera, = (captura for captura in capturas if captura)
    store.registrar(primera, fetched_at=HORA, resultado='fallo', reintento_permitido=True)
    segunda = store.tomar(trabajo, ahora=HORA)
    assert segunda.intento == 2
    assert not store.registrar(primera, fetched_at=HORA, resultado='fallo')
    assert store.vencidos(ahora=HORA + timedelta(minutes=16)) == 1
    assert store.tomar(trabajo, ahora=HORA + timedelta(minutes=17)) is None
    assert store.estado()['intentos'] == 2
    assert [fila['resultado'] for fila in store.estado()['fuentes']] == ['fallo', 'interrumpido']
    assert store.estado()['observaciones'] == 0


def test_variantes_vendedores_y_condiciones_son_series_distintas(tmp_path):
    store = IntradayStore(tmp_path)
    ofertas = (OFERTA, replace(OFERTA, variante='LAPTOP-8GB'),
               replace(OFERTA, vendedor='Distribuidor'), replace(OFERTA, condicion='Reacondicionada'))
    for indice, oferta in enumerate(ofertas):
        registrar(store, HORA + timedelta(minutes=indice), 100 - indice, oferta)
    assert len(store.ofertas(OFERTA.producto_id)) == 4
    assert {serie['comprobaciones'] for serie in store.precios_diarios(OFERTA.producto_id)} == {1}


def test_agregacion_diaria_cdmx_con_mediana_y_ultimo(tmp_path):
    store = IntradayStore(tmp_path)
    for indice, precio in enumerate((100, 200, 40, 120)):
        registrar(store, HORA + timedelta(minutes=indice), precio)
    registrar(store, HORA + timedelta(hours=13), 125)
    filas = store.precios_diarios(OFERTA.producto_id)
    assert [(fila['fecha'], fila['mediana'], fila['comprobaciones']) for fila in filas] == [
        ('2026-11-14', 120, 5)]
    assert (filas[0]['minimo'], filas[0]['maximo'], filas[0]['ultimo']) == (40, 200, 125)
    registrar(store, HORA + timedelta(hours=15), 400)
    assert store.precios_diarios(OFERTA.producto_id)[0]['fecha'] == '2026-11-15'


def test_hora_historica_desconocida_y_actualizacion_de_fuente_independiente(tmp_path):
    store = IntradayStore(tmp_path)
    anterior = date(2026, 11, 10)
    registrar(store, HORA, 300, precision_temporal='dia', fecha_precio=anterior)
    vieja = store.ofertas(OFERTA.producto_id)[0]
    assert vieja['observed_at'] is None and vieja['source_updated_at'] is None
    assert vieja['fecha_precio'] == anterior.isoformat()
    assert vieja['fetched_at_utc'].startswith('2026-11-14T15:00')
    publicada = HORA - timedelta(hours=3)
    registrar(store, HORA + timedelta(minutes=15), 430, source_updated_at=publicada)
    ultima = store.ofertas(OFERTA.producto_id)[0]
    assert ultima['observed_at'].startswith('2026-11-14T15:15')
    assert ultima['source_updated_at'].startswith('2026-11-14T12:00')


def test_bloqueo_no_admite_precio_y_crudo_original_no_se_copia(tmp_path):
    store = IntradayStore(tmp_path / 'intradia')
    cuerpo = b'respuesta 403'
    original = tmp_path / 'original.gz'
    original.write_bytes(gzip.compress(cuerpo))
    captura = store.tomar(Trabajo('tiendas', OFERTA.enlace, HORA), ahora=HORA)
    with pytest.raises(ValueError, match='evidencia'):
        store.registrar(captura, fetched_at=HORA, resultado='bloqueado', estado_http=403,
                        observaciones=[Observacion(OFERTA, 1, 'MXN')])
    assert store.registrar(captura, fetched_at=HORA, resultado='bloqueado', estado_http=403,
                           crudo=cuerpo, crudo_preexistente=original)
    assert not (store.root / 'raw').exists()
    assert store.ofertas(OFERTA.producto_id) == []
    with store._conexion() as conexion:
        guardada = conexion.execute('SELECT ruta_cruda, sha256 FROM capturas').fetchone()
    assert guardada['ruta_cruda'] == '../original.gz'
    assert guardada['sha256'] == hashlib.sha256(cuerpo).hexdigest()


def test_historial_publicado_con_varias_fechas_se_mantiene_separado(tmp_path):
    store = IntradayStore(tmp_path)
    captura = store.tomar(Trabajo('profeco_buen_fin', OFERTA.enlace, HORA), ahora=HORA)
    dias = (date(2026, 11, 12), date(2026, 11, 13))
    puntos = [Observacion(OFERTA, 579, 'MXN', precision_temporal='dia', fecha_precio=dia) for dia in dias]
    assert store.registrar(captura, fetched_at=HORA, resultado='ok', estado_http=200,
                           crudo=b'evidencia', observaciones=puntos, diario_publicado=True)
    assert store.estado()['observaciones'] == 0
    assert store.estado()['observaciones_diarias_fuente'] == 2
    assert store.precios_diarios(OFERTA.producto_id) == []
    hora_dos = HORA + timedelta(minutes=10)
    consulta_dos = store.tomar(Trabajo('profeco_buen_fin', OFERTA.enlace, hora_dos), ahora=hora_dos)
    assert store.registrar(consulta_dos, fetched_at=hora_dos, resultado='ok', estado_http=200,
                           crudo=b'evidencia2', observaciones=[puntos[0], replace(puntos[1], precio=600)],
                           diario_publicado=True)
    with store._conexion() as conexion:
        diarios = conexion.execute('''
            SELECT precio, consultas, valores_distintos FROM precios_diarios_fuente ORDER BY fecha_precio
        ''').fetchall()
    assert [tuple(fila) for fila in diarios] == [(579, 2, 1), (None, 2, 2)]
