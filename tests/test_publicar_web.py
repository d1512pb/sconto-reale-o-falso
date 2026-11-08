import json
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest
import pandas as pd

from sconto.consulta import evaluar_oferta
from sconto.publicar_web import construir


def test_javascript_coincide_con_consulta_python():
    if not shutil.which('node'):
        pytest.skip('Node no disponible para probar la consulta estática')
    ref = dict(serie_id='A', moneda='MXN', canal='en_linea', cobertura_base=True, base_cerrada=True,
               mediana_base=1000, p25_base=900, p75_base=1100, contexto='serie_vendedor')
    casos = []
    for contexto in ['minimo_multitienda', 'serie_vendedor']:
        for cobertura in [True, False]:
            for precio in [800, 1000, 1200]:
                casos.append(dict(ref={**ref, 'contexto': contexto, 'cobertura_base': cobertura}, precio=precio))
    modulo = (Path('web') / 'consulta.mjs').resolve().as_uri()
    codigo = f"import {{comparar}} from {json.dumps(modulo)}; let s=''; for await(const b of process.stdin)s+=b; console.log(JSON.stringify(JSON.parse(s).map(c=>comparar(c.ref,c.precio,2000,60,true))));"
    respuesta = subprocess.run(['node', '--input-type=module', '-e', codigo], input=json.dumps(casos), text=True, capture_output=True, check=True)
    for caso, js in zip(casos, json.loads(respuesta.stdout), strict=True):
        py = evaluar_oferta(caso['ref'], caso['precio'], 2000, 60, serie_oferta_id='A')
        assert js['estado'] == py['estado']
        assert js['diferencia'] == pytest.approx(py['diferencia_frente_referencia_pct']) if py['diferencia_frente_referencia_pct'] is not None else js['diferencia'] is None
        assert js['brecha'] == pytest.approx(py['brecha_consulta_pp']) if py['brecha_consulta_pp'] is not None else js['brecha'] is None


def test_sitio_solo_publica_precios_del_catalogo_y_conserva_faltantes(tmp_path):
    datos = Path('data/analitica')
    if not (datos / 'manifest.json').exists():
        pytest.skip('Necesita la entrega del ETL')
    resumen = construir(datos, tmp_path, Path('web'))
    snapshot = json.loads((tmp_path / 'snapshot.json').read_text(encoding='utf-8'))
    feed = json.loads((tmp_path / snapshot['archivo']).read_text(encoding='utf-8'))
    esperados = pd.read_parquet(datos / 'productos.parquet').query('en_catalogo_web').producto_canonico_id
    assert set(feed['detalles']) == set(esperados) == {p['producto_canonico_id'] for p in feed['productos']}
    assert resumen['productos'] == len(esperados)
    for pid in list(feed['detalles'])[:15]:
        descriptor = feed['detalles'][pid]
        contenido = (tmp_path / descriptor['archivo']).read_bytes()
        assert hashlib.sha256(contenido).hexdigest() == descriptor['sha256']
        ficha = json.loads(contenido)
        assert ficha['producto_canonico_id'] == pid
        ids = {serie['serie_id'] for serie in ficha['series']}
        assert all(p['serie_id'] in ids and p['precio_mediano'] > 0 for p in ficha['precios_diarios'])
        assert all(o['producto_canonico_id'] == pid for o in ficha['ofertas'])
    assert not list(tmp_path.glob('*.sqlite'))
    assert (tmp_path / 'snapshot.json').exists()
    assert feed['version'] == 'sconto-app-v2'
    assert feed['busqueda']['version'] == 'sconto-busqueda-v1'
    assert (tmp_path / 'manifest.webmanifest').exists()
    assert '__SCONTO_VERSION__' not in (tmp_path / 'sw.js').read_text(encoding='utf-8')
    assert (tmp_path / 'icons/icon-512.png').exists()
