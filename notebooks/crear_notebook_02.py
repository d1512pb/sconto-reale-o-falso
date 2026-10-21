"""Genera notebooks/02_Sconto_multifuente.ipynb (CRISP-DM). Ejecutar: python notebooks/crear_notebook_02.py [--ejecutar]"""
from pathlib import Path
import sys
import textwrap

import nbformat as nbf

AQUI = Path(__file__).resolve().parent
cells = []
def md(s): cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(s).strip()))
def code(s): cells.append(nbf.v4.new_code_cell(textwrap.dedent(s).strip()))

md('''
# Sconto reale o falso
## 02 · Precios multifuente y Buen Fin (CRISP-DM)
**ESCOM-IPN · Minería de Datos** · Daniel Peredo Borgonio · Kevin Celis Torres · Igor Cappelli

Este cuaderno continúa el Avance 1 (PROFECO QQP 2025, CDMX). Añade fuentes en línea, más eventos
(Buen Fin 2024, 2025 y 2026), análisis por día y, cuando existe, el **precio anunciado o tachado**.
Sigue las fases de CRISP-DM: negocio → datos → preparación → modelado → evaluación → despliegue.

**Para correrlo en Colab:** Entorno de ejecución → Ejecutar todo. Sólo necesita CPU y lee los datos
publicados en GitHub (no depende de archivos locales ni de credenciales).
''')
md('''
## 1. Comprensión del negocio
Una promoción puede anunciar una rebaja frente a un “precio anterior” sin que el comprador ahorre respecto del
precio habitual. Medimos tres cosas por serie (producto × vendedor o sucursal × canal) y por evento:

- **Ahorro histórico** = 100 × (1 − mediana del evento / mediana de la base).
- **Alza previa** = 100 × (mediana del previo / mediana de la base − 1).
- **Brecha** = descuento anunciado − ahorro histórico, en puntos porcentuales, sólo si hay anuncio.

Ventanas relativas al primer día del evento (D0): base D-60..D-15, previo D-14..D-1, evento D0..último día.
Un precio anunciado **no prueba engaño**: la etiqueta “descuento inflado” es una regla (brecha > 5, 10 o 15 pp),
derivada y no verificada; por eso no se entrena un clasificador supervisado con ella.
''')
code('''
import os, json, io, hashlib, zipfile
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display

REPO = 'd1512pb/sconto-reale-o-falso'
REL = f'https://github.com/{REPO}/releases/download/datos/'
LOCAL = os.environ.get('SCONTO_GOLD_LOCAL')  # sólo para probar el cuaderno antes de publicar
TABLAS = {}
if not LOCAL:
    respuesta = requests.get(REL + 'sconto_colab_actual.zip', timeout=180)
    respuesta.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(respuesta.content)) as paquete:
        manifiesto = json.loads(paquete.read('paquete.json'))
        for nombre, descripcion in manifiesto['tablas'].items():
            contenido = paquete.read(descripcion['archivo'])
            if hashlib.sha256(contenido).hexdigest() != descripcion['sha256']:
                raise ValueError(f'Archivo alterado: {nombre}')
            tabla = pd.read_parquet(io.BytesIO(contenido))
            if len(tabla) != descripcion['filas']:
                raise ValueError(f'Filas incorrectas: {nombre}')
            TABLAS[nombre] = tabla

def leer(nombre, release=False):
    if LOCAL:
        return pd.read_parquet(os.path.join(LOCAL, nombre + '.parquet'))
    return TABLAS[nombre].copy()

obs = leer('observaciones', release=True)
productos = leer('productos'); eventos = leer('eventos'); se = leer('series_evento')
sens = leer('sensibilidad'); X = leer('matriz_modelo'); meta = leer('metadatos_modelo')
obs['fecha_precio'] = pd.to_datetime(obs.fecha_precio)
for c in [c for c in eventos.columns if c.endswith(('_inicio', '_fin')) or c in ('d0', 'fin')]:
    eventos[c] = pd.to_datetime(eventos[c])
print('Origen de datos:', LOCAL or 'GitHub')
print(f'{len(obs):,} observaciones · {obs.fuente.nunique()} fuentes · {len(productos):,} productos · {len(se):,} series×evento')
''')
md('''
## 2. Comprensión de los datos
### 2.1 Qué aporta cada fuente
`metodo` distingue archivo oficial, API, scraping, agregador, archivo web (Wayback / Common Crawl) y comunidad.
`canal` separa tienda física (QQP) de venta en línea: nunca se fusionan en una misma serie.
''')
code('''
resumen = obs.groupby(['fuente', 'metodo', 'canal']).agg(
    filas=('precio', 'size'), productos=('producto_canonico_id', 'nunique'), series=('serie_id', 'nunique'),
    desde=('fecha_precio', 'min'), hasta=('fecha_precio', 'max'), dias=('fecha_precio', 'nunique'),
    con_tachado=('precio_anterior_anunciado', 'count'), con_pct=('pct_descuento_anunciado', 'count'))
display(resumen)
''')
md('''
### 2.2 Cobertura por día
Cada celda indica si hubo al menos un precio ese día. Los huecos son faltantes reales: no se imputan.
''')
code('''
def heatmap_cobertura(df, titulo, max_productos=60):
    d = df.dropna(subset=['producto_canonico_id'])
    top = d.groupby('producto_canonico_id').fecha_precio.nunique().nlargest(max_productos).index
    m = (d.loc[d.producto_canonico_id.isin(top)].assign(v=1)
           .pivot_table(index='producto_canonico_id', columns='fecha_precio', values='v', aggfunc='max'))
    if m.empty:
        print('Sin datos para', titulo); return
    fig, ax = plt.subplots(figsize=(14, max(3, len(m) * 0.12)))
    ax.imshow(m.notna().to_numpy(), aspect='auto', cmap='Blues', interpolation='nearest')
    ticks = np.linspace(0, m.shape[1] - 1, min(12, m.shape[1])).astype(int)
    ax.set_xticks(ticks, [m.columns[i].strftime('%Y-%m-%d') for i in ticks], rotation=45, ha='right', fontsize=7)
    ax.set_yticks([]); ax.set_ylabel(f'{len(m)} productos (los de más días)'); ax.set_title(titulo)
    plt.tight_layout(); plt.show()

for fuente, g in obs.groupby('fuente'):
    heatmap_cobertura(g, f'Cobertura producto × día · {fuente}')
''')
md('''
### 2.3 Evolución temporal con las ventanas del Buen Fin
Se grafican productos con varias fuentes. Las franjas marcan base (gris), previo (naranja) y evento (rojo).
''')
code('''
def franjas(ax, desde, hasta):
    for ev in eventos.itertuples():
        for ini, fin, color in [(ev.base_inicio, ev.base_fin, '0.9'), (ev.previo_inicio, ev.previo_fin, '#fde3c8'),
                                (ev.evento_inicio, ev.evento_fin, '#f7b6b6')]:
            if fin >= desde and ini <= hasta:
                ax.axvspan(ini, fin, color=color, zorder=0)

multi = obs.dropna(subset=['producto_canonico_id']).groupby('producto_canonico_id').plataforma_serie.nunique()
ejemplos = multi.loc[multi.ge(2)].index[:6]
for pid in ejemplos:
    d = obs.loc[obs.producto_canonico_id.eq(pid)]
    fig, ax = plt.subplots(figsize=(12, 3.2))
    franjas(ax, d.fecha_precio.min(), d.fecha_precio.max())
    for plat, g in d.groupby('plataforma_serie'):
        diario = g.groupby('fecha_precio').precio.median()
        ax.plot(diario.index, diario.values, marker='.', lw=1, label=plat)
    desc = productos.set_index('producto_canonico_id').reindex([pid]).descripcion_qqp.fillna('').iloc[0][:90]
    ax.set(title=f'{pid} · {desc}', ylabel='MXN (mediana diaria)'); ax.legend(fontsize=7)
    plt.tight_layout(); plt.show()
''')
md('''
## 3. Preparación de los datos
Por serie y evento se calculan medianas por ventana con los mismos mínimos del Avance 1: ≥4 fechas base en ≥21 días
y ≥1 fecha del evento para el ahorro; además ≥2 fechas del previo para el alza. La tabla de sensibilidad muestra
cuántas series quedan exigiendo 2, 3, 4 o 5 fechas base.
''')
code('''
cob = se.groupby(['evento_id', 'plataforma_serie']).agg(
    series=('serie_id', 'size'), cobertura_ahorro=('cobertura_ahorro', 'sum'),
    cobertura_alza=('cobertura_alza', 'sum'), con_anuncio=('descuento_anunciado_pct', 'count'),
    con_brecha=('brecha_pp', 'count'), mediana_ahorro=('ahorro_historico_pct', 'median'))
display(cob)
display(sens.pivot_table(index=['evento_id', 'plataforma_serie'], columns='min_fechas_base',
                         values='series_cobertura_ahorro', aggfunc='sum'))
''')
md('''
**Comprobación de reproducibilidad.** Con QQP 2025 (CDMX) deben salir exactamente las 298 series de ahorro y 93 de
alza del Avance 1.
''')
code('''
bf25 = se.loc[se.evento_id.eq('BF2025') & se.plataforma_serie.eq('qqp_cdmx')]
print('QQP BF2025 · ahorro:', int(bf25.cobertura_ahorro.sum()), '· alza:', int(bf25.cobertura_alza.sum()))
assert int(bf25.cobertura_ahorro.sum()) == 298 and int(bf25.cobertura_alza.sum()) == 93
''')
md('''
### 3.1 Anunciado vs. histórico
Sólo donde hay a la vez cobertura de ahorro y un anuncio (precio tachado o % mostrado durante el evento).
''')
code('''
br = se.dropna(subset=['brecha_pp'])
print(f'{len(br)} series con brecha calculable')
if len(br):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(br.ahorro_historico_pct, br.descuento_anunciado_pct, s=14, alpha=.7)
    lim = [min(br.ahorro_historico_pct.min(), 0) - 5, max(br.descuento_anunciado_pct.max(), 50) + 5]
    ax.plot(lim, lim, 'k--', lw=.8, label='anunciado = histórico')
    ax.set(xlabel='Ahorro histórico (%)', ylabel='Descuento anunciado (%)', title='Anunciado vs. histórico'); ax.legend()
    plt.tight_layout(); plt.show()
    display(br.groupby(['evento_id', 'plataforma_serie'])[[f'regla_descuento_inflado_{u}pp' for u in (5, 10, 15)]]
              .mean().mul(100).round(1).add_suffix(' (% de series)'))
''')
md('''
## 4. Modelado: Isolation Forest
Detección de anomalías no supervisada: separa observaciones con cortes aleatorios; las que se aíslan con pocos
cortes son poco comunes. Semilla fija para que el resultado se repita. El puntaje **no** es una probabilidad de fraude.
Los identificadores no entran como variables.
''')
code('''
from sklearn.ensemble import IsolationForest
SEMILLA = 42
Xm = X.dropna()
modelo = IsolationForest(n_estimators=500, contamination='auto', random_state=SEMILLA).fit(Xm)
puntaje = pd.Series(-modelo.score_samples(Xm), index=Xm.index, name='puntaje_anomalia')
res = Xm.join(puntaje).join(meta[['evento_id', 'plataforma_serie', 'producto_canonico_id', 'vendedor_serie',
                                  'descripcion_original', 'n_base', 'n_previo', 'n_evento']])
print(len(res), 'series en el modelo'); display(res.groupby(['evento_id', 'plataforma_serie']).size())
display(res.sort_values('puntaje_anomalia', ascending=False).head(15).round(2))
''')
md('''
**Revisión manual.** Los casos de mayor puntaje se revisan uno por uno (descripción, vendedor, fechas y precios);
un puntaje alto puede deberse a un alza previa, a una rebaja muy grande o a un error de captura.
''')
code('''
def detalle(serie_evento_id):
    r = meta.loc[serie_evento_id]
    d = obs.loc[obs.serie_id.eq(r.serie_id)].sort_values('fecha_precio')
    ev = eventos.set_index('evento_id').loc[r.evento_id]
    d = d.loc[d.fecha_precio.between(ev.base_inicio, ev.posterior_fin)]
    fig, ax = plt.subplots(figsize=(10, 2.8)); franjas(ax, d.fecha_precio.min(), d.fecha_precio.max())
    ax.plot(d.fecha_precio, d.precio, marker='o', lw=1)
    ax.set(title=f'{r.evento_id} · {str(r.descripcion_original)[:80]} · {r.vendedor_serie}', ylabel='MXN')
    plt.tight_layout(); plt.show()

for sid in res.sort_values('puntaje_anomalia', ascending=False).head(5).index:
    detalle(sid)
''')
md('''
## 5. Evaluación: comparación con reglas simples
Sin etiquetas verificadas no se reporta exactitud. Se compara el ordenamiento del modelo con reglas transparentes:
(a) sin ahorro (ahorro ≤ 0), (b) alza previa > 5 %, (c) brecha > 10 pp cuando existe.
''')
code('''
reglas = pd.DataFrame({'sin_ahorro': res.ahorro_historico_pct.le(0), 'alza_previa_5': res.alza_previa_pct.gt(5)})
reglas['brecha_10'] = se.set_index('serie_evento_id').reindex(res.index).regla_descuento_inflado_10pp
top = res.puntaje_anomalia.rank(ascending=False).le(max(5, int(len(res) * .1)))
comp = pd.DataFrame({r: {'casos_regla': int(reglas[r].fillna(False).sum()),
                         'en_top10%_modelo': int((reglas[r].fillna(False) & top).sum())} for r in reglas}).T
display(comp)
print('Correlación de Spearman puntaje vs. alza previa:',
      round(res.puntaje_anomalia.corr(res.alza_previa_pct, method='spearman'), 3))
''')
md('''
## 6. Despliegue
- El colector diario corre en GitHub Actions (Preciómetro, Mercado Libre) y en la PC del equipo (Amazon), con una
  pasada diaria y dos del 10 al 20 de noviembre. Cada corrida guarda el crudo con su SHA-256 y registra
  ok / fallo / bloqueado por fuente; una falla dos días seguidos abre una alerta.
- Este cuaderno se vuelve a ejecutar tras el Buen Fin 2026 (13–17 nov) para obtener las series del evento.
- Límites: QQP muestrea días sueltos; el gráfico de Preciómetro es el mínimo entre tiendas (no una sola tienda);
  Mercado Libre exige token para su API; el precio tachado retroactivo de 2024–2025 depende de lo que archivaron
  Wayback y Common Crawl. Ver `reports/resumen_recoleccion.md` del repositorio.
''')

nb = nbf.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.11'},
    'colab': {'name': '02_Sconto_multifuente.ipynb', 'provenance': []}})
nbf.validate(nb)
destino = AQUI / '02_Sconto_multifuente.ipynb'
if '--ejecutar' in sys.argv:
    from nbclient import NotebookClient
    NotebookClient(nb, timeout=900, kernel_name='python3').execute()
nbf.write(nb, destino)
print(destino)
