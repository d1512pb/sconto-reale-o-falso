"""Tests OFFLINE: datos y respuestas sintéticos, NO prueban precios ni cobertura real."""
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from sconto import almacen
from sconto.cliente import Bloqueado
from sconto.esquema import CLAVE, COLUMNAS
from sconto.fuentes import tiendas as tiendas

FIX = Path(__file__).parent / 'fixtures' / 'tiendas'
LIVERPOOL = 'https://www.liverpool.com.mx/tienda/pdp/prueba/100'
SEARS = 'https://www.sears.com.mx/producto/300/prueba/'
FECHA = '2026-10-20'


def _fixture(nombre):
    return (FIX / nombre).read_bytes()


def _producto(url=LIVERPOOL, **cambios):
    producto = {'@type': 'Product', 'url': url, 'name': 'Prueba sintética',
                'offers': {'@type': 'Offer', 'price': '799.00', 'priceCurrency': 'MXN',
                           'seller': {'name': 'Vendedor ficticio'}, 'availability': 'https://schema.org/InStock'}}
    producto.update(cambios)
    return producto


def _ld(producto):
    return '<script type="application/ld+json">' + json.dumps(producto) + '</script>'


def _lista(ambas=True):
    filas = [dict(producto_canonico_id='SINTETICO-L', tienda='liverpool', url=LIVERPOOL,
                  habilitado='1', confianza='alta')]
    if ambas:
        filas.append(dict(producto_canonico_id='SINTETICO-S', tienda='sears', url=SEARS,
                          habilitado='sí', confianza='verificado'))
    return pd.DataFrame(filas)


def test_liverpool_jsonld_y_markup_explicitamente_anunciados():
    ficha = tiendas.parsear_ficha(_fixture('sintetica_liverpool.html'), LIVERPOOL)
    assert (ficha['precio'], ficha['precio_anterior'], ficha['pct']) == (799, 999, 20)
    assert ficha['vendedor'] == 'Vendedor sintético'
    assert ficha['disponibilidad'] == 'https://schema.org/InStock'


def test_sears_estado_publico_principal_no_recomendaciones():
    ficha = tiendas.parsear_ficha(_fixture('sintetica_sears.html'), SEARS)
    assert (ficha['precio'], ficha['precio_anterior'], ficha['pct']) == (650, 1000, 35)
    assert ficha['vendedor'] == 'Comercio sintético' and ficha['disponibilidad'] == 'OutOfStock'


def test_estado_no_visible_no_anuncia_tachado_ni_porcentaje():
    html = _fixture('sintetica_sears.html').decode().replace('"showListPrice":true', '"showListPrice":false')
    html = html.replace('"showDiscountPercentage":true', '"showDiscountPercentage":false')
    ficha = tiendas.parsear_ficha(html, SEARS)
    assert ficha['precio_anterior'] is None and ficha['pct'] is None


@pytest.mark.parametrize('oferta', [
    {'@type': 'AggregateOffer', 'lowPrice': 799, 'highPrice': 999, 'priceCurrency': 'MXN'},
    {'@type': 'Offer', 'lowPrice': 799, 'highPrice': 999, 'priceCurrency': 'MXN'},
    {'@type': 'Offer', 'price': 'NaN', 'priceCurrency': 'MXN'},
    {'@type': 'Offer', 'price': 0, 'priceCurrency': 'MXN'},
    {'@type': 'Offer', 'price': -799, 'priceCurrency': 'MXN'},
    {'@type': 'Offer', 'price': 'desde $799 a $999', 'priceCurrency': 'MXN'},
    {'@type': 'Offer', 'price': 799},
])
def test_sin_precio_o_moneda_inequivocos_no_emite(oferta):
    assert tiendas.parsear_ficha(_ld(_producto(offers=oferta)), LIVERPOOL) is None


def test_highprice_no_es_precio_tachado_y_no_se_calcula_pct():
    producto = _producto()
    producto['offers'].update(lowPrice=1, highPrice=99999)
    ficha = tiendas.parsear_ficha(_ld(producto), LIVERPOOL)
    assert ficha['precio'] == 799 and ficha['precio_anterior'] is None and ficha['pct'] is None
    producto['offers']['priceSpecification'] = {'@type': 'UnitPriceSpecification',
                                               'priceType': 'https://schema.org/ListPrice', 'price': 999,
                                               'priceCurrency': 'MXN'}
    ficha = tiendas.parsear_ficha(_ld(producto), LIVERPOOL)
    assert ficha['precio_anterior'] == 999 and ficha['pct'] is None


