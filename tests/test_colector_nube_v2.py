from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import json
import sqlite3

import pytest
from requests import Response

from sconto.cliente import Bloqueado
from sconto.colector_nube_v2 import PROFECO, QQP, Programador, _tareas, estado, paso
from sconto.fuentes import qqp_vigilar
from sconto.fuentes.profeco_buenfin import _capturar, _guardar_respuesta, _leer, reintento_desde
from sconto.intraday import IntradayStore


HORA_CDMX = datetime(2026, 11, 16, 23, tzinfo=timezone.utc)
URL = 'https://elbuenfin.profeco.gob.mx/api/get/producto/10/4/0/35251'


def test_programador_una_vez_por_dia_y_read_only(tmp_path):
    assert estado(tmp_path) == []
    assert list(tmp_path.iterdir()) == []
    programa = Programador(IntradayStore(tmp_path))
    assert programa.tomar(PROFECO, HORA_CDMX - timedelta(seconds=1)) is None
    dia, intento = programa.tomar(PROFECO, HORA_CDMX)
    assert (dia, intento) == (date(2026, 11, 16), 1)
    assert programa.tomar(PROFECO, HORA_CDMX + timedelta(minutes=1)) is None
    programa.cerrar(PROFECO, dia, intento, HORA_CDMX, {'estado': 'ok'})
    assert programa.tomar(PROFECO, HORA_CDMX + timedelta(minutes=1)) is None
    assert estado(tmp_path)[0]['estado'] == 'ok'
    assert programa.tomar(PROFECO, HORA_CDMX + timedelta(days=1)) == (date(2026, 11, 17), 1)


def test_recupera_interrupcion_y_acota_reintentos(tmp_path):
    store = IntradayStore(tmp_path)
    programa = Programador(store)
    assert programa.tomar(PROFECO, HORA_CDMX)
    programa = Programador(store)
    programa.recuperar_interrumpidos(HORA_CDMX)
    dia, intento = programa.tomar(PROFECO, HORA_CDMX)
    assert intento == 2
    programa.cerrar(PROFECO, dia, intento, HORA_CDMX, {'estado': 'fallo'})
    assert programa.tomar(PROFECO, HORA_CDMX + timedelta(hours=2)) is None
    assert {x['estado'] for x in estado(tmp_path)} == {'interrumpido', 'fallo'}


def test_fallo_reintenta_despues_de_pausa_y_bloqueo_respeta_retry_after(tmp_path):
    programa = Programador(IntradayStore(tmp_path))
    dia, intento = programa.tomar(PROFECO, HORA_CDMX)
    programa.cerrar(PROFECO, dia, intento, HORA_CDMX, {'estado': 'parcial'})
    assert programa.tomar(PROFECO, HORA_CDMX + timedelta(minutes=14)) is None
    tardia = HORA_CDMX + timedelta(minutes=15)
    dia, intento = programa.tomar(PROFECO, tardia)
    siguiente = tardia + timedelta(days=1, hours=1)
    programa.cerrar(PROFECO, dia, intento, tardia, {'estado': 'bloqueado', 'siguiente_utc': siguiente.isoformat()})
    assert programa.tomar(PROFECO, tardia + timedelta(days=1)) is None
    assert programa.tomar(PROFECO, siguiente) == (date(2026, 11, 17), 1)


def test_calendario_buen_fin_qqp_y_respaldo():
    assert [x.nombre for x, _ in _tareas(date(2026, 11, 16))] == ['profeco_buen_fin', 'respaldo_privado']
    assert [x for x, _ in _tareas(date(2026, 11, 22))][0] == QQP
    assert PROFECO in {x for x, _ in _tareas(date(2026, 12, 1))}
    assert PROFECO not in {x for x, _ in _tareas(date(2026, 12, 2))}


