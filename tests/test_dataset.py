"""Validaciones del dataset gold y reproducción exacta del Avance 1.

Se ejecutan sobre data/gold/ (reconstruirlo antes con `python -m sconto.dataset`); se omiten si no existe.
"""
import pandas as pd
import pytest

from sconto.almacen import leer_bronze
from sconto.esquema import CANALES, CLAVE, METODOS, TIPOS_ID
from sconto.rutas import AVANCE1, GOLD

pytestmark = pytest.mark.skipif(not (GOLD / 'observaciones.parquet').exists(), reason='gold no construido')


@pytest.fixture(scope='module')
def obs():
    return pd.read_parquet(GOLD / 'observaciones.parquet')


@pytest.fixture(scope='module')
def se():
    return pd.read_parquet(GOLD / 'series_evento.parquet')


def test_sin_duplicados_por_clave(obs):
    assert not obs.duplicated(CLAVE).any()


def test_precios_fechas_y_porcentajes(obs):
    assert (obs.precio > 0).all()
    assert pd.to_datetime(obs.fecha_precio, errors='coerce').notna().all()
    pct = obs.pct_descuento_anunciado.dropna()
    assert pct.between(-100, 100).all()
    assert obs.precio_anterior_anunciado.dropna().gt(0).all()


def test_dominios(obs):
    assert set(obs.metodo.dropna()) <= METODOS
    assert set(obs.canal.dropna()) <= CANALES
    assert set(obs.tipo_id_externo.dropna()) <= TIPOS_ID


def test_no_se_mezclan_canales_en_una_serie(obs):
    assert obs.groupby('serie_id').canal.nunique().le(1).all()


def test_toda_fila_bronze_termina_limpia_o_excluida(obs):
    excl = pd.read_parquet(GOLD / 'exclusiones.parquet')
    # Cada fila limpia representa n_capturas filas bronze con la misma clave; las demás están en exclusiones.
    fuentes = sorted(set(obs.fuente) | set(excl.fuente.dropna()))
    bronze = sum(len(leer_bronze(f)) for f in fuentes)
    assert int(obs.n_capturas.sum()) + len(excl) == bronze


def test_reproduccion_avance1_qqp_2025(obs, se):
    qqp25 = obs.loc[obs.fuente.eq('qqp_cdmx') & obs.fecha_precio.str.startswith('2025')]
    assert len(qqp25) == 39363
    bf25 = se.loc[se.evento_id.eq('BF2025') & se.plataforma_serie.eq('qqp_cdmx')]
    assert int(bf25.cobertura_ahorro.sum()) == 298
    assert int(bf25.cobertura_alza.sum()) == 93


@pytest.mark.skipif(not (AVANCE1 / '07_matriz_modelo.csv').exists(), reason='Evidencia del Avance 1 sólo disponible localmente')
def test_matriz_igual_a_avance1():
    X = pd.read_parquet(GOLD / 'matriz_modelo.parquet')
    meta = pd.read_parquet(GOLD / 'metadatos_modelo.parquet')
    a1 = pd.read_csv(AVANCE1 / '07_matriz_modelo.csv', index_col='serie_id')
    m = X.join(meta[['serie_id', 'evento_id']])
    m = m.loc[m.evento_id.eq('BF2025') & m.serie_id.isin(a1.index)].set_index('serie_id')
    assert set(m.index) == set(a1.index)
    assert (m[a1.columns].loc[a1.index] - a1).abs().max().max() < 1e-9


def test_ids_no_son_variables_del_modelo():
    X = pd.read_parquet(GOLD / 'matriz_modelo.parquet')
    assert list(X.columns) == ['ahorro_historico_pct', 'alza_previa_pct', 'variabilidad_base_pct']
    assert X.notna().all().all()


def test_etiqueta_derivada_solo_con_brecha(se):
    for u in (5, 10, 15):
        col = f'regla_descuento_inflado_{u}pp'
        assert se.loc[se.brecha_pp.isna(), col].isna().all()