def test_no_suplanta_vendedor_por_nombre_tienda():
    producto = _producto()
    del producto['offers']['seller']
    del producto['offers']['availability']
    ficha = tiendas.parsear_ficha(_ld(producto), LIVERPOOL)
    assert ficha['vendedor'] is None and ficha['disponibilidad'] is None


def test_carousel_itemlist_otra_identidad_y_varios_vendedores_no_se_eligen():
    ajeno = _producto(url=SEARS)
    assert tiendas.parsear_ficha(_ld(ajeno), LIVERPOOL) is None
    lista = {'@type': 'ItemList', 'itemListElement': [_producto()]}
    assert tiendas.parsear_ficha(_ld(lista), LIVERPOOL) is None
    producto = _producto()
    producto['offers'] = [producto['offers'], dict(producto['offers'], price=1, seller={'name': 'Otro'})]
    assert tiendas.parsear_ficha(_ld(producto), LIVERPOOL) is None
    assert tiendas.parsear_ficha('<aside class="carousel">' + _ld(_producto()) + '</aside>', LIVERPOOL) is None


def test_productos_principales_ambiguos_no_se_mezclan():
    assert tiendas.parsear_ficha(_ld([_producto(), _producto(name='Otro producto')]), LIVERPOOL) is None


def test_markup_solo_del_producto_principal_y_no_oculto():
    html = _fixture('sintetica_liverpool.html').decode()
    inicio = html.index('<script')
    fin = html.index('</script>') + len('</script>')
    html = html[:inicio] + html[fin:]
    ficha = tiendas.parsear_ficha(html, LIVERPOOL)
    assert (ficha['precio'], ficha['precio_anterior'], ficha['pct']) == (799, 999, 20)
    html = html.replace('<main itemscope', '<main hidden itemscope')
    assert tiendas.parsear_ficha(html, LIVERPOOL) is None


@pytest.mark.parametrize('url', [
    'http://www.liverpool.com.mx/tienda/pdp/prueba/100',
    'https://www.liverpool.com.mx.ejemplo.org/tienda/pdp/prueba/100',
    'https://sub.liverpool.com.mx/tienda/pdp/prueba/100',
    'https://www.sears.com/tienda/pdp/prueba/100',
    'https://www.sears.com.mx:444/producto/300/',
    'https://usuario:clave@www.sears.com.mx/producto/300/',
    'https://www.sears.com.mx/mi-cuenta/',
    'https://www.liverpool.com.mx/tienda/categorias',
    'https://www.sears.com.mx/producto/300/%2e%2e/',
    'https://www.sears.com.mx/producto/300/%2fmi-cuenta/',
    'https://www.sears.com.mx/producto/300/%5cmi-cuenta/',
    'https://www.sears.com.mx/producto/300/%0a/',
])
def test_allowlist_rechaza_urls_no_publicas_de_ficha(url):
    with pytest.raises(ValueError):
        tiendas.validar_url(url)


def test_allowlist_valida_tienda_y_quita_fragmento():
    assert tiendas.validar_url(SEARS + '#x', 'sears') == SEARS
    assert tiendas.validar_url(SEARS.replace('.mx/', '.mx:443/')) == SEARS
    with pytest.raises(ValueError):
        tiendas.validar_url(SEARS, 'liverpool')


def test_robots_comodines_y_grupo_propio_conservadores():
    texto = _fixture('sintetico_robots.txt').decode()
    assert tiendas.permitido(texto, SEARS)
    assert not tiendas.permitido(texto, 'https://www.sears.com.mx/producto/999/oculto/')
    assert not tiendas.permitido('User-agent: *\nDisallow: /producto/*/prueba/$', SEARS)
    propio = 'User-agent: *\nAllow: /\nUser-agent: ScontoRealeOFalso\nDisallow: /producto/'
    assert not tiendas.permitido(propio, SEARS)


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    for modulo in (almacen, tiendas):
        monkeypatch.setattr(modulo, 'RAIZ', tmp_path)
        monkeypatch.setattr(modulo, 'RAW', tmp_path / 'raw')
    monkeypatch.setattr(almacen, 'BRONZE', tmp_path / 'bronze')
    monkeypatch.setattr(almacen, 'ESTADO_DIR', tmp_path / 'estado')
    monkeypatch.setattr(almacen, 'ESTADO_FUENTES', tmp_path / 'estado_fuentes.csv')
    monkeypatch.setattr(tiendas, 'CONFIG', tmp_path / 'config')
    (tmp_path / 'config').mkdir()
    _lista().iloc[:0].to_csv(tmp_path / 'config' / 'tiendas_objetivo.csv', index=False)
    return tmp_path