def test_cloud_paso_detecta_cache_sin_rehacer_consultas(tmp_path, monkeypatch):
    llamados = []
    monkeypatch.setattr('sconto.colector_nube_v2._operar_profeco',
                        lambda _store, fecha: (llamados.append(fecha) or {'estado': 'ok'}))
    programa = Programador(IntradayStore(tmp_path))
    paso(programa, lambda: HORA_CDMX)
    paso(programa, lambda: HORA_CDMX)
    assert llamados == [date(2026, 11, 16)]
    with sqlite3.connect(programa.store.database) as db:
        assert json.loads(db.execute('SELECT resultado_json FROM trabajos_nube').fetchone()[0]) == {'estado': 'ok'}


@pytest.mark.parametrize('cabecera,segundos', [('3600', 3600), ('Tue, 17 Nov 2026 00:00:00 GMT', 3600), ('x', None)])
def test_retry_after_admite_fecha_y_segundos(cabecera, segundos):
    respuesta = Response()
    respuesta.status_code = 429
    respuesta.headers['Retry-After'] = cabecera
    resultado = reintento_desde(Bloqueado('429', respuesta), HORA_CDMX)
    assert resultado == ((HORA_CDMX + timedelta(seconds=segundos)).isoformat() if segundos else None)


def test_recupera_confirmacion_interrumpida_sin_volver_a_consultar(tmp_path):
    respuesta = Response()
    respuesta.status_code = 200
    respuesta.url = URL
    respuesta.raw = BytesIO(b'[]')
    _guardar_respuesta(tmp_path, 'dato', respuesta, b'[]')
    (tmp_path / 'dato.json').rename(tmp_path / 'dato.json.part')

    class SinRed:
        def get(self, *args, **kwargs):
            pytest.fail('El par verificable debe recuperarse sin consultar')

    _capturar(SinRed(), tmp_path, 'dato', URL)
    datos, meta, ruta = _leer(tmp_path, 'dato', URL)
    assert datos == [] and meta['bytes'] == 2 and ruta.name == 'dato.gz'
    assert list(tmp_path.glob('*.part')) == []


def test_qqp_reconoce_el_rar_validado_aunque_haya_cambiado_el_ultimo_estado(tmp_path, monkeypatch):
    url = 'https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar'
    sha = '1' * 64
    nombre = f'QQP_2026.{sha}.rar'
    cuerpo = b'archivo de prueba'
    descarga = []

    class Catalogo:
        content = f'<a href="{url}">Publicación</a>'.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def get(self, _url):
            return self

    def descargar(_cliente, _url, salida, _esperado, reserva):
        descarga.append(reserva)
        salida.with_name(nombre).write_bytes(cuerpo)
        return dict(archivo=nombre, sha256=sha, bytes_descargados=len(cuerpo), miembros_csv=1,
                    estado='candidato_validado')

    monkeypatch.setattr(qqp_vigilar, '_descargar', descargar)
    monkeypatch.setattr(qqp_vigilar, 'huella_remota', lambda *_: dict(
        bytes_remotos=len(cuerpo), huella_inicio='huella', etag='test-etag', ultima_modificacion=None,
    ))
    archivo_incumbente = tmp_path / 'no_existe.rar'
    resultado = qqp_vigilar.vigilar(Catalogo(), 2026, tmp_path, archivo_incumbente, HORA_CDMX, reserva_bytes=100)
    assert json.loads((tmp_path / f'{nombre}.json').read_bytes()) == resultado
    (tmp_path / 'estado.json').write_text('{"estado":"bloqueado"}', encoding='utf-8')
    siguiente = qqp_vigilar.vigilar(Catalogo(), 2026, tmp_path, archivo_incumbente, HORA_CDMX + timedelta(days=7))
    assert resultado == siguiente and descarga == [100]


def test_qqp_protege_reserva_de_disco_antes_de_descargar(tmp_path):
    destino = tmp_path / 'QQP_2026.rar'
    with pytest.raises(qqp_vigilar.EspacioInsuficiente):
        qqp_vigilar._descargar(None, 'https://example.com', destino, {'bytes_remotos': 1}, reserva_bytes=1 << 64)
    assert list(tmp_path.iterdir()) == []
