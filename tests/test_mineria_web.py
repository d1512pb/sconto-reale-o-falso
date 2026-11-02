import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import pytest

from sconto.consulta import evaluar_oferta
from sconto.mart import guardar_sqlite, preparar_tablas
from sconto.mineria import modelar, VARIABLES
from sconto.web import leer, verificar


@pytest.fixture
def referencia():
    return dict(serie_id='A', moneda='MXN', canal='en_linea', cobertura_base=True, base_cerrada=True,
                mediana_base=1000, p25_base=900, p75_base=1100, contexto='serie_vendedor')


def test_minimo_multitienda_no_se_convierte_en_brecha_vendedor(referencia):
    referencia['contexto'] = 'minimo_multitienda'
    resultado = evaluar_oferta(referencia, 800, 2000, 60, serie_oferta_id='A')
    assert resultado['diferencia_frente_referencia_pct'] == pytest.approx(20)
    assert resultado['descuento_implicito_tachado_pct'] == pytest.approx(60)
    assert resultado['brecha_consulta_pp'] is None
    assert not resultado['anuncio_comparable']
    assert not resultado['es_veredicto_fraude']


def test_brecha_exige_identidad_serie_y_anuncio_textual(referencia):
    assert evaluar_oferta(referencia, 800, 2000)['brecha_consulta_pp'] is None
    assert evaluar_oferta(referencia, 800, pct_anunciado=60, serie_oferta_id='B')['brecha_consulta_pp'] is None
    assert evaluar_oferta(referencia, 800, pct_anunciado=60, serie_oferta_id='A')['brecha_consulta_pp'] == pytest.approx(40)


@pytest.mark.parametrize('cambio', [{'cobertura_base': False}, {'base_cerrada': False}, {'moneda': 'USD'}, {'canal': 'tienda_fisica'}])
def test_consulta_no_compara_historia_incompatible(referencia, cambio):
    referencia.update(cambio)
    resultado = evaluar_oferta(referencia, 800)
    assert resultado['estado'] == 'evidencia_insuficiente'
    assert resultado['diferencia_frente_referencia_pct'] is None


@pytest.mark.parametrize('precio', [0, -1, float('nan'), float('inf')])
def test_consulta_rechaza_precio_invalido(referencia, precio):
    with pytest.raises(ValueError):
        evaluar_oferta(referencia, precio)


def test_entrena_solo_2024_y_no_usa_evento_futuro():
    rng = np.random.default_rng(5)
    filas = []
    for evento, n in [('BF2024', 35), ('BF2025', 12), ('BF2026', 5)]:
        for i in range(n):
            filas.append(dict(serie_evento_id=f'{evento}-{i}', serie_id=f'S{i}', evento_id=evento,
                              producto_canonico_id=f'P{i}', descripcion_original='Producto', vendedor_serie='Tienda',
                              plataforma_serie='qqp_cdmx', canal='tienda_fisica', cobertura_alza=True,
                              brecha_pp=np.nan, **dict(zip(VARIABLES, rng.normal(0, 4, 3)))))
    series = pd.DataFrame(filas)
    eventos = pd.DataFrame({'evento_id': ['BF2024', 'BF2025', 'BF2026'], 'evento_fin': ['2024-11-18', '2025-11-17', '2026-11-17']})
    uno = modelar(series, eventos, '2026-11-01', arboles=30)
    modificada = series.copy()
    modificada.loc[modificada.evento_id.eq('BF2025'), VARIABLES] = 999999
    dos = modelar(modificada, eventos, '2026-11-01', arboles=30)
    a = uno['resultados'].query("evento_id == 'BF2024'").set_index('serie_evento_id')
    b = dos['resultados'].query("evento_id == 'BF2024'").set_index('serie_evento_id')
    pd.testing.assert_series_equal(a.puntaje_anomalia.sort_index(), b.puntaje_anomalia.sort_index())
    assert set(uno['resultados'].evento_id) == {'BF2024', 'BF2025'}
    assert uno['tarjeta']['variables'] == VARIABLES
    assert uno['tarjeta']['n_entrenamiento'] == 35
    assert uno['tarjeta']['n_validacion'] == 12
    assert uno['resultados'].revision_humana.eq('pendiente').all()


def test_sqlite_conserva_fk_nulos_y_consultas_parametrizadas(tmp_path):
    tablas = {'productos': pd.DataFrame({'producto_canonico_id': ['P']}),
              'series': pd.DataFrame({'serie_id': ['S'], 'producto_canonico_id': ['P']}),
              'observaciones': pd.DataFrame({'obs_id': ['O'], 'serie_id': ['S'], 'precio': [100.0], 'precio_anterior_anunciado': [np.nan]})}
    db = tmp_path / 'sconto_web.sqlite'
    guardar_sqlite(tablas, db)
    with sqlite3.connect(db) as cn:
        assert cn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert cn.execute('SELECT precio_anterior_anunciado FROM observaciones').fetchone() == (None,)
    assert leer(tmp_path, 'series', "S' OR 1=1 --").empty
    with pytest.raises(ValueError):
        leer(tmp_path, 'series; DROP TABLE series')
    tablas['observaciones']['serie_id'] = 'NO_EXISTE'
    with pytest.raises(pd.errors.DatabaseError):
        guardar_sqlite(tablas, tmp_path / 'otra.sqlite')


def test_web_rechaza_exportacion_alterada(tmp_path):
    db = tmp_path / 'sconto_web.sqlite'
    db.write_bytes(b'original')
    manifest = dict(version='sconto-mart-v1', archivos={'sconto_web.sqlite': hashlib.sha256(db.read_bytes()).hexdigest()})
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    verificar(tmp_path)
    db.write_bytes(b'cambiado')
    with pytest.raises(ValueError, match='modificado'):
        verificar(tmp_path)


def test_app_consulta_real_y_no_afirma_fraude():
    carpeta = Path('data/analitica')
    if not (carpeta / 'manifest.json').exists():
        pytest.skip('Exportar mart antes de probar la app con datos reales')
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path('app/streamlit_app.py').resolve())).run(timeout=45)
    assert not app.exception
    assert app.selectbox[0].options
    app.button[0].click().run(timeout=45)
    assert not app.exception