class ClienteSintetico:
    """Transporte falso: ninguna petición sale de memoria ni de fixtures sintéticas."""
    def __init__(self, respuestas=None):
        self.respuestas = respuestas or {}
        self.pedidas = []
        self.respetar_robots = True
        self._robots = {}
        self.cerrado = False
        self.sesion = SimpleNamespace(close=self.cerrar)

    def cerrar(self):
        self.cerrado = True

    def get(self, url, **kwargs):
        assert kwargs['allow_redirects'] is False
        self.pedidas.append(url)
        defecto = _fixture('sintetico_robots.txt') if url.endswith('/robots.txt') else _fixture(
            'sintetica_liverpool.html' if 'liverpool' in url else 'sintetica_sears.html')
        respuesta = self.respuestas.get(url, (200, defecto))
        if isinstance(respuesta, Exception):
            raise respuesta
        http, contenido = respuesta
        respuesta = SimpleNamespace(status_code=http, content=contenido, url=url)
        for hook in [kwargs['hooks']['response']]:
            hook(respuesta)
        if http in (403, 429, 503):
            raise Bloqueado(f'HTTP {http}', respuesta)
        return respuesta


def _instalar(monkeypatch, cliente):
    def construir(**kwargs):
        assert kwargs['reintentos'] == 0
        return cliente
    monkeypatch.setattr(tiendas, 'Cliente', construir)


def test_diario_esquema_crudos_estados_idempotencia_y_cero_red_en_repeticion(aislado, monkeypatch):
    cliente = ClienteSintetico()
    _instalar(monkeypatch, cliente)
    resultado = tiendas.diario(_lista(), FECHA)
    assert resultado['estado'] == 'ok' and resultado['filas'] == 2
    assert len(resultado['robots']) == 2 and len(cliente.pedidas) == 4 and cliente.cerrado
    dataframe = pd.read_parquet(aislado / 'bronze' / 'tiendas' / (FECHA + '.parquet'))
    assert list(dataframe.columns) == COLUMNAS
    assert not dataframe.duplicated(CLAVE).any()
    assert set(dataframe.producto_canonico_id) == {'SINTETICO-L', 'SINTETICO-S'}
    assert set(dataframe.plataforma) == {'liverpool', 'sears'}
    for fila in dataframe.to_dict('records'):
        contenido = gzip.decompress((aislado / fila['ruta_raw']).read_bytes())
        assert almacen.sha256_bytes(contenido) == fila['hash_raw']
    segunda = tiendas._correr(_lista(), FECHA, sin_red=True)
    assert segunda['estado'] == 'ok' and len(cliente.pedidas) == 4
    assert len(pd.read_parquet(aislado / 'bronze' / 'tiendas' / (FECHA + '.parquet'))) == 2
    estados = pd.read_csv(aislado / 'estado_fuentes.csv')
    assert len(estados) == 1 and estados.estado.iloc[0] == 'ok'


@pytest.mark.parametrize('respuesta', [
    (403, b'Forbidden sintetico'), (429, b'Too many requests sintetico'),
    (503, b'Unavailable sintetico'), (200, _fixture('sintetico_bloqueo.html')),
    (302, b'Redirect sintetico'), (401, b'Login sintetico'),
])
def test_primer_bloqueo_detiene_todas_las_urls_y_todo_reintento_del_dia(aislado, monkeypatch, respuesta):
    cliente = ClienteSintetico({LIVERPOOL: respuesta})
    _instalar(monkeypatch, cliente)
    primera = tiendas.diario(_lista(), FECHA)
    assert primera['estado'] == 'bloqueado' and primera['filas'] == 0
    assert SEARS not in cliente.pedidas and len(cliente.pedidas) == 2
    assert list((aislado / 'raw' / 'tiendas' / FECHA).glob('*.body.gz'))
    segunda = tiendas.diario(_lista(), FECHA)
    assert segunda['estado'] == 'bloqueado' and len(cliente.pedidas) == 2


