"""Genera el cuaderno CRISP-DM y la demo de consulta."""
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
# Sconto reale o falso · Segundo parcial
**ESCOM-IPN · Minería de Datos · Daniel Peredo Borgonio, Kevin Celis Torres e Igor Cappelli**

De capturas públicas a un buscador de precios: CRISP-DM, ETL, minería, evaluación y salida para la app.
En Colab: **Entorno de ejecución → Ejecutar todo**, CPU, sin claves ni GPU. La primera ejecución descarga
entradas y dependencias; la consolidación tarda varios minutos. El cuaderno 01 se conserva.
La entrega escolar es este notebook y **entrega_sconto.zip**; la demo ocurre aquí.
''')
md('''
## 1. Comprensión del negocio
**Decisión:** elegir dónde comprar una laptop/computadora o audífonos durante el Buen Fin, priorizando
Sears y comparando Liverpool y otras ofertas de la misma variante.
El porcentaje tachado puede diferir del ahorro frente al precio habitual.

Elegimos **CRISP-DM** porque conecta la pregunta de compra, la calidad de los datos, un modelo evaluado
y una salida utilizable; permite regresar a la recolección cuando falta vendedor, variante o historia.

| Fase | Producto verificable |
|---|---|
| Negocio | Pregunta de compra y límites |
| Datos | Fuentes, cobertura y evidencia |
| Preparación | ETL, exclusiones y reproducción del Avance 1 |
| Modelado | Isolation Forest histórico, buscador y reglas |
| Evaluación | Validación temporal, sensibilidad y consultas |
| Despliegue | Tablas, SQLite, JSON y demo |

**Éxito técnico:** reproducir 39,363/298/93 del Avance 1, conservar variantes/canales, contabilizar cada
captura y exportar consultas explicables. **Éxito de uso pendiente:** contrastar resultados con una
compra real durante el evento. Se evalúa precio, no calidad del producto ni fraude.
La app posterior será de consulta sin cuentas. Ante un nombre ambiguo se elige entre candidatos.
''')
code('''
import os, sys, json, hashlib, subprocess, io, zipfile, gzip
from pathlib import Path
''')
code('CONFIG = ' + repr(config))
code('''
LOCAL = os.environ.get('SCONTO_LOCAL_REPO')
if not LOCAL:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *CONFIG['dependencias']])
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display

BASE = Path(os.environ.get('SCONTO_TRABAJO', 'sconto_avance2')).resolve()
runtime = BASE / 'runtime'
BASE.mkdir(parents=True, exist_ok=True)
raw = f"https://raw.githubusercontent.com/{CONFIG['repo']}/{CONFIG['revision_codigo']}/"
for relativo, digest in CONFIG['archivos_codigo'].items():
    if digest == hashlib.sha256(b'').hexdigest():
        contenido = b''
    elif LOCAL:
        contenido = subprocess.check_output(['git', '-C', LOCAL, 'show', CONFIG['revision_codigo'] + ':' + relativo])
    else:
        respuesta = requests.get(raw + relativo, timeout=90)
        respuesta.raise_for_status()
        contenido = respuesta.content
    assert hashlib.sha256(contenido).hexdigest() == digest, relativo
    destino = runtime / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
sys.path.insert(0, str(runtime / 'src'))
os.environ['SCONTO_RAIZ'] = str(runtime)
os.environ['GITHUB_SHA'] = CONFIG['revision_codigo']
from sconto import dataset
from sconto.colab import cargar_paquete
from sconto.cuaderno import cargar_entrada, auditoria_limpieza, comparar_gold
from sconto.mart import preparar_tablas, exportar, registros
from sconto.compra import preparar_compra, consultar

def obtener(especificacion, variable_local):
    ruta = BASE / especificacion['archivo']
    local = os.environ.get(variable_local)
    if local:
        contenido = Path(local).read_bytes()
    elif ruta.exists():
        contenido = ruta.read_bytes()
    else:
        respuesta = requests.get(especificacion['url'], timeout=300)
        respuesta.raise_for_status()
        contenido = respuesta.content
    assert hashlib.sha256(contenido).hexdigest() == especificacion['sha256_zip'], 'Entrada alterada'
    ruta.write_bytes(contenido)
    return ruta

