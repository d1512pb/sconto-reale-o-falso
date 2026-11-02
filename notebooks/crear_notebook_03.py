"""Genera el Colab del Avance 2 con código y datos fijados en config/avance2.json."""
from pathlib import Path
import json
import textwrap

import nbformat as nbf

RAIZ = Path(__file__).resolve().parents[1]
config = json.loads((RAIZ / 'config/avance2.json').read_text(encoding='utf-8'))
cells = []


def md(texto):
    cells.append(nbf.v4.new_markdown_cell(textwrap.dedent(texto).strip()))


def code(texto):
    cells.append(nbf.v4.new_code_cell(textwrap.dedent(texto).strip()))


md('''
# Sconto reale o falso · Avance 2
## CRISP-DM: de precios observados a una herramienta de consulta
**ESCOM-IPN · Minería de Datos** · Daniel Peredo Borgonio, Kevin Celis Torres e Igor Cappelli

Este cuaderno continúa el Avance 1 y produce los datos que consume la miniweb Sconto.
En Colab: **Entorno de ejecución → Ejecutar todo**, con CPU. No necesita tokens ni GPU.
Conserva el cuaderno 01 como evidencia del primer avance.

El snapshot y el código están fijados por SHA-256 y revisión Git. No se descargan precios al ejecutar
una consulta en la web: los colectores generan gold, este análisis genera el mart y la web lo lee.
La captura automatizada corre fuera de Colab porque su sesión no es un servicio permanente.
''')
md('''
## 1. Comprensión del negocio
**Problema:** el porcentaje anunciado no necesariamente refleja ahorro frente al precio habitual.
**Usuario:** una persona que compara un producto de tecnología antes de comprar durante el Buen Fin.
**Entrega:** historial por serie, referencia de precio y casos que requieren revisión; nunca un veredicto de fraude.

Durante noviembre de 2026, la consulta contrasta un precio con la base histórica disponible.
El análisis retrospectivo BF2024/BF2025 permite evaluar el método con eventos terminados.
**BF2026 no recibe puntajes de evento antes de terminar.**

Criterios de aceptación: reproducir Avance 1 (39,363 / 298 / 93), conservar canales y variantes,
explicar faltantes y conseguir una exportación SQLite verificable que la web pueda consumir.
Sin etiquetas independientes de engaño, no es válido reportar accuracy, precisión o recall de fraude.
''')
code('''
import os, sys, json, hashlib, subprocess, io, zipfile
from pathlib import Path
''')
code('CONFIG = ' + repr(config))
code('''
LOCAL = os.environ.get('SCONTO_LOCAL_REPO')  # sólo para verificación del equipo
if not LOCAL:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *CONFIG['dependencias']])
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display

BASE = Path(os.environ.get('SCONTO_TRABAJO', 'sconto_avance2')).resolve()
BASE.mkdir(parents=True, exist_ok=True)
runtime = BASE / 'runtime'
raw = f"https://raw.githubusercontent.com/{CONFIG['repo']}/{CONFIG['revision_codigo']}/"
for relativo, digest in CONFIG['archivos_codigo'].items():
    contenido = (Path(LOCAL) / relativo).read_bytes() if LOCAL else requests.get(raw + relativo, timeout=60).content
    assert hashlib.sha256(contenido).hexdigest() == digest, f'Código distinto: {relativo}'
    destino = runtime / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
(runtime / 'src/sconto/__init__.py').write_text('', encoding='utf-8')
sys.path.insert(0, str(runtime / 'src'))
os.environ['GITHUB_SHA'] = CONFIG['revision_codigo']
from sconto.colab import cargar_paquete
from sconto.mart import ejecutar, guardar_sqlite
from sconto.consulta import evaluar_oferta

paquete = BASE / CONFIG['snapshot']['archivo']
entrada_local = os.environ.get('SCONTO_PAQUETE_LOCAL')
if entrada_local:
    contenido = Path(entrada_local).read_bytes()
elif paquete.exists():
    contenido = paquete.read_bytes()
else:
    respuesta = requests.get(CONFIG['snapshot']['url'], timeout=240)
    respuesta.raise_for_status()
    contenido = respuesta.content
assert hashlib.sha256(contenido).hexdigest() == CONFIG['snapshot']['sha256_zip'], 'Snapshot incorrecto'
paquete.write_bytes(contenido)
gold = cargar_paquete(paquete)
print('Código:', CONFIG['revision_codigo'])
print('Snapshot:', CONFIG['snapshot']['archivo'])
print('SHA-256 verificado:', CONFIG['snapshot']['sha256_zip'])
''')
md('''
## 2. Comprensión de los datos
QQP contiene tiendas físicas; los agregadores y tiendas web contienen precios en línea.
El mínimo diario multitienda no es el historial de un vendedor. Cada fuente conserva su identidad;
los cruces probables de modelo/variante no se usan como coincidencias exactas.

Las fuentes sin filas no se presentan como integradas. El piloto de Amazon directo es antiguo y está
desactivado; INEGI y API de Mercado Libre todavía no aportan filas. La expansión diaria es una lista fija.
''')
code('''
obs = gold['observaciones'].copy()
obs['fecha_precio'] = pd.to_datetime(obs.fecha_precio)
resumen = obs.groupby(['fuente', 'canal']).agg(filas=('obs_id', 'size'), productos=('id_externo', 'nunique'),
    inicio=('fecha_precio', 'min'), fin=('fecha_precio', 'max'), dias=('fecha_precio', 'nunique'),
    con_tachado=('precio_anterior_anunciado', 'count')).reset_index()
display(resumen)
display(pd.DataFrame({'tabla': gold.keys(), 'filas': [len(t) for t in gold.values()]}))
por_dia = obs.groupby(['fecha_precio', 'fuente']).size().unstack(fill_value=0)
ax = por_dia.plot(figsize=(13, 4), logy=True, title='Cobertura diaria por fuente (escala logarítmica)')
ax.set_ylabel('Observaciones; ceros de cobertura no son precios'); plt.show()

seleccion = pd.read_csv(runtime / 'config/preciometro_diarios.csv', dtype=str)
minimos = obs.loc[obs.fuente.eq('preciometro') & obs.producto_canonico_id.isin(seleccion.producto_canonico_id)]
calendario = pd.date_range(minimos.fecha_precio.min(), minimos.fecha_precio.max())
cobertura = minimos.groupby(['producto_canonico_id', 'fecha_precio']).size().unstack(fill_value=0)
cobertura = cobertura.reindex(index=seleccion.producto_canonico_id, columns=calendario, fill_value=0).gt(0)
fig, ax = plt.subplots(figsize=(14, 6))
ax.imshow(cobertura, aspect='auto', interpolation='nearest', cmap='Greens', vmin=0, vmax=1)
ticks = np.arange(0, len(calendario), max(1, len(calendario)//8))
ax.set_xticks(ticks, calendario[ticks].strftime('%d %b'), rotation=30)
ax.set_ylabel('200 productos de la lista diaria'); ax.set_title('Dato observado por producto y día')
plt.show()
print('Este mapa representa presencia/ausencia; no se rellenó ningún precio faltante.')
''')
md('''
## 3. Preparación y control del ETL
Serie = producto × vendedor/sucursal × canal (con fuente/plataforma y tipo de precio conservados).
Una observación repetida entre ambientes se consolida en gold; no se inventan días.
Para graficar se conserva la mediana de las observaciones de un mismo día, sin unir variantes.

Base D−60..D−15; previo D−14..D−1; evento D0..último día; posterior 14 días, sólo diagnóstico.
Mínimos: ≥4 fechas base con ≥21 días de amplitud; ≥1 fecha del evento; ≥2 fechas del previo para alza.
La sensibilidad de cobertura usa 2, 3, 4 y 5 fechas. Los extremos se revisan y no se eliminan por ser grandes.
''')
code('''
se = gold['series_evento']
qqp25 = obs.loc[obs.fuente.eq('qqp_cdmx') & obs.fecha_precio.dt.year.eq(2025)]
bf25 = se.loc[se.evento_id.eq('BF2025') & se.plataforma_serie.eq('qqp_cdmx')]
assert len(qqp25) == 39363
assert int(bf25.cobertura_ahorro.sum()) == 298
assert int(bf25.cobertura_alza.sum()) == 93
assert obs.precio.gt(0).all()
assert not obs.obs_id.duplicated().any()
assert obs.groupby('serie_id').canal.nunique().le(1).all()
assert list(gold['matriz_modelo'].columns) == ['ahorro_historico_pct', 'alza_previa_pct', 'variabilidad_base_pct']
print('Avance 1 reproducido: 39,363 observaciones / 298 series de ahorro / 93 de alza.')
display(gold['sensibilidad'])
print('Series con brecha disponible:', int(se.brecha_pp.notna().sum()))
if not se.brecha_pp.notna().any():
    print('No se puede evaluar aún la promesa de descuento con historia de la misma serie y evento.')
''')
md('''
## 4. Modelado
Isolation Forest de 300 árboles, semilla 42, sobre ahorro histórico, alza previa y variabilidad base.
Sólo **QQP CDMX y canal físico**: entrenamiento BF2024 y evaluación temporal BF2025.
No entran IDs, fecha posterior, etiquetas derivadas ni BF2026 incompleto. La brecha queda fuera por falta de muestra.

Puntaje = −score_samples: mayor valor, más inusual. El percentil 90 del entrenamiento define una cola
para revisión y no una probabilidad de fraude. Las reglas simples son ahorro ≤0 y alza previa >5%.
Se informa el solapamiento de productos entre años; no se afirma independencia por producto.
''')
code('''
SALIDA = BASE / 'entrega_web'
gold, tablas, analisis, manifest = ejecutar(paquete, runtime / 'config/preciometro_diarios.csv', SALIDA)
display(pd.Series(analisis['tarjeta'], name='Tarjeta del modelo').to_frame())
ranking = tablas['resultados_modelo']
assert not ranking.evento_id.eq('BF2026').any(), 'No puntuar un evento futuro/incompleto'
display(ranking.head(20))
fig, ax = plt.subplots(figsize=(10, 5))
for etapa, grupo in ranking.groupby('etapa'):
    ax.scatter(grupo.ahorro_historico_pct, grupo.alza_previa_pct, label=etapa, alpha=.65,
               s=20 + 80 * grupo.puntaje_anomalia)
ax.axhline(5, color='gray', linestyle=':'); ax.axvline(0, color='gray', linestyle=':')
ax.set(xlabel='Ahorro histórico (%)', ylabel='Alza previa (%)', title='Casos históricos; tamaño = rareza')
ax.legend(); plt.show()
''')
md('''
## 5. Evaluación y revisión humana
No hay verdad independiente de fraude. Evaluamos estabilidad del ranking con semillas 7/42/101,
coincidencia con reglas, sensibilidad del umbral y cobertura. Estos valores no son exactitud.
Los 20 casos exportados necesitan revisar variante, crudo/precio y contexto comercial antes de redactar conclusiones.
''')
code('''
display(tablas['evaluacion_modelo'])
display(analisis['revision'][['evento_id', 'descripcion_original', 'vendedor_serie', 'puntaje_anomalia', 'revision_humana']])
eventos = gold['eventos'].copy()
for c in eventos.columns:
    if c in ['d0', 'fin'] or c.endswith(('_inicio', '_fin')):
        eventos[c] = pd.to_datetime(eventos[c])
prueba = ranking.loc[ranking.etapa.eq('validacion_temporal')]
caso = prueba.iloc[0] if len(prueba) else ranking.iloc[0]
evento = eventos.set_index('evento_id').loc[caso.evento_id]
puntos = obs.loc[obs.serie_id.eq(caso.serie_id) & obs.fecha_precio.between(evento.base_inicio, evento.posterior_fin)]
fig, ax = plt.subplots(figsize=(13, 4))
for nombre, color in [('base', '#dbeafe'), ('previo', '#fef3c7'), ('evento', '#dcfce7'), ('posterior', '#f3e8ff')]:
    ax.axvspan(evento[nombre+'_inicio'], evento[nombre+'_fin'], color=color, label=nombre)
ax.scatter(puntos.fecha_precio, puntos.precio, color='#111827', s=18)
ax.set(title=f'{caso.evento_id}: {caso.descripcion_original}', ylabel='MXN', xlabel='Días observados')
ax.legend(); plt.show()
print('Serie:', caso.serie_id, '· vendedor/sucursal:', caso.vendedor_serie)
print('El posterior sólo se muestra como diagnóstico y puede coincidir con Black Friday/Cyber Monday.')
''')
md('''
## 6. Despliegue: contrato para la miniweb
El despliegue consiste en entregar un mart versionado y una consulta que usa la evidencia disponible.
**No se aloja la web en Colab.** SQLite y JSON se generan con el mismo código que usa la tarea diaria de GitHub.

`sconto_web.zip` contiene 11 tablas en Parquet/CSV.gz, SQLite con claves primarias y foráneas,
feed JSON, tarjeta de modelo, cola de revisión y manifiesto SHA-256.
La miniweb lee SQLite; una futura API puede usar el mismo contrato. Los precios escritos por el usuario no se guardan.

Se distingue referencia de mínimos multitienda, historial del mismo vendedor y evidencia insuficiente.
Un tachado permite calcular la rebaja implícita del anuncio; no demuestra ahorro histórico.
El análisis de una consulta tampoco sustituye las medianas del evento.
''')
code('''
import sqlite3
from contextlib import closing
with closing(sqlite3.connect(SALIDA / 'sconto_web.sqlite')) as cn:
    assert cn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert cn.execute('PRAGMA foreign_key_check').fetchall() == []
    for nombre, n in manifest['tablas'].items():
        assert cn.execute(f'SELECT COUNT(*) FROM "{nombre}"').fetchone()[0] == n
for nombre, digest in manifest['archivos'].items():
    assert hashlib.sha256((SALIDA / nombre).read_bytes()).hexdigest() == digest
display(pd.DataFrame(manifest['tablas'].items(), columns=['tabla', 'filas']))
print('Corte:', manifest['fecha_corte'], '· Fuente:', manifest['fuente'])
print('Exportación verificada:', SALIDA / 'sconto_web.zip')
print('Revisar manualmente:', SALIDA / 'casos_para_revision.csv')
modo = 'local' if LOCAL else 'Colab' if 'google.colab' in sys.modules else 'otro Python'
auditoria = dict(entorno=modo, revision_codigo=CONFIG['revision_codigo'], snapshot=CONFIG['snapshot'],
                 fecha_corte=manifest['fecha_corte'], tablas=manifest['tablas'],
                 validacion_avance1=[39363, 298, 93], revision_humana='pendiente')
(BASE / 'auditoria_ejecucion.json').write_text(json.dumps(auditoria, ensure_ascii=False, indent=2), encoding='utf-8')
print('Ejecución registrada como:', modo)
''')
code('''
# Cambiar a True sólo si deseas descargar la entrega desde una sesión de Colab.
DESCARGAR = False
GUARDAR_EN_DRIVE = False
if GUARDAR_EN_DRIVE:
    from google.colab import drive
    import shutil
    drive.mount('/content/drive')
    destino = Path('/content/drive/MyDrive/Sconto/entregas_avance2')
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SALIDA / 'sconto_web.zip', destino / f"sconto_web_{manifest['fecha_corte']}.zip")
    shutil.copy2(BASE / 'auditoria_ejecucion.json', destino / 'auditoria_ejecucion.json')
if DESCARGAR:
    from google.colab import files
    files.download(str(SALIDA / 'sconto_web.zip'))
''')
md('''
### Operación y pendientes para el segundo avance
1. Igor y Kevin revisan `casos_para_revision.csv` y las coincidencias de variante. La revisión sigue pendiente.
2. El equipo documenta qué hallazgos quedan respaldados por fuentes y cuáles son sólo señales.
3. GitHub ejecuta el mismo ETL con las nuevas capturas; la web indica el corte y la antigüedad.
4. API de Mercado Libre requiere credenciales y mapeos validados. Amazon directo continúa desactivado.
5. Repetir el análisis BF2026 después de terminar el evento, con los mínimos de cobertura satisfechos.

**Referencias del método y operación:** [Isolation Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html),
[Colab FAQ](https://research.google.com/colaboratory/faq.html),
[repositorio y fuentes](https://github.com/d1512pb/sconto-reale-o-falso).
''')

nb = nbf.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.11'},
    'colab': {'name': '03_Sconto_CRISP_DM_ETL_web.ipynb', 'provenance': []}})
destino = RAIZ / 'notebooks/03_Sconto_CRISP_DM_ETL_web.ipynb'
nbf.write(nb, destino)
print(destino)