def test_conserva_filas_previas_al_bloqueo(aislado, monkeypatch):
    cliente = ClienteSintetico({SEARS: (403, b'Forbidden sintetico')})
    _instalar(monkeypatch, cliente)
    resultado = tiendas.diario(_lista(), FECHA)
    assert resultado['estado'] == 'bloqueado' and resultado['filas'] == 1
    assert len(pd.read_parquet(aislado / 'bronze' / 'tiendas' / (FECHA + '.parquet'))) == 1


@pytest.mark.parametrize('respuesta', [(500, b'error'), (200, b'<html>error</html>'),
                                     requests.ConnectionError('Sin red sintetico'), (404, b'no existe')])
def test_robots_no_verificable_impide_solicitar_ficha(aislado, monkeypatch, respuesta):
    robots_url = 'https://www.liverpool.com.mx/robots.txt'
    cliente = ClienteSintetico({robots_url: respuesta})
    _instalar(monkeypatch, cliente)
    resultado = tiendas.diario(_lista(ambas=False), FECHA)
    assert resultado['estado'] == 'parcial' and resultado['filas'] == 0
    assert cliente.pedidas == [robots_url] and resultado['incidencias']


def test_robots_disallow_detiene_la_lista(aislado, monkeypatch):
    cliente = ClienteSintetico({'https://www.liverpool.com.mx/robots.txt':
                              (200, b'User-agent: *\nDisallow: /tienda/*')})
    _instalar(monkeypatch, cliente)
    resultado = tiendas.diario(_lista(), FECHA)
    assert resultado['estado'] == 'bloqueado' and len(cliente.pedidas) == 1


@pytest.mark.parametrize('cambios', [dict(habilitado='0'), dict(confianza='pendiente'),
                                  dict(url=''), dict(url=SEARS), dict(producto_canonico_id='')])
def test_objetivos_no_habilitados_o_no_confiables_no_salen_a_red(aislado, monkeypatch, cambios):
    lista = _lista(ambas=False)
    for clave, valor in cambios.items():
        lista[clave] = valor
    monkeypatch.setattr(tiendas, 'Cliente', lambda **kwargs: pytest.fail('No debe crear cliente'))
    resultado = tiendas.diario(lista, FECHA)
    assert resultado['estado'] == 'parcial' and resultado['filas'] == 0
    assert 'no integrado' in resultado['motivo']


def test_productos_canonicos_sin_urls_y_plantilla_vacia_son_parciales(aislado, monkeypatch):
    monkeypatch.setattr(tiendas, 'Cliente', lambda **kwargs: pytest.fail('No debe crear cliente'))
    resultado = tiendas.diario(pd.DataFrame([dict(producto_canonico_id='SINTETICO')]), FECHA)
    assert resultado['estado'] == 'parcial' and resultado['objetivos'] == 0
    assert all('no integrado' in resumen['motivo'] for resumen in resultado['tiendas'].values())


def test_solo_se_exige_la_lista_de_tiendas_habilitadas(aislado, monkeypatch):
    _instalar(monkeypatch, ClienteSintetico())
    resultado = tiendas.diario(_lista(ambas=False), FECHA)
    assert resultado['estado'] == 'ok' and resultado['filas'] == 1
    assert resultado['tiendas']['liverpool']['estado'] == 'ok'
    assert 'no integrado' in resultado['tiendas']['sears']['motivo']


def test_sin_red_sin_cache_y_max_cero_no_crean_cliente(aislado, monkeypatch):
    monkeypatch.setattr(tiendas, 'Cliente', lambda **kwargs: pytest.fail('No debe crear cliente'))
    assert tiendas._correr(_lista(), FECHA, sin_red=True)['estado'] == 'parcial'
    assert tiendas._correr(_lista(), FECHA, maximo=0)['objetivos'] == 0


def test_max_limita_peticiones_y_no_declara_cobertura_total(aislado, monkeypatch):
    cliente = ClienteSintetico()
    _instalar(monkeypatch, cliente)
    resultado = tiendas._correr(_lista(), FECHA, maximo=1)
    assert resultado['estado'] == 'parcial' and resultado['filas'] == 1
    assert SEARS not in cliente.pedidas


def test_csv_de_mapeo_se_filtra_por_ids_canonicos(aislado):
    _lista().to_csv(aislado / 'config' / 'tiendas_objetivo.csv', index=False)
    lista = tiendas._objetivos(pd.DataFrame([dict(producto_canonico_id='SINTETICO-S')]))
    assert lista.url.tolist() == [SEARS]


