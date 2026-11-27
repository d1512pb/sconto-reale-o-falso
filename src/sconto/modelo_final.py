"""Modelo final de Sconto · corte del 26 de noviembre de 2026.

Pregunta de negocio: ¿bajará el precio de este producto de tecnología durante el Buen Fin?
Etiqueta: la mediana del precio durante el evento es menor que la mediana de los 14 días previos,
en la misma serie (producto × sucursal). Las variables sólo usan precios anteriores al evento.

Esquema temporal (sin mirar el futuro):
- Entrenamiento: Buen Fin 2018–2023.
- Validación móvil para elegir hiperparámetros: 2022, 2023 y 2024, cada uno entrenado con los años anteriores.
- Prueba: Buen Fin 2025, entrenando con 2018–2024. No se usa para elegir nada.
- Validación final: Buen Fin 2026 (Preciómetro y piloto PROFECO), entrenando con 2018–2025.

Las reglas de la app (5 %, cuartil P25, cuatro fechas) se justifican con datos comparando las ventanas reales
del Buen Fin contra ventanas "placebo" de semanas normales con la misma estructura.
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin, clone
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from sconto import v2_history as H

SEMILLA = 42
VERSION = 'sconto-modelo-final-2026-11-26'

# Fechas oficiales de cada edición (inicio, fin, fuente consultada).
EDICIONES = {
    2018: ('2018-11-16', '2018-11-19', 'https://www.chilango.com/noticias/buen-fin-2018/'),
    2019: ('2019-11-15', '2019-11-18', 'https://www.promodescuentos.com/evento/el-buen-fin'),
    2020: ('2020-11-09', '2020-11-20', 'https://www.liderempresarial.com/el-buen-fin-2020-tendra-mas-duracion-como-estrategia-ante-contingencia/amp/'),
    2021: ('2021-11-10', '2021-11-16', 'https://www.merca20.com/?p=715945'),
    2022: ('2022-11-18', '2022-11-21', 'https://vanguardia.com.mx/noticias/llega-el-buen-fin-2022-estas-son-las-fechas-oficiales-seran-4-dias-de-ofertas-AH3867121'),
    2023: ('2023-11-17', '2023-11-20', 'https://www.xataka.com.mx/comercio-electronico/buen-fin-2023-tiene-fecha-mexico-fin-semana-promociones-descuentos-sera-17-al-20-noviembre'),
    2024: ('2024-11-15', '2024-11-18', 'Secretaría de Economía (anuncio oficial)'),
    2025: ('2025-11-13', '2025-11-17', 'Avance 1 (QQP 2025)'),
    2026: ('2026-11-13', '2026-11-17', 'https://www.sat.gob.mx/minisitio/SorteoElBuenFin/tarjetahabientes.html'),
}
# Semanas "normales": lejos del Buen Fin, del Hot Sale (finales de mayo) y de diciembre.
PLACEBO = ('02-15', '03-15', '04-15', '07-15', '08-15', '10-01')
UMBRALES = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20)
ANIOS_ENTRENAMIENTO = tuple(range(2018, 2024))
FOLDS_VALIDACION = (2022, 2023, 2024)
VARIABLES = list(H.VARIABLES)
VARIABLES_EXTENDIDAS = VARIABLES + ['log_precio_previo']
NOMBRES_VARIABLES = {
    'alza_previa_pct': 'Cambio de la mediana previa frente a la base (%)',
    'cambio_previo_pct': 'Cambio dentro de las dos semanas previas (%)',
    'iqr_base_pct': 'Dispersión de precios en la base (IQR %)',
    'iqr_previo_pct': 'Dispersión de precios en el previo (IQR %)',
    'n_base': 'Días con precio en la base',
    'n_previo': 'Días con precio en el previo',
    'amplitud_base_dias': 'Amplitud de la base (días)',
    'dias_desde_precio': 'Días desde el último precio previo',
    'log_precio_previo': 'Nivel de precio (log de la mediana previa)',
}


# ---------------------------------------------------------------- ventanas

def ventanas(evento_id: str, inicio, fin) -> dict:
    """Misma estructura que BF2024/BF2025: base de 46 días, previo de 14, evento y posterior de 14 días."""
    i, f = pd.Timestamp(inicio), pd.Timestamp(fin)
    return dict(evento_id=evento_id, base_inicio=i - pd.Timedelta(days=60), base_fin=i - pd.Timedelta(days=15),
                previo_inicio=i - pd.Timedelta(days=14), previo_fin=i - pd.Timedelta(days=1),
                evento_inicio=i, evento_fin=f, posterior_inicio=f + pd.Timedelta(days=1),
                posterior_fin=f + pd.Timedelta(days=14))


def eventos_buen_fin(anios=EDICIONES) -> pd.DataFrame:
    return pd.DataFrame([dict(ventanas(f'BF{a}', *EDICIONES[a][:2]), fuente_fechas=EDICIONES[a][2]) for a in anios])


def eventos_placebo(anios=range(2018, 2026)) -> pd.DataFrame:
    filas = []
    for a in anios:
        for md in PLACEBO:
            i = pd.Timestamp(f'{a}-{md}')
            filas.append(ventanas(f'P{a}-{md}', i, i + pd.Timedelta(days=3)))
    return pd.DataFrame(filas)


def _qqp(obs: pd.DataFrame) -> pd.DataFrame:
    q = obs.loc[obs.fuente.eq('qqp_cdmx')].copy()
    q['moneda'] = q.moneda.fillna('MXN')
    return q[['fuente', 'serie_id', 'fecha_precio', 'precio', *H.METADATOS]]


def _dominio(series: pd.DataFrame) -> pd.Series:
    return series[['fuente', 'canal', 'moneda']].eq(H.DOMINIO).all(axis=1)


# ---------------------------------------------------------------- 1. justificar umbrales con datos

def ventanas_comparables(obs: pd.DataFrame, corte) -> pd.DataFrame:
    """Series con base, previo y evento en ventanas reales del Buen Fin y en semanas normales (placebo)."""
    ev = pd.concat([eventos_buen_fin(range(2018, 2026)), eventos_placebo()], ignore_index=True)
    s = H.preparar_series(_qqp(obs), ev, pd.Timestamp(corte))
    s = s.loc[s.resultado_observado & _dominio(s)].copy()
    s['real'] = s.evento_id.str.startswith('BF')
    s['bajada_previo_pct'] = s.bajada_evento_pct
    s['ahorro_base_pct'] = 100 * (1 - s.mediana_evento / s.mediana_base)
    s['en_p25'] = s.mediana_evento.le(s.p25_base)
    return s


def curva_umbral(v: pd.DataFrame, columna: str, con_p25: bool = False) -> pd.DataFrame:
    """Para cada umbral t: % de ventanas del Buen Fin y de semanas normales que lo superan.

    J de Youden = % Buen Fin − % normal: cuánto separa el umbral una bajada del evento del ruido normal.
    """
    filas = []
    for t in UMBRALES:
        regla = v[columna].ge(t) & (v.en_p25 if con_p25 else True)
        bf, normal = regla[v.real].mean(), regla[~v.real].mean()
        filas.append(dict(umbral_pct=t, pct_buen_fin=100 * bf, pct_semanas_normales=100 * normal,
                          youden_j=100 * (bf - normal), lift=bf / normal if normal else np.nan))
    return pd.DataFrame(filas)


def precision_referencia(obs: pd.DataFrame, k_max: int = 5, min_fechas: int = 6, repeticiones: int = 10) -> pd.DataFrame:
    """Error de la mediana de referencia si sólo hubiera k fechas en la base, frente a usar todas."""
    q = _qqp(obs).assign(fecha_precio=lambda d: pd.to_datetime(d.fecha_precio))
    rng = np.random.default_rng(SEMILLA)
    filas, conteos = [], []
    for e in eventos_buen_fin(range(2018, 2026)).itertuples():
        d = (q.loc[q.fecha_precio.between(e.base_inicio, e.base_fin)]
             .groupby(['serie_id', 'fecha_precio']).precio.median().reset_index())
        conteos.append(d.groupby('serie_id').size())
        for _, g in d.groupby('serie_id'):
            if len(g) < min_fechas:
                continue
            completa, arr = g.precio.median(), g.precio.to_numpy()
            for k in range(1, k_max + 1):
                for _ in range(repeticiones):
                    sub = arr[rng.choice(len(arr), k, replace=False)]
                    filas.append(dict(k=k, error_pct=100 * abs(np.median(sub) / completa - 1)))
    r = pd.DataFrame(filas)
    n = pd.concat(conteos)
    tabla = r.groupby('k').error_pct.agg(
        muestras='size', error_mediano='median', error_p90=lambda x: np.percentile(x, 90),
        pct_error_mayor_5=lambda x: 100 * (x >= 5).mean()).reset_index()
    tabla['pct_series_con_k_fechas'] = [100 * n.ge(k).mean() for k in tabla.k]
    return tabla


def estudio_evento(obs: pd.DataFrame) -> pd.DataFrame:
    """Precio relativo a la mediana de la base, por semana relativa al inicio de cada Buen Fin 2018–2025."""
    q = _qqp(obs).assign(fecha_precio=lambda d: pd.to_datetime(d.fecha_precio))
    piezas = []
    for e in eventos_buen_fin(range(2018, 2026)).itertuples():
        d = (q.loc[q.fecha_precio.between(e.base_inicio, e.posterior_fin)]
             .groupby(['serie_id', 'fecha_precio']).precio.median().reset_index())
        ref = d.loc[d.fecha_precio.le(e.base_fin)].groupby('serie_id').precio.median().rename('ref')
        d = d.join(ref, on='serie_id').dropna(subset=['ref'])
        antes = (d.fecha_precio - e.evento_inicio).dt.days
        despues = (d.fecha_precio - e.evento_fin).dt.days
        # Semana 0 = días del evento; antes y después se cuentan en semanas completas desde sus bordes.
        d['semana'] = np.where(antes < 0, np.floor(antes / 7), np.where(despues > 0, np.ceil(despues / 7), 0))
        d['rel_pct'] = 100 * (d.precio / d.ref - 1)
        piezas.append(d)
    es = pd.concat(piezas)
    return (es.groupby('semana').rel_pct.agg(observaciones='size', promedio='mean', mediana='median')
            .reset_index().astype({'semana': int}))


# ---------------------------------------------------------------- 2. conjunto de datos de modelado

def observaciones_piloto(ruta_sqlite: Path) -> pd.DataFrame:
    """Piloto PROFECO Buen Fin 2026 con la estructura de observaciones. Sin direcciones: sólo cadena y sucursal cifrada."""
    c = sqlite3.connect(f'file:{Path(ruta_sqlite).as_posix()}?mode=ro', uri=True)
    p = pd.read_sql("select d.offer_id, d.fecha_precio, d.precio, d.condiciones_json, c.fetched_at_utc, o.producto_id, o.vendedor "
                    "from observaciones_diarias_fuente d join capturas c using(capture_id) join ofertas o using(offer_id) "
                    "where o.fuente='profeco_buen_fin'", c)
    c.close()
    p = p.sort_values('fetched_at_utc').groupby(['offer_id', 'fecha_precio']).tail(1)
    info = p.condiciones_json.map(json.loads)
    cadena = p.vendedor.str.split(' SUCURSAL').str[0].str.strip()
    return pd.DataFrame(dict(
        fuente='profeco_bf2026', serie_id=p.offer_id.str[:20], fecha_precio=p.fecha_precio, precio=p.precio,
        id_externo='PROFECO-' + p.producto_id.astype(str), canal='tienda_fisica', moneda='MXN',
        vendedor_serie=p.offer_id.str[:20], vendedor_o_cadena=cadena,
        descripcion_original=info.map(lambda d: f"{d.get('marca') or ''} | {d.get('descripcion') or ''}".strip(' |')),
        producto_canonico_id=None))


def dataset_modelado(obs: pd.DataFrame, piloto: pd.DataFrame | None, corte) -> pd.DataFrame:
    """Una fila por serie y Buen Fin con variables previas al evento y la etiqueta 'bajó'."""
    columnas = ['fuente', 'serie_id', 'fecha_precio', 'precio', *H.METADATOS]
    base = obs.loc[obs.fuente.isin(['qqp_cdmx', 'preciometro'])].copy()
    base['moneda'] = base.moneda.fillna('MXN')
    entrada = [base[columnas]]
    if piloto is not None and len(piloto):
        entrada.append(piloto[columnas])
    s = H.preparar_series(pd.concat(entrada, ignore_index=True), eventos_buen_fin(), pd.Timestamp(corte))
    finitas = np.isfinite(s[VARIABLES].astype(float)).all(axis=1)
    s['anio'] = s.evento_id.str[2:].astype(int)
    qqp = s.fuente.eq('qqp_cdmx') & _dominio(s) & s.resultado_observado & s.anio.le(2025)
    profeco = s.fuente.eq('profeco_bf2026') & s.resultado_observado
    # Preciómetro es el mínimo entre tiendas: la tienda cambia, así que sólo se relaja la identidad de sucursal.
    precio_min = (s.fuente.eq('preciometro') & s.evento_cerrado & s.amplitud_base_dias.ge(H.MIN_AMPLITUD)
                  & s.n_base.ge(H.MIN_BASE) & s.n_previo.ge(H.MIN_PREVIO) & s.n_evento.ge(H.MIN_EVENTO))
    d = s.loc[(qqp | profeco | precio_min) & finitas].copy()
    d['y'] = d.bajada_evento_mxn.gt(0).astype(int)
    d['log_precio_previo'] = np.log(d.mediana_previo)
    d['conjunto'] = np.select(
        [d.anio.le(2021), d.anio.le(2024), d.anio.eq(2025), d.anio.eq(2026)],
        ['entrenamiento', 'validacion', 'prueba', 'validacion_final'], 'otro')
    d.loc[d.anio.between(2022, 2023), 'conjunto'] = 'entrenamiento_y_validacion'
    d['poblacion'] = d.fuente.map({'qqp_cdmx': 'QQP sucursales CDMX', 'preciometro': 'Preciómetro mínimo en línea',
                                   'profeco_bf2026': 'PROFECO sucursales CDMX/ZMVM'})
    d['categoria'] = (d.descripcion_original.fillna('').str.split('|', n=1).str[0].str.strip().str.capitalize()
                      .where(d.fuente.eq('qqp_cdmx')))
    if 'producto_canonico_id' in obs.columns:
        mapa = (obs.loc[obs.fuente.eq('preciometro')].dropna(subset=['producto_canonico_id'])
                .groupby('serie_id').producto_canonico_id.first())
        d['producto_canonico_id'] = d.serie_id.map(mapa)
    columnas_salida = ['evento_id', 'anio', 'conjunto', 'poblacion', 'fuente', 'serie_id', 'id_externo',
                       'producto_canonico_id', 'categoria', 'tienda', 'descripcion_original', *VARIABLES_EXTENDIDAS,
                       'mediana_base', 'mediana_previo', 'mediana_evento', 'bajada_evento_pct', 'y']
    return d[columnas_salida].sort_values(['anio', 'fuente', 'serie_id']).reset_index(drop=True)


# ---------------------------------------------------------------- 3. modelos

class PuntajeIsolationForest(BaseEstimator, TransformerMixin):
    """Agrega como variable el puntaje de rareza de un Isolation Forest ajustado sólo con el entrenamiento."""

    def __init__(self, n_estimators=300, contamination='auto', random_state=SEMILLA):
        self.n_estimators, self.contamination, self.random_state = n_estimators, contamination, random_state

    def fit(self, X, y=None):
        self.iso_ = IsolationForest(n_estimators=self.n_estimators, contamination=self.contamination,
                                    random_state=self.random_state).fit(X)
        return self

    def transform(self, X):
        return np.column_stack([np.asarray(X, dtype=float), -self.iso_.score_samples(X)])


class ClasificadorIsolationForest(BaseEstimator, ClassifierMixin):
    """Isolation Forest usado como clasificador.

    El bosque aprende sin etiqueta qué series son raras. La etiqueta sólo se usa para decidir la dirección:
    si en el entrenamiento las series raras bajan más que las normales, "rara" se predice como "bajará".
    """

    def __init__(self, n_estimators=300, contamination=0.1, max_features=1.0, random_state=SEMILLA):
        self.n_estimators, self.contamination = n_estimators, contamination
        self.max_features, self.random_state = max_features, random_state

    def fit(self, X, y):
        y = np.asarray(y)
        self.iso_ = IsolationForest(n_estimators=self.n_estimators, contamination=self.contamination,
                                    max_features=self.max_features, random_state=self.random_state).fit(X)
        rara = self.iso_.predict(X) == -1
        self.rara_baja_ = bool(y[rara].mean() >= y[~rara].mean()) if rara.any() and (~rara).any() else True
        self.referencia_ = np.sort(-self.iso_.score_samples(X))
        self.classes_ = np.array([0, 1])
        return self

    def predict(self, X):
        rara = self.iso_.predict(X) == -1
        return (rara if self.rara_baja_ else ~rara).astype(int)

    def predict_proba(self, X):
        puntaje = -self.iso_.score_samples(X)
        p = np.searchsorted(self.referencia_, puntaje, side='right') / len(self.referencia_)
        p = p if self.rara_baja_ else 1 - p
        return np.column_stack([1 - p, p])


class ReglaSimple(BaseEstimator, ClassifierMixin):
    """Línea base de una sola regla: 'bajará' si la variable cumple el signo indicado."""

    def __init__(self, variable='cambio_previo_pct', mayor_que_cero=False):
        self.variable, self.mayor_que_cero = variable, mayor_que_cero

    def fit(self, X, y):
        self.classes_ = np.array([0, 1])
        return self

    def predict(self, X):
        v = X[self.variable].to_numpy()
        return (v > 0 if self.mayor_que_cero else v < 0).astype(int)

    def predict_proba(self, X):
        p = self.predict(X).astype(float)
        return np.column_stack([1 - p, p])


class ClaseMayoritaria(BaseEstimator, ClassifierMixin):
    def fit(self, X, y):
        self.p_ = float(np.mean(y))
        self.clase_ = int(self.p_ >= .5)
        self.classes_ = np.array([0, 1])
        return self

    def predict(self, X):
        return np.full(len(X), self.clase_)

    def predict_proba(self, X):
        return np.column_stack([np.full(len(X), 1 - self.p_), np.full(len(X), self.p_)])


@dataclass
class Candidato:
    familia: str
    variante: str
    variables: list
    estimador: object


def candidatos() -> list[Candidato]:
    c = [Candidato('Línea base: clase mayoritaria', 'siempre predice la clase más común del entrenamiento',
                   VARIABLES, ClaseMayoritaria())]
    for var, signo, texto in (('cambio_previo_pct', False, 'ya venía bajando en las 2 semanas previas'),
                              ('alza_previa_pct', True, 'subió antes del evento'),
                              ('alza_previa_pct', False, 'bajó antes del evento')):
        c.append(Candidato('Línea base: regla simple', f'bajará si {texto}', VARIABLES, ReglaSimple(var, signo)))
    for vars_, nombre in ((VARIABLES, '8 variables'), (VARIABLES_EXTENDIDAS, '8 variables + precio')):
        for C in (0.01, 0.1, 1, 10):
            for cw in (None, 'balanced'):
                c.append(Candidato('Regresión logística', f'C={C}, pesos={cw or "no"}, {nombre}', vars_,
                                   make_pipeline(StandardScaler(), LogisticRegression(C=C, class_weight=cw, max_iter=3000))))
        for prof in (2, 3, 4, 5, 6):
            for hoja in (5, 10, 20, 40):
                for cw in (None, 'balanced'):
                    c.append(Candidato('Árbol de decisión', f'profundidad={prof}, hoja>={hoja}, pesos={cw or "no"}, {nombre}', vars_,
                                       DecisionTreeClassifier(max_depth=prof, min_samples_leaf=hoja, class_weight=cw,
                                                              random_state=SEMILLA)))
        for prof in (4, 8, None):
            for hoja in (1, 5, 10, 20):
                for cw in (None, 'balanced'):
                    c.append(Candidato('Random Forest', f'profundidad={prof or "libre"}, hoja>={hoja}, pesos={cw or "no"}, {nombre}', vars_,
                                       RandomForestClassifier(n_estimators=300, max_depth=prof, min_samples_leaf=hoja,
                                                              class_weight=cw, random_state=SEMILLA, n_jobs=-1)))
        for cont in (0.05, 0.1, 0.2, 0.3, 0.4):
            for mf in (1.0, 0.5):
                c.append(Candidato('Isolation Forest', f'contaminación={cont}, variables por árbol={mf:.0%}, {nombre}', vars_,
                                   ClasificadorIsolationForest(contamination=cont, max_features=mf)))
        for prof, hoja in ((4, 10), (8, 5), (None, 10)):
            c.append(Candidato('Random Forest + puntaje IF', f'profundidad={prof or "libre"}, hoja>={hoja}, {nombre}', vars_,
                               make_pipeline(PuntajeIsolationForest(),
                                             RandomForestClassifier(n_estimators=300, max_depth=prof, min_samples_leaf=hoja,
                                                                    random_state=SEMILLA, n_jobs=-1))))
    return c


def _probabilidad(modelo, X):
    return modelo.predict_proba(X)[:, list(modelo.classes_).index(1)]


def metricas(y, pred, prob, pesos=None) -> dict:
    y, pred, prob = np.asarray(y), np.asarray(pred), np.asarray(prob, dtype=float)
    w = np.ones(len(y)) if pesos is None else np.asarray(pesos, dtype=float)
    tp = w[(y == 1) & (pred == 1)].sum(); tn = w[(y == 0) & (pred == 0)].sum()
    fp = w[(y == 0) & (pred == 1)].sum(); fn = w[(y == 1) & (pred == 0)].sum()
    rec = tp / (tp + fn) if tp + fn else np.nan
    esp = tn / (tn + fp) if tn + fp else np.nan
    try:
        auc = roc_auc_score(y, prob, sample_weight=w) if len(np.unique(y[w > 0])) == 2 else np.nan
    except ValueError:
        auc = np.nan
    return dict(n=int(round(w.sum())), tn=tn, fp=fp, fn=fn, tp=tp,
                accuracy=(tp + tn) / w.sum(), balanced_accuracy=np.nanmean([rec, esp]),
                precision=tp / (tp + fp) if tp + fp else np.nan, recall=rec, especificidad=esp,
                f1=2 * tp / (2 * tp + fp + fn) if tp + fp + fn else np.nan, auc=auc,
                brier=float(np.average((prob - y) ** 2, weights=w)))


def intervalos(y, pred, prob, grupos, repeticiones=1000) -> dict:
    """IC95 con remuestreo por producto: productos completos entran o salen juntos."""
    estratos, inverso = np.unique(np.asarray(grupos).astype(str), return_inverse=True)
    rng = np.random.default_rng(SEMILLA)
    pesos = rng.multinomial(len(estratos), [1 / len(estratos)] * len(estratos), size=repeticiones)[:, inverso]
    valores = {k: [] for k in ('accuracy', 'balanced_accuracy', 'f1', 'auc')}
    for w in pesos:
        m = metricas(y, pred, prob, w)
        for k in valores:
            valores[k].append(m[k])
    salida = {}
    for k, v in valores.items():
        v = np.asarray(v, dtype=float); v = v[np.isfinite(v)]
        salida[f'{k}_ic95'] = [float(np.quantile(v, .025)), float(np.quantile(v, .975))] if len(v) else [None, None]
    return salida


def _ajustar_predecir(cand: Candidato, train: pd.DataFrame, test: pd.DataFrame):
    modelo = clone(cand.estimador)
    Xtr, Xte = train[cand.variables], test[cand.variables]
    if not isinstance(modelo, (ReglaSimple,)):
        Xtr, Xte = (Xtr.to_numpy(dtype=float), Xte.to_numpy(dtype=float))
    modelo.fit(Xtr, train.y.to_numpy())
    return modelo, modelo.predict(Xte), _probabilidad(modelo, Xte)


def validacion_movil(datos: pd.DataFrame, cands: list[Candidato]) -> pd.DataFrame:
    """Cada candidato se entrena con los años anteriores y se valida en 2022, 2023 y 2024."""
    qqp = datos.loc[datos.fuente.eq('qqp_cdmx')]
    filas = []
    for cand in cands:
        por_fold = []
        for anio in FOLDS_VALIDACION:
            tr, va = qqp.loc[qqp.anio.lt(anio)], qqp.loc[qqp.anio.eq(anio)]
            _, pred, prob = _ajustar_predecir(cand, tr, va)
            m = metricas(va.y, pred, prob)
            por_fold.append(m)
            filas.append(dict(familia=cand.familia, variante=cand.variante, fold=anio, **m))
    tabla = pd.DataFrame(filas)
    resumen = (tabla.groupby(['familia', 'variante'], sort=False)
               .agg(bal_acc_validacion=('balanced_accuracy', 'mean'), bal_acc_min=('balanced_accuracy', 'min'),
                    accuracy_validacion=('accuracy', 'mean'), f1_validacion=('f1', 'mean'), auc_validacion=('auc', 'mean'))
               .reset_index())
    return tabla, resumen


def elegir(resumen: pd.DataFrame) -> pd.DataFrame:
    """Mejor variante por familia según la balanced accuracy media de validación (AUC desempata)."""
    orden = resumen.sort_values(['bal_acc_validacion', 'auc_validacion'], ascending=False)
    return orden.groupby('familia', sort=False).head(1).reset_index(drop=True)


def evaluar(datos: pd.DataFrame, cands: list[Candidato], elegidos: pd.DataFrame):
    """Prueba 2025 (entrena 2018–2024) y validación final 2026 (entrena 2018–2025) para cada familia elegida."""
    qqp = datos.loc[datos.fuente.eq('qqp_cdmx')]
    por_nombre = {(c.familia, c.variante): c for c in cands}
    conjuntos = {
        'Prueba 2025 · QQP sucursales': (qqp.loc[qqp.anio.le(2024)], qqp.loc[qqp.anio.eq(2025)]),
        'Validación final 2026 · Preciómetro': (qqp, datos.loc[datos.fuente.eq('preciometro') & datos.anio.eq(2026)]),
        'Validación final 2026 · PROFECO': (qqp, datos.loc[datos.fuente.eq('profeco_bf2026') & datos.anio.eq(2026)]),
    }
    filas, predicciones, modelos = [], [], {}
    for fila in elegidos.itertuples():
        cand = por_nombre[(fila.familia, fila.variante)]
        for nombre, (tr, te) in conjuntos.items():
            if te.empty:
                continue
            modelo, pred, prob = _ajustar_predecir(cand, tr, te)
            m = metricas(te.y, pred, prob)
            ic = intervalos(te.y.to_numpy(), pred, prob, te.id_externo.to_numpy())
            filas.append(dict(conjunto=nombre, familia=cand.familia, variante=cand.variante,
                              n_productos=te.id_externo.nunique(), positivos=int(te.y.sum()), **m, **ic))
            predicciones.append(te[['evento_id', 'fuente', 'serie_id', 'id_externo', 'producto_canonico_id',
                                    'descripcion_original', 'bajada_evento_pct', 'y']]
                                .assign(conjunto=nombre, familia=cand.familia, prob_bajada=prob, prediccion=pred))
            if nombre.startswith('Validación final 2026 · Preciómetro'):
                modelos[cand.familia] = modelo
    return pd.DataFrame(filas), pd.concat(predicciones, ignore_index=True), modelos


def importancias(modelo, variables) -> pd.DataFrame:
    est = modelo[-1] if hasattr(modelo, 'steps') else modelo
    if hasattr(modelo, 'steps') and any(isinstance(p, PuntajeIsolationForest) for _, p in modelo.steps):
        variables = list(variables) + ['puntaje_rareza_if']
    if hasattr(est, 'feature_importances_'):
        imp = est.feature_importances_
    elif hasattr(est, 'coef_'):
        imp = np.abs(est.coef_[0])
    else:
        return pd.DataFrame()
    NOMBRES_VARIABLES.setdefault('puntaje_rareza_if', 'Puntaje de rareza del Isolation Forest')
    return (pd.DataFrame(dict(variable=variables, importancia=imp, descripcion=[NOMBRES_VARIABLES.get(v, v) for v in variables]))
            .sort_values('importancia', ascending=False).reset_index(drop=True))


# ---------------------------------------------------------------- figuras

def figuras(salida: Path, curvas: dict, estudio: pd.DataFrame, metricas_finales: pd.DataFrame,
            predicciones: pd.DataFrame, elegido: str) -> list[Path]:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rutas = []
    azul, gris, naranja = '#2563eb', '#9ca3af', '#ea580c'

    fig, ejes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, (titulo, curva) in zip(ejes, curvas.items()):
        ax.plot(curva.umbral_pct, curva.pct_buen_fin, marker='o', color=azul, label='Buen Fin')
        ax.plot(curva.umbral_pct, curva.pct_semanas_normales, marker='o', color=gris, label='Semanas normales')
        ax.fill_between(curva.umbral_pct, curva.pct_semanas_normales, curva.pct_buen_fin, color=azul, alpha=.08)
        mejor = curva.loc[curva.youden_j.idxmax()]
        en5 = curva.loc[curva.umbral_pct.eq(5)].iloc[0]
        ax.axvline(5, color=naranja, ls='--', lw=1)
        ax.annotate('', xy=(5, en5.pct_buen_fin), xytext=(5, en5.pct_semanas_normales),
                    arrowprops=dict(arrowstyle='<->', color=naranja, lw=1.4))
        ax.text(5.4, (en5.pct_buen_fin + en5.pct_semanas_normales) / 2,
                f'Separación con 5 %:\nJ = {en5.youden_j:.1f} pts\n(máx. {mejor.youden_j:.1f} en {mejor.umbral_pct:g} %)',
                fontsize=8, color=naranja, va='center')
        ax.set_title(titulo, fontsize=10); ax.set_xlabel('Umbral (%)'); ax.set_ylabel('% de ventanas que lo superan')
        ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.2)
    fig.suptitle('¿Desde qué tamaño una bajada es del Buen Fin y no ruido normal? (QQP 2018–2025)', fontsize=11)
    fig.tight_layout(); rutas.append(salida / 'fig_umbral_ruido_vs_buen_fin.png'); fig.savefig(rutas[-1], dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.bar(estudio.semana, estudio.promedio, color=[naranja if s == 0 else azul for s in estudio.semana])
    ax.axhline(0, color='black', lw=.8)
    ax.set_xlabel('Semanas respecto al Buen Fin (0 = días del evento)'); ax.set_ylabel('Precio vs. mediana base (%)')
    ax.set_title('Precio promedio alrededor del Buen Fin · QQP CDMX 2018–2025', fontsize=11); ax.grid(axis='y', alpha=.2)
    fig.tight_layout(); rutas.append(salida / 'fig_estudio_evento.png'); fig.savefig(rutas[-1], dpi=150); plt.close(fig)

    tabla = metricas_finales.pivot_table(index='familia', columns='conjunto', values='balanced_accuracy', sort=False)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    tabla.plot.barh(ax=ax, color=[azul, naranja, gris][:tabla.shape[1]], width=.8)
    ax.axvline(.5, color='black', lw=.8, ls=':')
    ax.set_xlabel('Balanced accuracy (0.5 = adivinar)'); ax.set_ylabel(''); ax.set_xlim(.3, 1)
    ax.set_title('Comparación de modelos con datos que no vieron al entrenar', fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc='upper center', bbox_to_anchor=(.5, -.16), ncol=3); ax.grid(axis='x', alpha=.2)
    fig.tight_layout(); rutas.append(salida / 'fig_comparacion_modelos.png'); fig.savefig(rutas[-1], dpi=150); plt.close(fig)

    sel = predicciones.loc[predicciones.familia.eq(elegido)]
    conj = list(dict.fromkeys(sel.conjunto))
    fig, ejes = plt.subplots(1, len(conj), figsize=(4 * len(conj), 3.6))
    for ax, nombre in zip(np.atleast_1d(ejes), conj):
        p = sel.loc[sel.conjunto.eq(nombre)]
        m = np.array([[((p.y == 0) & (p.prediccion == 0)).sum(), ((p.y == 0) & (p.prediccion == 1)).sum()],
                      [((p.y == 1) & (p.prediccion == 0)).sum(), ((p.y == 1) & (p.prediccion == 1)).sum()]])
        ax.imshow(m, cmap='Blues')
        for (i, j), v in np.ndenumerate(m):
            ax.text(j, i, int(v), ha='center', va='center', fontsize=12, color='white' if v > m.max() / 2 else 'black')
        ax.set_xticks([0, 1], ['No bajará', 'Bajará']); ax.set_yticks([0, 1], ['No bajó', 'Bajó'])
        ax.set_xlabel('Predicción'); ax.set_title(nombre, fontsize=9)
    fig.suptitle(f'Matrices de confusión · {elegido}', fontsize=11)
    fig.tight_layout(); rutas.append(salida / 'fig_matrices_confusion.png'); fig.savefig(rutas[-1], dpi=150); plt.close(fig)
    return rutas


# ---------------------------------------------------------------- ejecución completa

def cargar_paquete(ruta_zip: Path) -> pd.DataFrame:
    z = zipfile.ZipFile(ruta_zip)
    return pd.read_parquet(io.BytesIO(z.read('observaciones.parquet')))


def ejecutar(paquete: Path, piloto: Path | None, salida: Path, corte='2026-11-26', modelos_dir: Path | None = None) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    obs = cargar_paquete(paquete)
    resultado = {'version': VERSION, 'corte': corte, 'generado_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')}

    # 1. Reglas con datos
    v = ventanas_comparables(obs, corte)
    curvas = {'Bajada frente a las 2 semanas previas (etiqueta del modelo)': curva_umbral(v, 'bajada_previo_pct'),
              'Ahorro frente a la mediana base + P25 (regla de la app)': curva_umbral(v, 'ahorro_base_pct', con_p25=True)}
    solo_pct = curva_umbral(v, 'ahorro_base_pct')
    precision = precision_referencia(obs)
    estudio = estudio_evento(obs)
    curvas['Bajada frente a las 2 semanas previas (etiqueta del modelo)'].to_csv(salida / 'umbral_etiqueta_modelo.csv', index=False)
    curvas['Ahorro frente a la mediana base + P25 (regla de la app)'].to_csv(salida / 'umbral_regla_app_con_p25.csv', index=False)
    solo_pct.to_csv(salida / 'umbral_regla_app_sin_p25.csv', index=False)
    precision.to_csv(salida / 'precision_referencia_fechas.csv', index=False)
    estudio.to_csv(salida / 'estudio_evento_semanal.csv', index=False)
    resultado['ventanas'] = dict(buen_fin=int(v.real.sum()), semanas_normales=int((~v.real).sum()))

    # 2. Dataset
    obs_piloto = observaciones_piloto(piloto) if piloto and Path(piloto).exists() else None
    datos = dataset_modelado(obs, obs_piloto, corte)
    datos.to_csv(salida / 'dataset_modelado.csv', index=False)
    resultado['dataset'] = (datos.groupby(['evento_id', 'poblacion'])
                            .agg(series=('y', 'size'), bajaron=('y', 'sum'), productos=('id_externo', 'nunique'))
                            .reset_index().to_dict(orient='records'))

    # 3. Modelos
    cands = candidatos()
    folds, resumen = validacion_movil(datos, cands)
    folds.to_csv(salida / 'validacion_por_fold.csv', index=False)
    resumen.to_csv(salida / 'seleccion_variantes.csv', index=False)
    elegidos = elegir(resumen)
    elegidos.to_csv(salida / 'variantes_elegidas.csv', index=False)
    finales, predicciones, modelos = evaluar(datos, cands, elegidos)
    finales.to_csv(salida / 'metricas_finales.csv', index=False)
    predicciones.to_csv(salida / 'predicciones.csv', index=False)
    supervisadas = elegidos.loc[~elegidos.familia.str.startswith('Línea base')]
    modelo_elegido = supervisadas.sort_values(['bal_acc_validacion', 'auc_validacion'], ascending=False).iloc[0]
    resultado['modelo_elegido'] = dict(familia=modelo_elegido.familia, variante=modelo_elegido.variante,
                                       bal_acc_validacion=float(modelo_elegido.bal_acc_validacion))
    var_elegidas = next(c.variables for c in cands if (c.familia, c.variante) == (modelo_elegido.familia, modelo_elegido.variante))
    importancias(modelos[modelo_elegido.familia], var_elegidas).to_csv(salida / 'importancia_variables.csv', index=False)
    rutas = figuras(salida, curvas, estudio, finales, predicciones, modelo_elegido.familia)
    resultado['figuras'] = [r.name for r in rutas]
    if modelos_dir is not None:
        import joblib
        modelos_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(dict(modelo=modelos[modelo_elegido.familia], variables=var_elegidas, version=VERSION,
                         familia=modelo_elegido.familia, variante=modelo_elegido.variante),
                    modelos_dir / 'modelo_final.joblib')
    (salida / 'resumen.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return dict(resultado=resultado, curvas=curvas, solo_pct=solo_pct, precision=precision, estudio=estudio, datos=datos,
                folds=folds, resumen=resumen, elegidos=elegidos, finales=finales, predicciones=predicciones, modelos=modelos)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--paquete', type=Path, required=True)
    ap.add_argument('--piloto', type=Path)
    ap.add_argument('--salida', type=Path, required=True)
    ap.add_argument('--modelos', type=Path)
    ap.add_argument('--corte', default='2026-11-26')
    a = ap.parse_args(argv)
    r = ejecutar(a.paquete, a.piloto, a.salida, a.corte, a.modelos)
    print(json.dumps(r['resultado'], ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