paquete = obtener(CONFIG['snapshot'], 'SCONTO_PAQUETE_LOCAL')
entrada_zip = obtener(CONFIG['entrada'], 'SCONTO_ENTRADA_LOCAL')
referencia_publicada = cargar_paquete(paquete)
entrada, entrada_manifest = cargar_entrada(entrada_zip)
CORTE = entrada_manifest['fecha_corte']
assert entrada_manifest['gold_sha256'] == CONFIG['snapshot']['sha256_zip']
originales = entrada['bronze_observaciones']
print('Corte:', CORTE, '· Código:', CONFIG['revision_codigo'])
print('Entradas y código verificados con SHA-256.')
''')
md('''
## 2. Comprensión y extracción de datos
Los colectores diarios guardan respuestas y extraen filas **bronze**; este cuaderno vuelve a limpiar
todas las capturas del corte. La adquisición programada continúa fuera de Colab, cuya sesión es temporal.
QQP reutiliza la extracción inicial validada en el cuaderno 01; la versión nacional queda separada
del análisis CDMX. Se comprueban las cifras y matrices originales más adelante.

Preciómetro aporta mínimos diarios multitienda y ofertas por vendedor: son dos tipos de evidencia.
Amazon directo sigue desactivado; sus precios recientes llegan por fuentes indirectas.
Una fuente sin filas no se cuenta como integrada. Tener el módulo de una API no implica tener datos.

**Extracción reproducible de ejemplo:** ejecutamos el parser real sobre la proyección pública de
AirPods del 7 de noviembre. Conserva precios, fechas y vendedores, excluye datos de sesión y enlaza
el hash del crudo privado. No solicitamos páginas de tiendas al abrir el notebook.
''')
code('''
from sconto.fuentes.preciometro import parsear
ruta_evidencia = runtime / 'data/evidencia/preciometro/2026-11-07/11008.json.gz'
evidencia = gzip.decompress(ruta_evidencia.read_bytes())
contenido_evidencia = json.loads(evidencia)
historia_extraida, ofertas_extraidas, meta_extraida = parsear(
    evidencia, 'https://preciometro.com/productos/11008',
    'data/evidencia/preciometro/2026-11-07/11008.json.gz',
    contenido_evidencia['sha256_respuesta_original'], fecha_captura=CORTE)
display(ofertas_extraidas[['descripcion_original', 'plataforma', 'vendedor_o_cadena', 'precio', 'url']])
print('Puntos históricos extraídos:', len(historia_extraida), '· ofertas:', len(ofertas_extraidas))
display(originales.groupby('fuente').agg(capturas=('obs_id', 'size'), ids=('id_externo', 'nunique')))
display(originales[['precio', 'precio_anterior_anunciado', 'pct_descuento_anunciado', 'disponibilidad']].isna().mean().rename('proporcion_faltante'))
''')
md('''
## 3. Preparación: ETL desde las capturas extraídas
Validamos precios positivos, dominios, fechas y porcentajes. Cada rechazo lleva motivo.
Consolidamos repeticiones por fuente/ID/día/vendedor conservando la captura más reciente.
Emparejamos identidades nativas o cruces validados; los probables no unen productos de fuentes distintas.
La serie conserva producto/listado, vendedor o sucursal, plataforma, moneda y canal.
El IQR señala revisión; no eliminamos extremos por su magnitud ni imputamos precios o días ausentes.
''')
code('''
validas, exclusiones = dataset.validar(originales, fecha_referencia=CORTE)
obs = dataset.consolidar(validas)
obs = dataset.mapear_productos(obs, entrada['productos'])
obs = dataset.asignar_series(obs)
auditoria_etl = auditoria_limpieza(originales, validas, obs, exclusiones)
display(auditoria_etl)
display(exclusiones.head())
assert comparar_gold(obs, referencia_publicada) == len(obs)
assert not obs.duplicated(['fuente', 'id_externo', 'fecha_precio', 'vendedor_o_cadena']).any()
assert obs.groupby('serie_id').canal.nunique().le(1).all()
print('Observaciones reconstruidas iguales al snapshot publicado:', len(obs))
''')
code('''
eventos = entrada['eventos'].copy()
for campo in eventos.columns:
    if campo in ['d0', 'fin'] or campo.endswith(('_inicio', '_fin')):
        eventos[campo] = pd.to_datetime(eventos[campo])
