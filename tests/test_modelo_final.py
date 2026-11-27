"""El modelo ligero de la API debe dar exactamente lo mismo que pandas y scikit-learn."""
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sconto import prediccion_ligera as L
from sconto import v2_history as H
from sconto.modelo_final import ClasificadorIsolationForest, ReglaSimple, curva_umbral, metricas, ventanas

RAIZ = Path(__file__).resolve().parents[1]
CORTE = RAIZ / 'data/operacion/v2/corte_final_20261126'
MODELO = RAIZ / 'data/operacion/v2/modelo_final_20261126/modelo_final.joblib'
ARBOL = RAIZ / 'data/operacion/v2/app_v3/modelo/arbol.json'


def test_ventanas_iguales_a_eventos_del_proyecto():
    v = ventanas('BF2025', '2025-11-13', '2025-11-17')
    assert (str(v['base_inicio'].date()), str(v['base_fin'].date())) == ('2025-09-14', '2025-10-29')
    assert (str(v['previo_inicio'].date()), str(v['previo_fin'].date())) == ('2025-10-30', '2025-11-12')


def test_caracteristicas_ligeras_contra_pandas():
    fechas = pd.date_range('2025-09-10', '2025-11-12', freq='5D')
    precios = 1000 + 10 * np.sin(np.arange(len(fechas)))
    obs = pd.DataFrame(dict(fuente='qqp_cdmx', serie_id='s1', fecha_precio=fechas, precio=precios, id_externo='p1',
                            canal='tienda_fisica', moneda='MXN', vendedor_serie='T1', vendedor_o_cadena='T',
                            descripcion_original='Pantallas | X'))
    ev = pd.DataFrame([ventanas('BF2025', '2025-11-13', '2025-11-17')])
    s = H.preparar_series(obs, ev, pd.Timestamp('2025-12-31')).iloc[0]
    x = L.caracteristicas([(f.date(), p) for f, p in zip(fechas, precios)], date(2025, 11, 13))
    for var in H.VARIABLES:
        assert x[var] == pytest.approx(float(s[var]), rel=1e-9, abs=1e-9), var


def test_regla_simple_y_metricas():
    X = pd.DataFrame(dict(cambio_previo_pct=[-1.0, 0.0, 2.0]))
    assert ReglaSimple().fit(X, [1, 0, 0]).predict(X).tolist() == [1, 0, 0]
    m = metricas(np.array([1, 0, 1, 0]), np.array([1, 0, 0, 0]), np.array([.9, .1, .4, .2]))
    assert m['accuracy'] == .75 and m['balanced_accuracy'] == .75 and m['recall'] == .5


def test_isolation_forest_aprende_direccion_sin_usar_etiqueta_para_ajustar():
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(0, 1, (90, 2)), rng.normal(6, 1, (10, 2))])
    y = np.r_[np.zeros(90), np.ones(10)]
    clf = ClasificadorIsolationForest(contamination=.1).fit(X, y)
    assert clf.rara_baja_ and clf.predict(X)[-10:].mean() > .5


def test_curva_umbral_youden():
    v = pd.DataFrame(dict(real=[True, True, False, False], x=[6.0, 1.0, 0.0, 6.0], en_p25=True))
    fila = curva_umbral(v, 'x').set_index('umbral_pct').loc[5]
    assert fila.pct_buen_fin == 50 and fila.pct_semanas_normales == 50 and fila.youden_j == 0


@pytest.mark.skipif(not (MODELO.exists() and ARBOL.exists()), reason='modelo final no generado')
def test_arbol_exportado_igual_a_scikit_learn():
    import joblib
    paquete = joblib.load(MODELO)
    arbol = json.loads(ARBOL.read_text(encoding='utf-8'))
    datos = pd.read_csv(RAIZ / 'reports/modelo_final/dataset_modelado.csv')
    X = datos[paquete['variables']].to_numpy(dtype=float)
    esperado = paquete['modelo'].predict_proba(X)[:, 1]
    obtenido = [L.evaluar_arbol(arbol, dict(zip(paquete['variables'], fila))) for fila in X]
    assert np.allclose(esperado, obtenido)


@pytest.mark.skipif(not CORTE.exists(), reason='corte final no disponible')
def test_caracteristicas_ligeras_en_series_reales():
    z = zipfile.ZipFile(next(CORTE.glob('sconto_colab_*.zip')))
    obs = pd.read_parquet(io.BytesIO(z.read('observaciones.parquet')), columns=['fuente', 'serie_id', 'fecha_precio', 'precio'])
    datos = pd.read_csv(RAIZ / 'reports/modelo_final/dataset_modelado.csv')
    muestra = datos.loc[datos.fuente.eq('qqp_cdmx') & datos.anio.eq(2024)].head(15)
    for fila in muestra.itertuples():
        o = obs.loc[obs.serie_id.eq(fila.serie_id)]
        precios = [(pd.Timestamp(f).date(), p) for f, p in zip(o.fecha_precio, o.precio)]
        x = L.caracteristicas(precios, date(2024, 11, 15))
        for var in ('alza_previa_pct', 'cambio_previo_pct', 'iqr_base_pct', 'n_base', 'amplitud_base_dias'):
            assert x[var] == pytest.approx(getattr(fila, var), rel=1e-6, abs=1e-6), (fila.serie_id, var)
