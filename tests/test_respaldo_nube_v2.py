from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import sqlite3
import subprocess
from threading import Thread
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as ET

import pytest

from sconto import respaldo_nube_v2 as nube
from sconto.intraday import IntradayStore, Observacion, Oferta, Trabajo


@pytest.fixture
def llave(tmp_path):
    if not shutil.which('age') or not shutil.which('age-keygen'):
        pytest.skip('Se requiere age para el ensayo criptográfico')
    identidad = tmp_path / 'identidad.txt'
    subprocess.run(['age-keygen', '-o', str(identidad)], check=True, capture_output=True)
    destinatario = subprocess.check_output(['age-keygen', '-y', str(identidad)], text=True).strip()
    return identidad, destinatario


@pytest.fixture
def copia(tmp_path, llave):
    origen = tmp_path / 'volumen'
    store = IntradayStore(origen)
    ahora = datetime(2026, 11, 16, 18, tzinfo=timezone.utc)
    enlace = 'https://elbuenfin.profeco.gob.mx/api/get/producto/10/4/0/123'
    intento = store.tomar(Trabajo('profeco_buen_fin', enlace, ahora), ahora=ahora)
    ficha = Oferta('modelo-sucursal', 'PROFECO-BF26-123', 'Sucursal física', enlace)
    store.registrar(intento, fetched_at=ahora, estado_http=200, resultado='ok', crudo=b'prueba diaria',
                   diario_publicado=True, observaciones=[
                       Observacion(ficha, 950, 'MXN', precision_temporal='dia', fecha_precio=ahora.date())])
    contexto = origen / 'profeco/raw/2026-11-16/bf_suspension.json'
    contexto.parent.mkdir(parents=True)
    contexto.write_bytes(b'{"http":429}')
    (origen / '.env').write_text('marcador-de-prueba', encoding='utf-8')
    catalogo = tmp_path / 'catalogo.sqlite'
    with sqlite3.connect(catalogo) as db:
        db.execute('CREATE TABLE catalogo_consulta (id TEXT)')
    archivo = tmp_path / 'respaldo.age'
    resultado = nube.crear(origen, archivo, llave[1], catalogo=catalogo)
    return archivo, resultado, llave[0], origen, catalogo, llave[1]


def comprobar_restauracion(destino):
    assert (destino / 'profeco/raw/2026-11-16/bf_suspension.json').read_bytes() == b'{"http":429}'
    with sqlite3.connect(destino / 'intradia.sqlite3') as db:
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT precio FROM observaciones_diarias_fuente').fetchone() == (950,)
        for (ruta,) in db.execute('SELECT ruta_cruda FROM capturas'):
            assert (destino / ruta).is_file()
    assert not (destino / '.env').exists()
    assert (destino / 'catalogo.sqlite').is_file()


def test_cifra_restaura_y_rechaza_alteracion(copia, tmp_path):
    archivo, metadatos, identidad, *_ = copia
    datos = archivo.read_bytes()
    assert datos.startswith(b'age-encryption.org/v1\n') and b'prueba diaria' not in datos
    destino = tmp_path / 'recuperada'
    nube.abrir(archivo, destino, identidad, sha256=metadatos['sha256'])
    comprobar_restauracion(destino)
    with pytest.raises(FileExistsError):
        nube.abrir(archivo, destino, identidad, sha256=metadatos['sha256'])
    archivo.write_bytes(datos[:-1] + bytes([datos[-1] ^ 1]))
    fallida = tmp_path / 'fallida'
    with pytest.raises(ValueError, match='SHA-256'):
        nube.abrir(archivo, fallida, identidad, sha256=metadatos['sha256'])
    with pytest.raises(ValueError, match='age'):
        nube.abrir(archivo, fallida, identidad, sha256=nube._sha(archivo))
    assert not fallida.exists()