def test_url_duplicada_conflictiva_no_se_consulta(aislado, monkeypatch):
    lista = pd.concat([_lista(False), _lista(False).assign(producto_canonico_id='OTRO-SINTETICO')])
    monkeypatch.setattr(tiendas, 'Cliente', lambda **kwargs: pytest.fail('No debe crear cliente'))
    resultado = tiendas.diario(lista, FECHA)
    assert resultado['estado'] == 'parcial' and resultado['objetivos'] == 0


def test_cache_http_error_no_se_reinterpreta_como_exito(aislado, monkeypatch):
    cliente = ClienteSintetico({LIVERPOOL: (404, _fixture('sintetica_liverpool.html'))})
    _instalar(monkeypatch, cliente)
    primera = tiendas.diario(_lista(False), FECHA)
    segunda = tiendas._correr(_lista(False), FECHA, sin_red=True)
    assert primera['filas'] == segunda['filas'] == 0
    assert primera['estado'] == segunda['estado'] == 'parcial'


def test_cli_help_max_sin_red(aislado, monkeypatch, capsys):
    with pytest.raises(SystemExit) as salida:
        tiendas.main(['--help'])
    assert salida.value.code == 0
    assert '--sin-red' in capsys.readouterr().out
    _lista().to_csv(aislado / 'config' / 'tiendas_objetivo.csv', index=False)
    monkeypatch.setattr(tiendas, 'Cliente', lambda **kwargs: pytest.fail('No debe crear cliente'))
    assert tiendas.main(['--sin-red', '--max', '1', '--fecha', FECHA]) == 1
    resultado = json.loads(capsys.readouterr().out)
    assert resultado['objetivos'] == 1 and resultado['estado'] == 'parcial'
    with pytest.raises(SystemExit) as salida:
        tiendas.main(['--max', '-1'])
    assert salida.value.code == 2


@pytest.mark.parametrize('atributos', ['id="carousel-principal"', 'class="related"',
                                     'hidden', 'style="display:none"'])
def test_jsonld_en_contextos_secundarios_u_ocultos_no_emite(atributos):
    assert tiendas.parsear_ficha('<aside ' + atributos + '>' + _ld(_producto()) + '</aside>', LIVERPOOL) is None


def test_descuentos_no_se_mezclan_entre_vendedores():
    html = _fixture('sintetica_liverpool.html').decode()
    html = html.replace('<meta itemprop="price"', '<span itemprop="seller">Otro vendedor</span><meta itemprop="price"')
    ficha = tiendas.parsear_ficha(html, LIVERPOOL)
    assert ficha['vendedor'] == 'Vendedor sintético'
    assert ficha['precio_anterior'] is None and ficha['pct'] is None


def test_porcentaje_condicional_no_se_toma_como_descuento_del_precio():
    html = _fixture('sintetica_liverpool.html').decode().replace('-20%', '20% adicional con banco')
    assert tiendas.parsear_ficha(html, LIVERPOOL)['pct'] is None


def test_listprice_contradictorio_no_se_anuncia():
    producto = _producto()
    producto['offers']['priceSpecification'] = [
        {'priceType': 'https://schema.org/ListPrice', 'price': precio} for precio in (999, 1299)]
    assert tiendas.parsear_ficha(_ld(producto), LIVERPOOL)['precio_anterior'] is None


def test_cliente_real_no_sigue_redirect_aunque_su_get_intente_hacerlo(aislado, monkeypatch):
    cliente = tiendas.Cliente(pausa=(0, 0), reintentos=0, detectar_captcha=False)
    pedidas = []

    def get(url, **kwargs):
        pedidas.append(url)
        respuesta = requests.Response()
        respuesta.url = url
        if url.endswith('/robots.txt'):
            respuesta.status_code = 200
            respuesta._content = _fixture('sintetico_robots.txt')
        else:
            respuesta.status_code = 302
            respuesta.headers['Location'] = '/tienda/pdp/otro/200'
            respuesta._content = b'Redirect sintetico'
        kwargs['hooks']['response'](respuesta)
        return respuesta

    monkeypatch.setattr(cliente.sesion, 'get', get)
    _instalar(monkeypatch, cliente)
    resultado = tiendas.diario(_lista(), FECHA)
    assert resultado['estado'] == 'bloqueado'
    assert pedidas == ['https://www.liverpool.com.mx/robots.txt', LIVERPOOL]
    crudos = list((aislado / 'raw' / 'tiendas' / FECHA).glob('*.body.gz'))
    assert any(gzip.decompress(ruta.read_bytes()) == b'Redirect sintetico' for ruta in crudos)
