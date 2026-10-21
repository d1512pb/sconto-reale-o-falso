"""Pruebas offline de Wayback (parsers de HTML histórico, selección de capturas y corrida con Wayback falso)."""
import json
from pathlib import Path

import pandas as pd

from sconto import parsers_archivo as pa
from sconto.esquema import CLAVE, COLUMNAS
from sconto.fuentes import wayback as wb

FIX = Path(__file__).parent / 'fixtures' / 'wayback'


def leer(nombre):
    return (FIX / nombre).read_bytes()


def test_numeros_y_porcentajes():
    assert pa.a_numero('$1,439.00') == 1439.0
    assert pa.a_numero('1.439,50') == 1439.5
    assert pa.a_numero('$ 12,999') == 12999.0
    assert pa.a_numero('$999.00 con un ahorro') == 999.0
    assert pa.a_numero('0') is None and pa.a_numero(None) is None
    assert pa.a_pct('-31%') == 31.0 and pa.a_pct('47% OFF') == 47.0 and pa.a_pct('sin dato') is None


def test_amazon_ficha_con_tachado():
    r = pa.parsear_amazon(leer('amazon_ficha_2024-11-01.html'))
    assert r['estado'] == 'ok' and r['asin'] == 'B0C29CL98P'
    assert r['precio'] == 999.0 and r['precio_anterior'] == 1439.0 and r['pct'] == 31.0
    assert r['etiqueta_anterior'] == 'Precio de lista'
    assert r['vendido_por'] == 'Tecnolife' and r['enviado_por'] == 'Amazon' and r['marca'] == 'Sony'


def test_amazon_tabla_antigua_y_captcha():
    r = pa.parsear_amazon(leer('amazon_tabla_antigua.html'))
    assert r['estado'] == 'ok' and r['precio'] == 219.6 and r['asin'] == 'B09BVJ6K5K'
    assert pa.parsear_amazon(leer('amazon_captcha.html'))['estado'] == 'captcha'


def test_mercadolibre_estado_preinyectado():
    r = pa.parsear_mercadolibre(leer('ml_catalogo_2024-12-16.html'))
    assert r['estado'] == 'ok' and r['mlm'] == 'MLM18593745'
    assert (r['precio'], r['precio_anterior'], r['pct']) == (661.97, 1249.0, 47.0)
    assert r['vendido_por'] == 'Radioshack' and r['tienda_oficial'] is True and r['cuotas'] == 24
    r = pa.parsear_mercadolibre(leer('ml_catalogo_2025-04-28.html'))
    assert r['precio'] == 711.0 and r.get('precio_anterior') is None and r['vendido_por'] == 'ELECTROMARTZMXF'


def test_tarjetas_jsonld_y_html():
    html = """<html><head><script type="application/ld+json">{"@type":"ItemList","itemListElement":[
      {"@type":"ListItem","item":{"@type":"Product","name":"Pantalla LG 65UR7800PSB","url":"/p/123",
       "offers":{"@type":"Offer","price":"8999.00","priceCurrency":"MXN"}}}]}</script></head><body></body></html>"""
    r = pa.parsear_tarjetas(html, 'https://www.tienda.mx/buen-fin')
    assert r['estado'] == 'ok' and r['tarjetas'][0]['precio'] == 8999.0
    assert r['tarjetas'][0]['url'] == 'https://www.tienda.mx/p/123'
    html = """<html><body><ul><li class="card"><a href="/tv-55"><h3>Smart TV 55 pulgadas</h3></a>
      <span class="price-old">$12,999.00</span><span class="price">$9,999.00</span><span>-23%</span></li></ul></body></html>"""
    t = pa.parsear_tarjetas(html, 'https://www.tienda.mx/')['tarjetas'][0]
    assert (t['nombre'], t['precio'], t['precio_anterior'], t['pct']) == ('Smart TV 55 pulgadas', 9999.0, 12999.0, 23.0)


def test_tipo_pagina():
    assert pa.tipo_pagina('https://www.amazon.com.mx/dp/B0C29CL98P/') == 'amazon'
    assert pa.tipo_pagina('https://www.mercadolibre.com.mx/x/p/MLM18593745') == 'mercadolibre'
    assert pa.tipo_pagina('https://articulo.mercadolibre.com.mx/MLM-123456789-tv-_JM') == 'mercadolibre'
    assert pa.tipo_pagina('https://www.sanborns.com.mx/c/buen-fin/') == 'tienda'


def _filas_cdx():
    datos = json.loads(leer('cdx_B0C29CL98P.json'))
    return [dict(zip(datos[0], f)) for f in datos[1:]]