def test_s3_envio_condicional_y_recuperacion_en_otra_carpeta(copia, tmp_path, monkeypatch):
    pytest.importorskip('boto3')
    objetos = {}

    class S3Local(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_PUT(self):
            if self.path in objetos or self.headers.get('If-None-Match') != '*':
                self.send_error(412)
                return
            cuerpo = self.rfile.read(int(self.headers['Content-Length']))
            metadata = {n: self.headers[n] for n in ('x-amz-meta-sha256', 'x-amz-meta-formato')}
            objetos[self.path] = (cuerpo, metadata, self.headers['Authorization'])
            self.send_response(200)
            self.end_headers()

        def servir(self, traer):
            cuerpo, metadata, _ = objetos[self.path]
            self.send_response(200)
            self.send_header('Content-Length', str(len(cuerpo)))
            for nombre, valor in metadata.items():
                self.send_header(nombre, valor)
            self.end_headers()
            if traer:
                self.wfile.write(cuerpo)

        def do_HEAD(self):
            self.servir(False)

        def do_GET(self):
            url = urlsplit(self.path)
            params = parse_qs(url.query)
            if params.get('list-type') == ['2']:
                listado = ET.Element('ListBucketResult')
                ET.SubElement(listado, 'IsTruncated').text = 'false'
                for ruta, (cuerpo, _, _) in objetos.items():
                    clave = ruta.split('/', 2)[2]
                    if clave.startswith(params['prefix'][0]):
                        obj = ET.SubElement(listado, 'Contents')
                        ET.SubElement(obj, 'Key').text = clave
                        ET.SubElement(obj, 'Size').text = str(len(cuerpo))
                xml = ET.tostring(listado, encoding='utf-8')
                self.send_response(200)
                self.send_header('Content-Length', str(len(xml)))
                self.end_headers()
                self.wfile.write(xml)
                return
            self.servir(True)

    _, _, identidad, origen, catalogo, destinatario = copia
    contenido = b'Archivo QQP simulado'
    digest = sha256(contenido).hexdigest()
    nombre = f'QQP_2026.{digest}.rar'
    carpeta = origen / nube.CARPETA_QQP
    carpeta.mkdir(parents=True)
    (carpeta / nombre).write_bytes(contenido)
    (carpeta / (nombre + '.json')).write_text(json.dumps({
        'estado': 'candidato_validado', 'archivo': nombre, 'sha256': digest,
        'bytes_descargados': len(contenido), 'miembros_csv': 12}), encoding='utf-8')
    (carpeta / 'no_publicable.rar.rechazado').write_bytes(b'RAR incompleto')
    archivo = tmp_path / 'respaldo_con_qqp.age'
    server = ThreadingHTTPServer(('127.0.0.1', 0), S3Local)
    hilo = Thread(target=server.serve_forever, daemon=True)
    hilo.start()
    monkeypatch.setattr(nube, 'ENDPOINT', f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setenv('SCONTO_BACKUP_BUCKET', 'copia-local')
    monkeypatch.setenv('SCONTO_BACKUP_ACCESS_KEY_ID', 'FICTICIO-PARA-PRUEBA')
    monkeypatch.setenv('SCONTO_BACKUP_SECRET_ACCESS_KEY', 'FICTICIO-PARA-PRUEBA')
    bucket, cliente = nube._conectar_s3()
    try:
        assert nube.enviar_qqp(origen, destinatario, bucket, cliente) == [nombre]
        qqp = nube.enviar_qqp(origen, destinatario, bucket, cliente)
        assert qqp == [nombre] and len(objetos) == 1
        nube.crear(origen, archivo, destinatario, catalogo=catalogo, qqp_externo=qqp)
        resultado = nube.enviar(archivo, bucket, cliente)
        objeto = objetos['/' + bucket + '/' + resultado['clave']]
        assert objeto[0] == archivo.read_bytes()
        assert objeto[2].startswith('AWS4-HMAC-SHA256')
        assert resultado['estado'] == 'objeto_confirmado'
        destino = tmp_path / 'segunda_ubicacion'
        verificacion = nube.recuperar(resultado['clave'], destino, identidad, bucket, cliente)
        comprobar_restauracion(destino)
        assert verificacion['archivos_qqp'] == 1
        assert (destino / nube.CARPETA_QQP / nombre).read_bytes() == contenido
        assert not (destino / nube.CARPETA_QQP / 'no_publicable.rar.rechazado').exists()
        with pytest.raises(ValueError, match='Clave'):
            nube.recuperar('../copia.age', tmp_path / 'ruta_invalida', identidad, bucket, cliente)
        assert len(objetos) == 2
        ruta_qqp = '/' + bucket + '/' + nube._clave_qqp(nombre)
        cuerpo, metadata, auth = objetos[ruta_qqp]
        objetos[ruta_qqp] = (bytes([cuerpo[0] ^ 1]) + cuerpo[1:], metadata, auth)
        fallo = tmp_path / 'recuperacion_qqp_alterada'
        with pytest.raises(ValueError, match='alterado'):
            nube.recuperar(resultado['clave'], fallo, identidad, bucket, cliente)
        assert not fallo.exists()
    finally:
        cliente.close()
        server.shutdown()
        server.server_close()
        hilo.join()


def test_cli_no_imprime_credenciales(monkeypatch, capsys):
    def error():
        raise RuntimeError('valor-privado-sintetico')
    monkeypatch.setattr(nube, '_conectar_s3', error)
    monkeypatch.setattr('sys.argv', ['respaldo_nube_v2', 'listar'])
    assert nube.main() == 1
    salida = capsys.readouterr()
    assert not salida.out
    assert json.loads(salida.err) == {'estado': 'error', 'tipo': 'RuntimeError'}
