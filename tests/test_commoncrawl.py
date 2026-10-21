"""Pruebas offline de Common Crawl: robots.txt, selección de crawls, lectura WARC por rango y corrida bloqueada."""
import io
import json
import urllib.robotparser
from pathlib import Path

import pandas as pd
from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

from sconto.cliente import USER_AGENT, NoPermitido
from sconto.esquema import CLAVE
from sconto.fuentes import commoncrawl as cc
from sconto.fuentes import wayback as wb
from sconto.parsers_archivo import parsear

FIX = Path(__file__).parent / 'fixtures' / 'commoncrawl'
FIX_WB = Path(__file__).parent / 'fixtures' / 'wayback'


def test_robots_de_common_crawl_prohibe_indice_y_datos():
    """robots.txt reales (16-oct-2026): el índice y los WARC están vetados a todo user-agent."""
    for host, archivo, url in [
            ('index', 'robots_index.commoncrawl.org.txt',
             'https://index.commoncrawl.org/CC-MAIN-2024-46-index?url=www.amazon.com.mx/dp/B0C29CL98P&output=json'),
            ('data', 'robots_data.commoncrawl.org.txt',
             'https://data.commoncrawl.org/crawl-data/CC-MAIN-2024-46/segments/x/warc/y.warc.gz')]:
        rp = urllib.robotparser.RobotFileParser()
        rp.parse((FIX / archivo).read_text().splitlines())
        assert not rp.can_fetch(USER_AGENT, url), host


def test_seleccion_de_crawls_sep_dic():
    info = json.loads((FIX / 'collinfo_formato.json').read_text())
    ids = [c['id'] for c in cc.seleccionar_crawls(info)]
    assert ids == ['CC-MAIN-2024-38', 'CC-MAIN-2024-46', 'CC-MAIN-2025-47']  # junio 2025 queda fuera


def _warc(html: bytes, url='https://www.amazon.com.mx/dp/B0C29CL98P/') -> bytes:
    buf = io.BytesIO()
    w = WARCWriter(buf, gzip=True)
    cab = StatusAndHeaders('200 OK', [('Content-Type', 'text/html; charset=UTF-8')], protocol='HTTP/1.1')
    w.write_record(w.create_warc_record(url, 'response', payload=io.BytesIO(html), http_headers=cab))
    return buf.getvalue()


def test_lectura_warc_y_parser_compartido():
    html = (FIX_WB / 'amazon_ficha_2024-11-01.html').read_bytes()
    cuerpo, estado = cc.carga_warc(_warc(html))
    assert estado == 200 and cuerpo == html
    r = parsear(cuerpo, 'https://www.amazon.com.mx/dp/B0C29CL98P/')
    assert (r['precio'], r['precio_anterior'], r['pct']) == (999.0, 1439.0, 31.0)


def test_adaptar_fila_y_seleccion():
    fila_cc = dict(urlkey='mx,com,amazon)/dp/b0c29cl98p', timestamp='20241105120000', mime='text/html', status='200',
                   url='https://www.amazon.com.mx/dp/B0C29CL98P', length='310000', offset='1234',
                   filename='crawl-data/CC-MAIN-2024-46/segments/1/warc/a.warc.gz', digest='X')
    snap = wb.seleccionar(dict(tipo='asin', id='B0C29CL98P'), [cc.a_fila_wayback(fila_cc, 'CC-MAIN-2024-46')])[0]
    assert snap['ventana'] == 'BF2024:previo' and snap['offset'] == '1234'
    r = parsear((FIX_WB / 'amazon_ficha_2024-11-01.html').read_bytes(), snap['original'])
    fila = cc.adaptar(wb.filas_producto(dict(tipo='asin', id='B0C29CL98P'), snap, r, 'x', 'h', '2026-10-16'), snap)
    cond = json.loads(fila['condiciones'])
    assert fila['fuente'] == 'commoncrawl' and fila['metodo'] == 'commoncrawl' and fila['crawl'] == 'CC-MAIN-2024-46'
    assert cond['warc_offset'] == '1234' and 'snapshot' not in cond and fila['fecha_precio'] == '2024-11-05'


class CCBloqueado:
    peticiones = 0

    def crawls(self):
        raise NoPermitido('https://index.commoncrawl.org/collinfo.json')


def test_backfill_bloqueado_por_robots(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, 'BRONZE', tmp_path)
    estados = []
    monkeypatch.setattr(cc, 'registrar_estado', lambda *a, **k: estados.append(a))
    prods = pd.DataFrame([dict(producto_canonico_id='P1', asins='B0C29CL98P', mlm_ids=None)])
    res = cc.backfill(prods, fecha='2026-10-16', cc=CCBloqueado())
    assert res['filas'] == 0 and 'collinfo' in res['bloqueado_robots']
    assert estados[-1][1] == 'bloqueado' and 'robots.txt' in estados[-1][3]


def test_escribir_sin_duplicados(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, 'BRONZE', tmp_path)
    monkeypatch.setattr('sconto.almacen.BRONZE', tmp_path)
    base = dict(fuente='commoncrawl', metodo='commoncrawl', canal='en_linea', id_externo='B0C29CL98P',
                tipo_id_externo='asin', fecha_precio='2024-11-05', vendedor_o_cadena='Tecnolife', precio=999.0,
                moneda='MXN', timestamp_cc='20241105120000')
    assert cc.escribir([base, dict(base, timestamp_cc='20241105130000', precio=989.0)], '2026-10-16') == 1
    df = pd.read_parquet(tmp_path / 'commoncrawl' / '2026-10-16.parquet')
    assert len(df) == 1 and df.precio.iloc[0] == 989.0 and not df.duplicated(CLAVE).any()
    assert cc.escribir([base], '2026-10-17') == 0  # ya existe en otra partición
