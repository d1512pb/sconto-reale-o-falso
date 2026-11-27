"""Viabilidad: evalúa en BF2026 el modelo supervisado fijado (BF2024 -> BF2025). Uso: python scripts/viabilidad_modelo_bf2026.py <raiz_repo>"""
import io, json, sqlite3, sys, zipfile
from pathlib import Path
import numpy as np, pandas as pd

RAIZ = Path(sys.argv[1])
sys.path.insert(0, str(RAIZ / 'src'))
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sconto import v2_history as H

corte = RAIZ / 'data/operacion/v2/corte_final_20261126'
z = zipfile.ZipFile(next(corte.glob('sconto_colab_*.zip')))
obs = pd.read_parquet(io.BytesIO(z.read('observaciones.parquet')))
eventos = pd.read_parquet(io.BytesIO(z.read('eventos.parquet')))
for c in eventos.columns:
    if c.endswith(('_inicio', '_fin')) or c in ('d0', 'fin'):
        eventos[c] = pd.to_datetime(eventos[c])
obs['moneda'] = obs.moneda.fillna('MXN')
FECHA = pd.Timestamp('2026-11-26')

# Piloto PROFECO como observaciones con la misma estructura
c = sqlite3.connect(f"file:{(corte/'piloto_profeco_intradia.sqlite3').as_posix()}?mode=ro", uri=True)
p = pd.read_sql("select d.offer_id, d.fecha_precio, d.precio, d.condiciones_json, c.fetched_at_utc, o.producto_id, o.vendedor "
                "from observaciones_diarias_fuente d join capturas c using(capture_id) join ofertas o using(offer_id) "
                "where o.fuente='profeco_buen_fin'", c)
p = p.sort_values('fetched_at_utc').groupby(['offer_id', 'fecha_precio']).tail(1)
desc = p.condiciones_json.map(lambda s: json.loads(s).get('descripcion'))
piloto = pd.DataFrame(dict(fuente='profeco_bf2026', serie_id=p.offer_id, fecha_precio=p.fecha_precio, precio=p.precio,
                           id_externo=p.producto_id, canal='tienda_fisica', moneda='MXN', vendedor_serie=p.vendedor,
                           vendedor_o_cadena=p.vendedor, descripcion_original=desc))

series = H.preparar_series(pd.concat([obs[['fuente', 'serie_id', 'fecha_precio', 'precio', *H.METADATOS]], piloto]), eventos, FECHA)
fin = lambda d: np.isfinite(d[H.VARIABLES].astype(float)).all(axis=1)

# Modelo fijado: mismo dominio, mismos hiperparámetros y semilla que v2_history.modelo_supervisado
dom = series.loc[series[['fuente', 'canal', 'moneda']].eq(H.DOMINIO).all(axis=1)]
apt = dom.loc[dom.minimos_previos & fin(dom)]
train = apt.loc[apt.evento_id.eq('BF2024') & apt.resultado_observado]
test25 = apt.loc[apt.evento_id.eq('BF2025') & apt.resultado_observado]
modelos = {'arbol_2': DecisionTreeClassifier(max_depth=2, min_samples_leaf=10, random_state=H.SEMILLA),
           'regresion_logistica': make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=1000))}
for m in modelos.values():
    m.fit(train[H.VARIABLES], train.etiqueta_bajo.astype(int))

def metricas(nombre, d):
    y = d.etiqueta_bajo.astype(int).to_numpy()
    filas = []
    for k, m in modelos.items():
        pr = m.predict(d[H.VARIABLES])
        tn, fp, fn, tp = confusion_matrix(y, pr, labels=[0, 1]).ravel()
        filas.append(dict(conjunto=nombre, modelo=k, n=len(y), positivos=int(y.sum()), productos=d.id_externo.nunique(),
                          acc=accuracy_score(y, pr), bal_acc=balanced_accuracy_score(y, pr),
                          prec=precision_score(y, pr, zero_division=0), rec=recall_score(y, pr, zero_division=0),
                          f1=f1_score(y, pr, zero_division=0), tn=tn, fp=fp, fn=fn, tp=tp))
    base = np.ones_like(y)
    filas.append(dict(conjunto=nombre, modelo='clase_mayoritaria(1)', n=len(y), positivos=int(y.sum()),
                      productos=d.id_externo.nunique(), acc=accuracy_score(y, base), bal_acc=balanced_accuracy_score(y, base),
                      prec=precision_score(y, base, zero_division=0), rec=1.0, f1=f1_score(y, base, zero_division=0)))
    return filas

res = metricas('prueba_BF2025_QQP (reproducción)', test25)

# 2026 estricto: piloto PROFECO con los mismos mínimos del protocolo
s26 = series.loc[series.evento_id.eq('BF2026') & fin(series)]
pil = s26.loc[s26.fuente.eq('profeco_bf2026') & s26.resultado_observado]
res += metricas('BF2026 piloto PROFECO (estricto)', pil)

# 2026 relajado: mínimo multitienda de Preciómetro. Su "vendedor" cambia, por eso el protocolo lo excluye;
# se relaja sólo la identidad de sucursal, manteniendo mínimos de fechas y amplitud.
rel = s26.loc[s26.fuente.eq('preciometro') & s26.amplitud_base_dias.ge(H.MIN_AMPLITUD) & s26.n_base.ge(H.MIN_BASE)
              & s26.n_previo.ge(H.MIN_PREVIO) & s26.n_evento.ge(H.MIN_EVENTO)].copy()
rel['etiqueta_bajo'] = rel.bajada_evento_mxn.gt(0).astype(int)
res += metricas('BF2026 Preciómetro mínimo multitienda (identidad relajada)', rel)

pd.set_option('display.width', 250)
print(f"Mínimos: base>={H.MIN_BASE} fechas, amplitud>={H.MIN_AMPLITUD} d, previo>={H.MIN_PREVIO}, evento>={H.MIN_EVENTO}")
print(f"Entrenamiento BF2024 n={len(train)}")
print(pd.DataFrame(res).round(3).to_string(index=False))
print('\nPreciómetro BF2026 candidatos:', int(s26.fuente.eq('preciometro').sum()),
      '· con n_evento>=1:', int((s26.fuente.eq('preciometro') & s26.n_evento.ge(1)).sum()))
print('Clase en Preciómetro relajado: bajó', int(rel.etiqueta_bajo.sum()), 'de', len(rel),
      '· cambio mediano evento vs previo %:', round(float(rel.bajada_evento_pct.median()), 2))