def test_seleccion_descarta_basura_y_captchas():
    obj = dict(tipo='asin', id='B0C29CL98P')
    sel = wb.seleccionar(obj, _filas_cdx())
    # quedan sólo fichas reales (sin '"+t.src+"', sin .jpg y sin capturas de 2 KB = CAPTCHA)
    assert [s['timestamp'] for s in sel] == ['20241101234641']
    assert sel[0]['ventana'] == 'BF2024:previo'
    # `length` negativo (desbordado en el CDX real de B0CPL6NDWH) = tamaño desconocido: se conserva
    rara = dict(_filas_cdx()[1], timestamp='20241116080000', original='https://www.amazon.com.mx/dp/B0C29CL98P',
                length='-6134879456')
    assert [s['ventana'] for s in wb.seleccionar(obj, [rara])] == ['BF2024:evento']
    assert wb.captura_valida(dict(tipo='mlm', id='MLM18593745'),
                             dict(original='https://www.mercadolibre.com.mx/a-b/p/MLM18593745#reco'))
    assert not wb.captura_valida(dict(tipo='mlm', id='MLM18593745'),
                                 dict(original='https://www.mercadolibre.com.mx/a-b/p/MLM18593745/s'))


def test_ventanas_bf():
    assert wb.ventana_de_fecha('2024-11-16') == 'BF2024:evento'
    assert wb.ventana_de_fecha('2024-09-16') == 'BF2024:base'
    assert wb.ventana_de_fecha('2025-11-12') == 'BF2025:previo'
    assert wb.ventana_de_fecha('2025-06-01') is None


def test_objetivos_y_consultas():
    prods = pd.DataFrame([dict(producto_canonico_id='P1', asins='B0C29CL98P;B09B2SBHQK', mlm_ids='MLM18593745')])
    objs = wb.objetivos_producto(prods, ids=['MLM-123456789'], nombres={'MLM18593745': 'Amazon Fire TV Stick 3.ª'})
    assert [(o['tipo'], o['id']) for o in objs] == [('asin', 'B0C29CL98P'), ('asin', 'B09B2SBHQK'),
                                                    ('mlm', 'MLM18593745'), ('mlm_item', 'MLM123456789')]
    cons = wb.consultas_de(objs[2])
    assert cons[1]['url'] == 'mercadolibre.com.mx/amazon-fire-tv' and cons[1]['filtros'] == ('urlkey:.*/p/mlm18593745.*',)
    assert wb.consultas_de(objs[3])[0]['url'] == 'articulo.mercadolibre.com.mx/MLM-123456789'


def test_diario_pide_solo_capturas_recientes(monkeypatch):
    vistos = {}
    monkeypatch.setattr(wb, 'backfill', lambda **kw: vistos.update(kw) or {})
    wb.diario(pd.DataFrame([dict(producto_canonico_id='P1', asins='B0C29CL98P')]), fecha='2026-11-20', dias=10)
    assert (vistos['desde'], vistos['hasta'], vistos['incluir_tiendas']) == ('20261110', '20261120', False)


class WaybackFalso:
    bloqueos_seguidos = 0
    peticiones = 0

    def cdx(self, url, match='prefix', filtros=(), **kw):
        return _filas_cdx() if 'b0c29cl98p' in url.lower() else []

    def descargar(self, ts, original):
        return leer('amazon_ficha_2024-11-01.html'), f'data/raw/wayback/{ts}.html.gz', 'h' * 64, 'cache'


def test_backfill_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(wb, 'BRONZE', tmp_path / 'bronze')
    monkeypatch.setattr(wb, 'CACHE_WB', tmp_path / 'cache')
    monkeypatch.setattr('sconto.almacen.BRONZE', tmp_path / 'bronze')
    estados = []
    monkeypatch.setattr(wb, 'registrar_estado', lambda *a, **k: estados.append(a))
    prods = pd.DataFrame([dict(producto_canonico_id='P1', asins='B0C29CL98P', mlm_ids=None)])
    res = wb.backfill(productos=prods, incluir_tiendas=False, fecha='2026-10-16', wb=WaybackFalso())
    assert res['snapshots'] == 1 and res['con_precio'] == 1 and res['con_tachado'] == 1 and res['filas'] == 1
    df = pd.read_parquet(tmp_path / 'bronze' / 'wayback' / '2026-10-16.parquet')
    assert list(df.columns[:len(COLUMNAS)]) == COLUMNAS and not df.duplicated(CLAVE).any()
    f = df.iloc[0]
    assert (f.metodo, f.canal, f.fecha_precio, f.tipo_id_externo, f.moneda) == ('wayback', 'en_linea', '2024-11-01',
                                                                                 'asin', 'MXN')
    assert f.precio == 999.0 and f.precio_anterior_anunciado == 1439.0 and f.pct_descuento_anunciado == 31.0
    assert 'web.archive.org/web/20241101234641id_/' in json.loads(f.condiciones)['snapshot']
    assert estados[-1][1] == 'ok'
    # re-ejecutar otro día no duplica claves entre particiones
    res2 = wb.backfill(productos=prods, incluir_tiendas=False, fecha='2026-10-17', wb=WaybackFalso())
    assert res2['filas'] == 0 and not (tmp_path / 'bronze' / 'wayback' / '2026-10-17.parquet').exists()