display(eventos)
series_evento = dataset.series_evento(obs, eventos)
matriz, matriz_brecha, metadatos = dataset.matrices(series_evento)
sensibilidad = dataset.sensibilidad(obs, eventos)
gold = dict(observaciones=obs, exclusiones=exclusiones, productos=entrada['productos'], eventos=eventos,
            series_evento=series_evento, sensibilidad=sensibilidad, matriz_modelo=matriz,
            matriz_modelo_brecha=matriz_brecha, metadatos_modelo=metadatos)
for nombre in ('matriz_modelo', 'matriz_modelo_brecha', 'metadatos_modelo'):
    calculada = gold[nombre].astype(object).where(gold[nombre].notna(), None)
    publicada = referencia_publicada[nombre].astype(object).where(referencia_publicada[nombre].notna(), None)
    pd.testing.assert_frame_equal(calculada, publicada, check_dtype=False, check_exact=True)
qqp25 = obs.loc[obs.fuente.eq('qqp_cdmx') & obs.fecha_precio.dt.year.eq(2025)]
bf25 = series_evento.loc[series_evento.evento_id.eq('BF2025') & series_evento.plataforma_serie.eq('qqp_cdmx')]
assert len(qqp25) == 39363
assert int(bf25.cobertura_ahorro.sum()) == 298
assert int(bf25.cobertura_alza.sum()) == 93
print('Avance 1 reproducido: 39,363 observaciones, 298 series de ahorro, 93 de alza.')
display(sensibilidad)
''')
md('''
Base D−60..D−15, previo D−14..D−1, evento completo y 14 días posteriores de diagnóstico.
Para ahorro: ≥4 fechas base en ≥21 días y ≥1 del evento; para alza, además ≥2 del previo.
Sensibilidad: 2, 3, 4 y 5 fechas base, conservando amplitud. Primero se toman medianas por día
para evitar que más capturas de una fecha le den más peso.

Ahorro = 100 × (1 − mediana_evento / mediana_base);
alza = 100 × (mediana_previo / mediana_base − 1);
variabilidad = 100 × IQR_base / mediana_base.
Brecha = anuncio menos ahorro, sólo en la misma serie con cobertura. Las etiquetas a 5/10/15 pp
son reglas derivadas, no verdad independiente ni etiquetas para entrenar un clasificador.
''')
code('''
resumen_fuentes = obs.groupby(['fuente', 'canal']).agg(
    filas=('obs_id', 'size'), productos=('id_externo', 'nunique'), inicio=('fecha_precio', 'min'),
    fin=('fecha_precio', 'max'), dias=('fecha_precio', 'nunique'), con_tachado=('precio_anterior_anunciado', 'count')).reset_index()
