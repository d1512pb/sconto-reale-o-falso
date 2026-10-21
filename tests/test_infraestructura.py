from datetime import datetime, timezone

import pandas as pd
import pytest
import requests

from sconto import almacen
from sconto.cliente import Bloqueado, Cliente, NoPermitido


def respuesta(url, codigo=200, contenido=b'', headers=None):
    resultado = requests.Response()
    resultado.status_code = codigo
    resultado.url = url
    resultado._content = contenido
    resultado.headers.update(headers or {})
    return resultado


def cliente_simulado(monkeypatch, respuestas):
    cliente = Cliente(pausa=(0, 0), reintentos=0)
    llamadas = []

    def obtener(url, **kwargs):
        llamadas.append(url)
        resultado = respuestas[url]
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(cliente.sesion, 'get', obtener)
    return cliente, llamadas


@pytest.mark.parametrize('codigo', [401, 403, 429, 500, 503])
def test_robots_no_disponible_nunca_autoriza(monkeypatch, codigo):
    cliente, llamadas = cliente_simulado(monkeypatch, {
        'https://tienda.test/robots.txt': respuesta('https://tienda.test/robots.txt', codigo)})
    with pytest.raises(NoPermitido):
        cliente.get('https://tienda.test/producto')
    assert len(llamadas) == 1


def test_robots_error_red_no_autoriza(monkeypatch):
    cliente, llamadas = cliente_simulado(monkeypatch, {
        'https://tienda.test/robots.txt': requests.Timeout()})
    with pytest.raises(NoPermitido):
        cliente.get('https://tienda.test/producto')
    assert len(llamadas) == 1


def test_redireccion_verifica_robots_de_destino(monkeypatch):
    cliente, llamadas = cliente_simulado(monkeypatch, {
        'https://tienda.test/robots.txt': respuesta('https://tienda.test/robots.txt', contenido=b'User-agent: *\nDisallow: /privado'),
        'https://tienda.test/producto': respuesta('https://tienda.test/producto', 302, headers={'Location': '/privado'})})
    with pytest.raises(NoPermitido):
        cliente.get('https://tienda.test/producto')
    assert 'https://tienda.test/privado' not in llamadas


def test_captcha_503_no_se_reintenta(monkeypatch):
    cliente, llamadas = cliente_simulado(monkeypatch, {
        'https://tienda.test/robots.txt': respuesta('https://tienda.test/robots.txt', 404),
        'https://tienda.test/producto': respuesta('https://tienda.test/producto', 503, b'Robot check', {'content-type': 'text/html'})})
    cliente.reintentos = 3
    with pytest.raises(Bloqueado) as bloqueo:
        cliente.get('https://tienda.test/producto')
    assert bloqueo.value.respuesta.status_code == 503
    assert len(llamadas) == 2


def test_bronze_vacio_no_borra_captura_previa(monkeypatch, tmp_path):
    monkeypatch.setattr(almacen, 'BRONZE', tmp_path)
    primero = pd.DataFrame({'id': ['A'], 'precio': [100.]})
    ruta = almacen.escribir_bronze('prueba', primero, '2026-10-20', clave=['id'])
    almacen.escribir_bronze('prueba', pd.DataFrame(), '2026-10-20', clave=['id'])
    pd.testing.assert_frame_equal(pd.read_parquet(ruta), primero)
    almacen.escribir_bronze('prueba', primero, '2026-10-20', clave=['id'])
    assert len(pd.read_parquet(ruta)) == 1


def test_fecha_mexico_no_depende_del_host(monkeypatch):
    class Reloj:
        @classmethod
        def now(cls, zona):
            return datetime(2026, 10, 21, 2, tzinfo=timezone.utc).astimezone(zona)

    monkeypatch.setattr(almacen, 'datetime', Reloj)
    assert almacen.hoy() == '2026-10-20'
