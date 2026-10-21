from pathlib import Path

from sconto.fuentes.tiendas import parsear_ficha

URL = 'https://www.liverpool.com.mx/tienda/pdp/barra-de-sonido-ht-s20r/1097521774?skuid=1097521774'
FIXTURE = Path(__file__).parent / 'fixtures/tiendas/liverpool_configurador_real_recortado.html'


def test_configurador_real_no_usa_carrusel():
    resultado = parsear_ficha(FIXTURE.read_bytes(), URL)
    assert resultado['precio'] == 3999
    assert resultado['precio_anterior'] == 6699
    assert resultado['pct'] is None
    assert resultado['vendedor'] is None
    assert 'contexto' in resultado['evidencia']


def test_configurador_otro_sku_no_se_usa():
    assert parsear_ficha(FIXTURE.read_bytes(), URL.replace('1097521774', '1000000000')) is None