display(resumen_fuentes)
seleccion = pd.read_csv(runtime / 'config/preciometro_diarios.csv', dtype=str)
minimos = obs.loc[obs.fuente.eq('preciometro') & obs.producto_canonico_id.isin(seleccion.producto_canonico_id)]
calendario = pd.date_range(minimos.fecha_precio.min(), minimos.fecha_precio.max())
cobertura = minimos.groupby(['producto_canonico_id', 'fecha_precio']).size().unstack(fill_value=0)
cobertura = cobertura.reindex(index=seleccion.producto_canonico_id, columns=calendario, fill_value=0).gt(0)
fig, ax = plt.subplots(figsize=(13, 5))
ax.imshow(cobertura, aspect='auto', interpolation='nearest', cmap='Greens', vmin=0, vmax=1)
ticks = np.arange(0, len(calendario), max(1, len(calendario)//8))
ax.set_xticks(ticks, calendario[ticks].strftime('%d %b'), rotation=30)
ax.set(title='Presencia de observación por producto y día', ylabel='Lista diaria de 200 productos')
plt.show()
print('Cero significa ausencia en el mapa de cobertura; nunca se rellena un precio con cero.')
''')
md('''
## 4. Modelado
### 4.1 Patrones históricos
Isolation Forest: 300 árboles, semilla 42, tres variables de precio. Entrenamiento BF2024;
validación temporal BF2025, exclusivamente QQP CDMX físico. No entran identificadores ni posterior.
El puntaje −score_samples mide rareza. El percentil 90 del entrenamiento marca casos para revisión.
Se compara con ahorro ≤0 y alza previa >5%; no se interpreta como probabilidad de engaño.
BF2026 incompleto y las ofertas web no reciben ese puntaje. La cuarta variable brecha necesita más muestra.
''')
code('''
tablas, analisis = preparar_tablas(gold, seleccion, CORTE)
display(pd.Series(analisis['tarjeta'], name='Tarjeta del modelo').to_frame())
ranking = tablas['resultados_modelo']
assert not ranking.evento_id.eq('BF2026').any()
display(ranking.head(10))
fig, ax = plt.subplots(figsize=(9, 4))
for etapa, grupo in ranking.groupby('etapa'):
    ax.scatter(grupo.ahorro_historico_pct, grupo.alza_previa_pct, label=etapa, alpha=.6,
               s=20 + 80 * grupo.puntaje_anomalia)
ax.axhline(5, color='gray', linestyle=':'); ax.axvline(0, color='gray', linestyle=':')
ax.set(xlabel='Ahorro histórico (%)', ylabel='Alza previa (%)', title='Casos históricos; tamaño = rareza')
ax.legend(); plt.show()
''')
md('''
### 4.2 Búsqueda y señal de precio para comprar
TF-IDF de fragmentos de 3–5 caracteres y similitud coseno recupera candidatos del catálogo.
Contradicciones explícitas de RAM, capacidad, generación, CPU o color los descartan.
La similitud no crea un emparejamiento exacto entre fuentes. Ante ambigüedad se elige producto.

Ventaja = 100 × (1 − precio / mediana_base). Con base cerrada ≥4 fechas y ≥21 días:
- **Precio favorable:** ventaja ≥5% y precio ≤P25.
- **Precio alto:** sobreprecio ≥5% y precio ≥P75.
- **Sin señal clara:** demás casos comparables.
- **Evidencia insuficiente:** identidad, vigencia (máximo un día), canal, moneda o historia no comparables.

El 5% es una decisión de diseño: se contrasta con 10%. La compatibilidad textual es provisional;
se muestra pendiente confirmar SKU, condición, envío e inventario. El mínimo multitienda es referencia
de mercado, no prueba de inflación de una tienda. La brecha de consulta sólo usa historia del mismo vendedor.
Sin envío verificado se compara precio publicado, nunca un total inventado. Marketplace conserva quién vende.
''')
code('''
compra, buscador = preparar_compra(tablas, CORTE)
display(compra['catalogo_consulta'].groupby(['familia', 'foco_compra']).size().rename('productos').reset_index())
display(buscador.buscar('Lenovo IdeaPad Slim 3 i3 8GB RAM 512GB SSD')[['producto_canonico_id', 'nombre', 'similitud']])
display(buscador.buscar('airpods pro 3')[['producto_canonico_id', 'nombre', 'similitud']])
display(compra['ofertas_evaluadas'].groupby(['contexto_referencia', 'indicador'], dropna=False).size().rename('ofertas'))
''')
md('''
## 5. Evaluación
### 5.1 Modelo y sensibilidad
Medimos estabilidad entre semillas, coincidencia con reglas y tamaños de muestra. Informamos productos
compartidos entre entrenamiento y prueba; no presumimos independencia por producto. Sin etiquetas
independientes no calculamos accuracy, precisión ni recall de engaño. La revisión humana sigue pendiente.
''')
code('''
display(tablas['evaluacion_modelo'])
display(analisis['revision'][['evento_id', 'descripcion_original', 'vendedor_serie', 'puntaje_anomalia', 'revision_humana']])
caso = ranking.loc[ranking.etapa.eq('validacion_temporal')].iloc[0]
evento = eventos.set_index('evento_id').loc[caso.evento_id]
puntos = obs.loc[obs.serie_id.eq(caso.serie_id) & obs.fecha_precio.between(evento.base_inicio, evento.posterior_fin)]
fig, ax = plt.subplots(figsize=(12, 4))
for ventana, color in [('base', '#dbeafe'), ('previo', '#fef3c7'), ('evento', '#dcfce7'), ('posterior', '#f3e8ff')]:
    ax.axvspan(evento[ventana+'_inicio'], evento[ventana+'_fin'], color=color, label=ventana)
ax.scatter(puntos.fecha_precio, puntos.precio, s=20, color='#111827')
ax.set(title=f'{caso.evento_id}: {caso.descripcion_original}', ylabel='MXN', xlabel='Fecha observada')
ax.legend(); plt.show()
print('Vendedor/sucursal:', caso.vendedor_serie, '· posterior sólo diagnóstico: puede coincidir con Black Friday.')
print('Brechas de evento comparables:', int(series_evento.brecha_pp.notna().sum()))
''')
code('''
consultas_prueba = [
    ('airpods pro 3', 'P4-11008'),
    ('Lenovo IdeaPad Slim 3 i3 8GB RAM 512GB SSD', 'P4-11770'),
    ('Lenobo IdeaPad Slim 3 i3 8GB RAM 512GB SSD', 'P4-11770'),
    ('zzzzqqq producto inexistente', None),
]
evaluacion_busqueda = []
for texto, esperado in consultas_prueba:
    respuesta = buscador.buscar(texto)
    ids = respuesta.producto_canonico_id.tolist()
    evaluacion_busqueda.append(dict(consulta=texto, esperado=esperado,
        primero=ids[0] if ids else None, pasa=(esperado in ids[:3] if esperado else not ids)))
evaluacion_busqueda = pd.DataFrame(evaluacion_busqueda)
display(evaluacion_busqueda)
assert evaluacion_busqueda.pasa.all()
print('Casos de aceptación elegidos para la demo; no estiman rendimiento general del buscador.')
alternativa, _ = preparar_compra(tablas, CORTE, umbral=10)
sensibilidad_reglas = compra['ofertas_evaluadas'][['obs_id', 'indicador']].merge(
    alternativa['ofertas_evaluadas'][['obs_id', 'indicador']], on='obs_id', suffixes=('_5', '_10'))
display(pd.crosstab(sensibilidad_reglas.indicador_5, sensibilidad_reglas.indicador_10))
display(compra['revision_identidades'].head(15))
antiguas = consultar('P4-11008', compra, (pd.Timestamp(CORTE) + pd.Timedelta(days=3)).date().isoformat())
assert antiguas.indicador.eq('evidencia_insuficiente').all()
''')
md('''
### 5.2 Demo real: consulta → producto → ofertas → explicación
Cambiar CONSULTA y elegir un ID de la lista. El ejemplo compara precios publicados de Sears y Liverpool;
no afirma disponibilidad actual ni costo total. La gráfica muestra puntos observados, sin rellenar días.
''')
code('''
CONSULTA = 'airpods pro 3'
candidatos = buscador.buscar(CONSULTA)
display(candidatos[['producto_canonico_id', 'nombre', 'similitud']])
PRODUCTO = 'P4-11008'
resultado = consultar(PRODUCTO, compra, CORTE)
departamentales = resultado.loc[resultado.plataforma.str.lower().isin(['sears', 'liverpool'])]
display(departamentales[['plataforma', 'vendedor_o_cadena', 'tipo_vendedor', 'precio', 'fecha_precio',
                        'identidad_oferta', 'indicador', 'ahorro_referencia_pct', 'contexto_referencia', 'url']])
for texto in departamentales.resumen:
    print(texto)
sid = tablas['series'].loc[tablas['series'].producto_canonico_id.eq(PRODUCTO) & tablas['series'].contexto.eq('minimo_multitienda')].serie_id.iloc[0]
historia = tablas['precios_diarios'].loc[tablas['precios_diarios'].serie_id.eq(sid)]
evento = eventos.set_index('evento_id').loc['BF2026']
fig, ax = plt.subplots(figsize=(12, 4))
for ventana, color in [('base', '#dbeafe'), ('previo', '#fef3c7'), ('evento', '#dcfce7')]:
    ax.axvspan(evento[ventana+'_inicio'], evento[ventana+'_fin'], color=color, label=ventana)
ax.scatter(pd.to_datetime(historia.fecha_precio), historia.precio_mediano, s=12, label='Mínimo multitienda observado')
ax.axvline(pd.Timestamp(CORTE), linestyle=':', color='black', label='Corte')
ax.set(title='AirPods Pro 3 · referencia de mercado', ylabel='MXN', xlabel='Fecha')
ax.legend(); plt.show()
display(consultar('P4-11770', compra, CORTE)[['plataforma', 'vendedor_o_cadena', 'precio', 'identidad_oferta', 'indicador', 'resumen']])
''')
md('''
## 6. Despliegue: datos listos para la app instalable
El notebook entrega datos versionados. La instalación y la interfaz móvil se desarrollarán después.
El consumidor usa catálogo/búsqueda, ofertas por vendedor, historial, referencia, indicador y explicación.
SQLite conserva claves y JSON permite consultar sin ejecutar Python en el teléfono.

La app debe recalcular antigüedad con su fecha de consulta y ocultar indicadores de ofertas vencidas.
La compatibilidad textual no equivale a SKU confirmado. El corte congelado reproduce la clase; la actualización
diaria debe volver a ejecutar el ETL y actualizar el manifiesto sin modificar este snapshot escolar.
''')
code('''
SALIDA = BASE / 'entrega_app'
tablas.update(compra)
tablas['evaluacion_busqueda'] = evaluacion_busqueda
tablas['sensibilidad_indicador'] = sensibilidad_reglas
fuente = dict(entrada=CONFIG['entrada'], gold_referencia=CONFIG['snapshot'], filas_observaciones=len(obs))
feed = dict(version='sconto-app-v1', fecha_corte=CORTE, vigencia_maxima_dias=1,
            productos=registros(compra['catalogo_consulta']), ofertas=registros(compra['ofertas_evaluadas']),
            requiere_confirmacion_sku=True, precio_total_verificado=False,
            reglas={'ventaja_minima_pct': 5, 'cuantil_favorable': .25, 'cuantil_alto': .75},
            contrato='CONTRATO_APP.md')
series_app = tablas['series'].loc[tablas['series'].producto_canonico_id.isin(compra['catalogo_consulta'].producto_canonico_id)]
feed['series'] = registros(series_app)
feed['referencias'] = registros(tablas['referencias_base'].loc[tablas['referencias_base'].serie_id.isin(series_app.serie_id)])
feed['historial'] = registros(tablas['precios_diarios'].loc[tablas['precios_diarios'].serie_id.isin(series_app.serie_id)])
manifest = exportar(tablas, analisis, SALIDA, fuente, CORTE,
                    extras_json={'app_feed.json': feed, 'indice_busqueda.json': buscador.indice()})
import sqlite3
from contextlib import closing
with closing(sqlite3.connect(SALIDA / 'sconto_web.sqlite')) as cn:
    assert cn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert cn.execute('PRAGMA foreign_key_check').fetchall() == []
    for nombre, cantidad in manifest['tablas'].items():
        assert cn.execute(f'SELECT COUNT(*) FROM "{nombre}"').fetchone()[0] == cantidad
for nombre, digest in manifest['archivos'].items():
    assert hashlib.sha256((SALIDA / nombre).read_bytes()).hexdigest() == digest
display(pd.DataFrame(manifest['tablas'].items(), columns=['tabla', 'filas']))
''')
code('''
ETL = BASE / 'dataset_limpio'
ETL.mkdir(parents=True, exist_ok=True)
archivos_etl = []
for nombre, tabla in gold.items():
    exportable = tabla.reset_index() if nombre.startswith(('matriz_', 'metadatos_')) else tabla
    for extension in ('parquet', 'csv.gz'):
        destino = ETL / f'{nombre}.{extension}'
        if extension == 'parquet':
            exportable.to_parquet(destino, index=False)
        else:
            exportable.to_csv(destino, index=False, compression={'method': 'gzip', 'mtime': 0})
        archivos_etl.append(destino)
diccionario = pd.DataFrame([dict(capa=capa, tabla=nombre, campo=campo, tipo=str(tabla[campo].dtype), nulos=int(tabla[campo].isna().sum()))
                            for capa, coleccion in [('etl', gold), ('app', tablas)]
                            for nombre, tabla in coleccion.items() for campo in tabla.columns])
diccionario.to_csv(ETL / 'esquema.csv', index=False)
archivos_etl.append(ETL / 'esquema.csv')
auditoria_etl.to_csv(ETL / 'auditoria_etl.csv', index=False)
archivos_etl.append(ETL / 'auditoria_etl.csv')
modo = 'local' if LOCAL else 'Colab' if 'google.colab' in sys.modules else 'otro Python'
auditoria = dict(entorno=modo, revision_codigo=CONFIG['revision_codigo'], fecha_corte=CORTE,
                 entradas=fuente, tablas_etl={k: len(v) for k, v in gold.items()}, tablas_app=manifest['tablas'],
                 validacion_avance1=[39363, 298, 93], revision_humana='pendiente',
                 archivos_etl={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos_etl})
(BASE / 'auditoria_ejecucion.json').write_text(json.dumps(auditoria, ensure_ascii=False, indent=2), encoding='utf-8')
entrega = BASE / 'entrega_sconto.zip'
with zipfile.ZipFile(entrega, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for archivo in archivos_etl:
        z.write(archivo, 'dataset_limpio/' + archivo.name)
    z.write(SALIDA / 'sconto_web.zip', 'datos_app.zip')
    z.write(BASE / 'auditoria_ejecucion.json', 'auditoria_ejecucion.json')
    for nombre in ('DICCIONARIO.md', 'CONTRATO_APP.md'):
        z.write(runtime / nombre, nombre)
print('Entrega completa:', entrega.name, '· MB:', round(entrega.stat().st_size / 1e6, 1))
print('Ejecución registrada como:', modo)
''')
md('''
### Conclusiones y límites del corte
La tabla siguiente se calcula al ejecutar. Se conservan fuentes y canales, se reproduce el primer avance
y se consultan precios con evidencia. La historia de vendedor y los anuncios limitan el diagnóstico
de descuento inflado. Antes de comprar se debe cotejar la variante y las condiciones.
La cantidad de productos del catálogo no equivale al número de variantes verificadas.
''')
code('''
display(pd.Series({
    'observaciones_limpias': len(obs), 'catalogo_consulta': len(compra['catalogo_consulta']),
    'ofertas_en_snapshot': len(compra['ofertas_evaluadas']),
    'ofertas_con_conflicto_o_identidad_pendiente': len(compra['revision_identidades']),
    'series_evento_con_brecha': int(series_evento.brecha_pp.notna().sum()),
    'entrenamiento_BF2024': analisis['tarjeta']['n_entrenamiento'],
    'validacion_BF2025': analisis['tarjeta']['n_validacion'],
}).to_frame('resultado'))
print('Siguiente fase: conectar estas salidas con la app y contrastar consultas con la tienda durante el Buen Fin.')
''')
code('''
DESCARGAR = False
GUARDAR_EN_DRIVE = False
if GUARDAR_EN_DRIVE:
    from google.colab import drive
    import shutil
    drive.mount('/content/drive')
    destino = Path('/content/drive/MyDrive/Sconto/entregas_avance2')
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy2(entrega, destino / f'entrega_sconto_{CORTE}.zip')
if DESCARGAR:
    from google.colab import files
    files.download(str(entrega))
''')
md('''
### Fuentes y reproducción
- [PROFECO QQP](https://datos.profeco.gob.mx/datos_abiertos/qqp.php): observaciones de sucursales físicas.
- [Preciómetro](https://preciometro.com): mínimos y ofertas por vendedor; cada fila conserva URL y hash.
- [Isolation Forest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html)
  y [TF-IDF](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html): implementación open source.
- [Repositorio](https://github.com/d1512pb/sconto-reale-o-falso): código, registro de fuentes y manifiestos.

Captura: lista fija, ritmos limitados, robots.txt y detención ante bloqueos; sin cuentas falsas, proxies
o evasión de CAPTCHA. APIs sin acceso y fuentes bloqueadas se documentan sin inventar precios.
Se distinguen las ejecuciones locales, en Colab y en GitHub Actions.
''')

nb = nbf.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.11'},
    'colab': {'name': '03_Sconto_CRISP_DM_ETL_web.ipynb', 'provenance': []}})
nbf.write(nb, RAIZ / 'notebooks/03_Sconto_CRISP_DM_ETL_web.ipynb')
print(f'Notebook generado: {len(cells)} celdas')
