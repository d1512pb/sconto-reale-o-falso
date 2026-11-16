"""Genera el notebook 04 con el código y snapshot base fijados por SHA-256."""
from __future__ import annotations

import argparse
import base64
import hashlib
from io import BytesIO
from pathlib import Path
import zipfile

import nbformat as nbf


RAIZ = Path(__file__).resolve().parents[1]
SNAPSHOT = 'sconto_colab_2026-11-14.zip'
SHA256_SNAPSHOT = '9fc3bf271f54037ee7180e297de61fe551715b1ec22ea7d57af82dea76ea5e79'
BRONZE = 'sconto_entrada_v2_2026-11-14.zip'
SHA256_BRONZE = '4814d5339e2c896ee71c75b06e17291c5c3054815dea580961324a7cba96b064'
PROFECO = 'profeco_bf2026_privado_2026-11-14.zip'
SHA256_PROFECO = '84be1ca16529f6aa3cc8b36b5b1a647874d45d52499d4b4bed388178f1cbcba2'
ORIGEN = 'https://github.com/d1512pb/sconto-reale-o-falso/releases/download/datos/'
RUTAS = [RAIZ / 'config' / nombre for nombre in ('eventos.yaml', 'preciometro_diarios.csv')]
DEPENDENCIAS = ['numpy==2.4.6', 'pandas==3.0.6', 'pyarrow==26.0.0', 'scikit-learn==1.9.1',
                'matplotlib==3.11.2', 'PyYAML==6.0.3', 'tzdata==2026.5']


def paquete_codigo(archivos=None):
    buffer = BytesIO()
    if archivos is None:
        archivos = sorted((RAIZ / 'src/sconto').rglob('*.py')) + RUTAS
    with zipfile.ZipFile(buffer, 'w') as z:
        for ruta in archivos:
            nombre = ruta.relative_to(RAIZ).as_posix()
            z.writestr(zipfile.ZipInfo(nombre), ruta.read_bytes(), zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def crear():
    n = nbf.v4.new_notebook(metadata={'kernelspec': {'display_name': 'Python 3',
                                                    'language': 'python', 'name': 'python3'}})
    md, cell = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
    codigo = paquete_codigo()
    sha_codigo = hashlib.sha256(codigo).hexdigest()
    codigo_b64 = base64.b64encode(codigo).decode('ascii')
    n.cells = [
        md('''# Sconto v2 · Buen Fin 2026

## Comprensión del negocio

¿Hay evidencia comparable de que un precio conviene? El histórico describe lo observado. El modelo retrospectivo evalúa si la mediana del evento bajó frente al periodo previo en la misma serie QQP.

El corte base cubre el 13 y 14 de noviembre de 2026. La ventana completa termina el 17 de noviembre y la posterior termina el 1 de diciembre. Los resultados de mercado de este corte son preliminares.'''),
        md('''## Reproducción en Colab o en una PC

El modo rápido `descarga_fijada` recupera el gold público del 14 de noviembre y verifica su SHA-256. En `reproduccion` se verifica una copia local de ese gold. En `preparacion_fijada` se reconstruyen las tablas desde bronze, con conciliación por fuente y comparación de cada tabla contra la referencia de operación. Carga los ZIP bronze y PROFECO de la entrega privada en el panel Archivos de Colab. El modo `actualizacion` abre el gold público más reciente y registra su hash.

En Colab se instalan las dependencias fijadas. Para un kernel local sin red, prepara el entorno y proporciona los ZIP locales. Los modos usan artefactos ya capturados.'''),
        cell(f'''import base64, hashlib, importlib.metadata, io, json, os, re, subprocess, sys, zipfile
from pathlib import Path
from urllib.request import urlopen

MODO = os.environ.get('SCONTO_V2_MODO', 'descarga_fijada')
INSTALAR_DEPENDENCIAS = os.environ.get('SCONTO_V2_INSTALAR', '0') == '1' or 'google.colab' in sys.modules
ENTRADA = Path(os.environ.get('SCONTO_V2_SNAPSHOT', {SNAPSHOT!r}))
ENTRADA_BRONZE = Path(os.environ.get('SCONTO_V2_BRONZE', {BRONZE!r}))
ENTRADA_PROFECO = Path(os.environ.get('SCONTO_V2_PROFECO', {PROFECO!r}))
SALIDA = Path(os.environ.get('SCONTO_V2_SALIDA', 'entrega_sconto_v2'))
DEPENDENCIAS = {DEPENDENCIAS!r}
if INSTALAR_DEPENDENCIAS:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', *DEPENDENCIAS], check=True)
for dependencia in DEPENDENCIAS:
    nombre, version = dependencia.split('==')
    assert importlib.metadata.version(nombre) == version, dependencia

ORIGEN = {ORIGEN!r}
FIJADO = {SNAPSHOT!r}
SHA_SNAPSHOT = {SHA256_SNAPSHOT!r}
SHA_BRONZE = {SHA256_BRONZE!r}
SHA_PROFECO = {SHA256_PROFECO!r}
if MODO == 'reproduccion' or (MODO == 'preparacion_fijada' and ENTRADA.is_file()):
    datos_zip = ENTRADA.read_bytes()
elif MODO in ('descarga_fijada', 'preparacion_fijada', 'actualizacion'):
    nombre = 'sconto_colab_actual.zip' if MODO == 'actualizacion' else FIJADO
    with urlopen(ORIGEN + nombre, timeout=180) as respuesta:
        datos_zip = respuesta.read()
else:
    raise ValueError('Modo de carga desconocido')
sha_datos = hashlib.sha256(datos_zip).hexdigest()
if MODO != 'actualizacion':
    assert sha_datos == SHA_SNAPSHOT, 'Copia de entrada distinta del corte fijado'
print('Modo', MODO, '· SHA-256 de datos', sha_datos)'''),
        cell(f'''# Archivo autocontenido con los módulos que usa el proyecto y la configuración fijada.
codigo_zip = base64.b64decode({codigo_b64!r})
sha_codigo = hashlib.sha256(codigo_zip).hexdigest()
assert sha_codigo == {sha_codigo!r}
codigo = Path('sconto_v2_codigo_' + sha_codigo[:12]).resolve()
with zipfile.ZipFile(io.BytesIO(codigo_zip)) as archivo:
    for ruta in archivo.namelist():
        if not re.fullmatch(r'(?:src/sconto/(?:[a-z_]+/)*[a-z0-9_]+\\.py|config/[a-z_]+\\.(?:csv|yaml))', ruta):
            raise ValueError('Ruta de código inesperada')
        destino = codigo / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(archivo.read(ruta))
sys.path.insert(0, str(codigo / 'src'))
os.environ['SCONTO_RAIZ'] = str(codigo)
import pandas as pd
import sconto
from sconto.colab import cargar_paquete
from sconto.mart import preparar_tablas
from sconto.app_datos import preparar_aplicacion
from sconto.v2_corte import reconstruir_corte, cargar_profeco
from sconto.v2_history import analizar
from sconto.v2_mercado import analizar_mercado, resumen_cambios

assert Path(sconto.__file__).is_relative_to(codigo)
print('Código verificado', sha_codigo)'''),
        md('''## Comprensión y preparación de los datos

QQP describe precios físicos observados. El mínimo multitienda y los anuncios del agregador tienen coberturas distintas. La fecha de observación histórica, la fecha de captura y la actualización de la tienda son campos distintos. Se conserva la procedencia y no se asignan horas ausentes.'''),
        cell('''from hashlib import file_digest
from zoneinfo import ZoneInfo

gold = cargar_paquete(io.BytesIO(datos_zip))
with zipfile.ZipFile(io.BytesIO(datos_zip)) as archivo:
    origen = json.loads(archivo.read('paquete.json'))
corte = pd.to_datetime(origen['dataset_construido_utc'], utc=True).tz_convert(ZoneInfo('America/Mexico_City')).date().isoformat()
conciliacion = {}
sha_bronze = None
if MODO == 'preparacion_fijada':
    if not ENTRADA_BRONZE.is_file():
        raise FileNotFoundError('Sube el ZIP bronze versionado de la entrega privada: ' + ENTRADA_BRONZE.name)
    with ENTRADA_BRONZE.open('rb') as entrada:
        sha_bronze = file_digest(entrada, 'sha256').hexdigest()
    assert sha_bronze == os.environ.get('SCONTO_V2_BRONZE_SHA256', SHA_BRONZE), 'Copia bronze distinta de la fijada'
    gold, etapas, fuentes_conciliadas = reconstruir_corte(ENTRADA_BRONZE, gold, sha_datos)
    conciliacion = {'etapas': etapas, 'fuentes': fuentes_conciliadas}
    print('Equivalencia con el ETL de operación verificada en todas las tablas.')
    display(etapas)
    display(fuentes_conciliadas)
else:
    print('Modo rápido: se verificó el gold; la reconstrucción desde bronze requiere preparacion_fijada.')
obs = gold['observaciones']
fuentes = obs.groupby('fuente', dropna=False).agg(filas=('obs_id','size'), series=('serie_id','nunique'),
    primera_fecha_precio=('fecha_precio','min'), ultima_fecha_precio=('fecha_precio','max'),
    ultima_fecha_captura=('fecha_captura','max')).reset_index()
assert obs.obs_id.is_unique and obs.precio.gt(0).all()
display(fuentes)
display(gold['exclusiones'].head(3))

seleccion = pd.read_csv(codigo / 'config/preciometro_diarios.csv', dtype=str)
tablas, anomalias = preparar_tablas(gold, seleccion, corte, ampliar_catalogo=True)
compra, _ = preparar_aplicacion(tablas, corte)
tablas.update(compra)
display(tablas['catalogo_consulta'].groupby('en_seguimiento_diario').size())'''),
        md('''## Modelado y evaluación histórica

Se distingue la regla provisional de compra, la detección de anomalías con Isolation Forest y la predicción supervisada de una bajada. Para la clasificación se aprende en 2024 y se evalúa en 2025. Ambos años ya se habían explorado en el proyecto. 2026 permanece pendiente de observaciones comparables y del cierre de la ventana.'''),
        cell('''historia = analizar(obs, gold['eventos'], fecha_corte=corte)
for nombre in ('cobertura', 'cobertura_resultado', 'sensibilidad', 'metricas', 'calibracion'):
    display(historia[nombre])
display(tablas['evaluacion_modelo'])'''),
        cell('''import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import ConfusionMatrixDisplay

figuras = {}
modelo = historia['protocolo'].get('modelo_elegido_en_2024')
prueba = historia['metricas'].query("etapa == 'prueba_BF2025' and modelo == @modelo") if modelo else pd.DataFrame()
if len(prueba):
    r = prueba.iloc[0]
    fig, ax = plt.subplots(figsize=(5.5, 4), layout='constrained')
    ConfusionMatrixDisplay(np.array([[int(r.tn), int(r.fp)], [int(r.fn), int(r.tp)]]),
                           display_labels=['Igual o mayor', 'Bajó']).plot(ax=ax, cmap='Blues', colorbar=False)
    ax.set(title='Matriz de confusión · QQP CDMX 2025', xlabel='Predicción', ylabel='Precio observado')
    figuras['matriz_confusion_bf2025'] = fig

calibracion = historia['calibracion']
if not calibracion.empty:
    fig, ax = plt.subplots(figsize=(6, 4), layout='constrained')
    ax.plot([0, 1], [0, 1], '--', color='.6', label='Correspondencia perfecta')
    for nombre, grupo in calibracion.loc[calibracion.n_series.gt(0)].groupby('modelo'):
        ax.plot(grupo.prob_media, grupo.frecuencia_bajada, 'o-', label=nombre.replace('_', ' '))
    ax.set(title='Calibración retrospectiva · QQP CDMX 2025', xlabel='Probabilidad media estimada',
           ylabel='Frecuencia de bajada observada', xlim=(0, 1), ylim=(0, 1))
    ax.legend(fontsize=8)
    figuras['calibracion_bf2025'] = fig

sensibilidad = historia['sensibilidad']
if not sensibilidad.empty:
    grafica = sensibilidad.query("fuente == 'qqp_cdmx' and min_fechas_base == 4 and referencia == 'mediana'")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.5), layout='constrained')
    for evento_id, grupo in grafica.groupby('evento_id'):
        ax1.plot(grupo.umbral_pct, grupo.perdida_media_vs_mejor_observado_mxn, 'o-', label=evento_id)
        senal = 100 * (grupo.favorables + grupo.altos) / grupo.series_con_historia
        ax2.plot(grupo.umbral_pct, senal, 'o-', label=evento_id)
    for eje in (ax1, ax2):
        eje.set(xlabel='Diferencia exigida (%)')
        eje.legend(fontsize=8)
    ax1.set(ylabel='Pérdida media (MXN)', title='Error frente a la mejor de dos fechas')
    ax2.set(ylabel='Series con señal (%)', title='Cobertura de la señal')
    figuras['sensibilidad_reglas_qqp_cdmx'] = fig

cobertura = historia['cobertura_resultado']
if not cobertura.empty:
    muestra = cobertura.query("fuente == 'qqp_cdmx' and min_fechas_base == 4 and min_fechas_evento == 1")
    if not muestra.empty:
        ax = muestra.set_index('evento_id')[['con_historia_previa','base_suficiente','resultado_maduro']].plot.bar(
            figsize=(7, 4), title='Cobertura física · QQP CDMX', ylabel='Series por evento', xlabel='Buen Fin')
        ax.legend(['Historia previa', 'Base suficiente', 'Resultado maduro'], fontsize=8)
        figuras['cobertura_qqp_cdmx'] = ax.figure
for fig in figuras.values():
    display(fig)
    plt.close(fig)'''),
        md('''## Buen Fin 2026 · avance descriptivo

Se reporta cada población por separado. Cada comparación usa una mediana por serie y día. Dos registros en días diferentes no precisan cuándo cambió el precio ni cuánto duró una oferta. Los mínimos del agregador y los anuncios con identidad pendiente carecen de corroboración directa suficiente para las hipótesis de oferta verificada.'''),
        cell('''evento = gold['eventos'].set_index('evento_id', drop=False).loc['BF2026']
mercado = analizar_mercado(obs, gold['series_evento'], evento, corte)
display(mercado['inventario'].groupby(['fuente','fecha_precio']).filas.sum().unstack())
display(resumen_cambios(mercado['cambios']))
display(mercado['hallazgos'])

tienda = obs.loc[obs.fuente.eq('tiendas') & obs.plataforma.str.casefold().eq('liverpool')]
if not tienda.empty:
    serie = tienda.serie_id.value_counts().index[0]
    muestra = tienda.loc[tienda.serie_id.eq(serie)].sort_values('fecha_precio')
    fig, ax = plt.subplots(figsize=(7, 3.7), layout='constrained')
    fechas = pd.to_datetime(muestra.fecha_precio)
    ax.plot(fechas, muestra.precio, 'o-', label='Publicado')
    ax.plot(fechas, muestra.precio_anterior_anunciado, '.--', label='Tachado')
    ax.set(title='Una ficha histórica de Liverpool', xlabel='Día observado', ylabel='Precio (MXN)')
    ax.legend()
    fig.autofmt_xdate()
    figuras['evolucion_ficha_liverpool'] = fig
    display(fig)
    plt.close(fig)'''),
        md('''### Consulta especial de PROFECO

La entrada privada de PROFECO contiene precios diarios completos y exclusiones con motivo, sin direcciones, nombres de sucursal ni crudos. Los identificadores opacos permiten mantener una serie por sucursal dentro de esta copia. La hora corresponde a la consulta a PROFECO. CDMX y Edomex conservan su propia población.'''),
        cell('''from sconto.v2_mercado import analizar_profeco_bf

oficial = {}
datos_oficiales = {}
sha_oficial = None
if ENTRADA_PROFECO.is_file():
    contenido = ENTRADA_PROFECO.read_bytes()
    sha_oficial = hashlib.sha256(contenido).hexdigest()
    assert sha_oficial == os.environ.get('SCONTO_V2_PROFECO_SHA256', SHA_PROFECO), 'Copia de PROFECO distinta de la fijada'
    datos_oficiales, manifiesto_profeco = cargar_profeco(io.BytesIO(contenido))
    if manifiesto_profeco['fecha_corte'] > corte:
        raise ValueError('La consulta especial es posterior al corte gold')
    oficial = analizar_profeco_bf(datos_oficiales['observaciones'], evento)
    display(oficial['resumen'])
    print('Registros fechados', len(datos_oficiales['observaciones']), '· Exclusiones', len(datos_oficiales['exclusiones']),
          '· SHA-256', sha_oficial)
else:
    print('Bloque PROFECO no ejecutado: sube el ZIP privado versionado', ENTRADA_PROFECO.name)'''),
        md('''## Despliegue y exportación reproducible

Se exportan las observaciones limpias completas, los resultados históricos y las tablas de mercado. Las fechas desconocidas permanecen vacías. La base de consulta se construye con la transformación compartida de la app y sus condiciones conservan la procedencia del precio publicado.'''),
        cell('''from sconto.mart import guardar_sqlite

SALIDA.mkdir(parents=True, exist_ok=True)
exportaciones = {
    'observaciones_limpias': obs, 'exclusiones': gold['exclusiones'], 'calidad_fuentes': fuentes,
    'productos': tablas['catalogo_consulta'], 'ofertas': tablas['ofertas_evaluadas'],
    'precios_diarios': tablas['precios_diarios'], 'referencias': tablas['referencias_base'],
    'anomalias': tablas['resultados_modelo'], 'eventos': gold['eventos'],
    **{'historico_' + k: t for k, t in historia.items() if isinstance(t, pd.DataFrame)},
    **{'mercado_' + k: t for k, t in mercado.items() if k != 'muestra'},
    **{'profeco_' + k: oficial[k] for k in ('inventario', 'resumen') if k in oficial},
    **{'profeco_' + k: t for k, t in datos_oficiales.items()},
    **{'conciliacion_' + k: t for k, t in conciliacion.items()},
}
archivos = []
esquema = []
for nombre, tabla in exportaciones.items():
    if 'particion' in tabla:
        tabla = tabla.assign(particion=tabla.particion.astype('string'))
    for columna, dtype in tabla.dtypes.items():
        unidad = 'porcentaje o puntos porcentuales' if '_pct' in columna or columna.endswith('_pp') else (
            'moneda de la fila' if columna in {'precio','precio_mediano','precio_anterior_anunciado','mediana_base','minimo_base'} else '')
        esquema.append((nombre, columna, str(dtype), unidad, int(tabla[columna].isna().sum())))
    parquet = SALIDA / (nombre + '.parquet')
    csv = SALIDA / (nombre + '.csv.gz')
    tabla.to_parquet(parquet, index=False)
    tabla.to_csv(csv, index=False, compression={'method':'gzip', 'mtime':0})
    archivos.extend([parquet, csv])
diccionario = SALIDA / 'esquema.csv'
pd.DataFrame(esquema, columns=['tabla','campo','tipo','unidad','nulos']).to_csv(diccionario,index=False)
base = SALIDA / 'sconto_v2_consulta.sqlite'
guardar_sqlite(tablas, base)
archivos.extend([diccionario, base])
for nombre, fig in figuras.items():
    ruta = SALIDA / (nombre + '.png')
    fig.savefig(ruta, dpi=150)
    archivos.append(ruta)
manifiesto = dict(esquema='sconto-notebook-v2', reglas='precio-v1 provisional',
    protocolo_modelo=historia['protocolo'], sha256_codigo=sha_codigo, sha256_datos=sha_datos, corte=corte,
    sha256_consulta_especial_profeco=sha_oficial,
    sha256_entrada_bronze=sha_bronze, equivalencia_operativa=bool(conciliacion),
    estado_profeco='comprobado' if datos_oficiales else 'entrada_no_disponible',
    dependencias=DEPENDENCIAS, ultima_fecha_por_fuente=fuentes.set_index('fuente').ultima_fecha_precio.astype(str).to_dict(),
    filas={k:len(t) for k,t in exportaciones.items()},
    archivos={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos},
    nulos='Valor desconocido o inaplicable según el campo. Nunca equivale a cero ni a precio confirmado.')
(SALIDA / 'manifest.json').write_text(json.dumps(manifiesto, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
print('Entrega', SALIDA, '· corte', corte, '· registros limpios', len(obs))'''),
    ]
    return n


def crear_operativo():
    archivos = [RAIZ / 'src/sconto' / (nombre + '.py') for nombre in (
        '__init__', 'consulta_v2', 'cuaderno_operativo_v2', 'decisiones_v2', 'intraday', 'rutas')]
    bundle = paquete_codigo(archivos)
    sha_bundle = hashlib.sha256(bundle).hexdigest()
    codigo_b64 = base64.b64encode(bundle).decode('ascii')
    md, cell = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
    return nbf.v4.new_notebook(metadata={'kernelspec': {'display_name': 'Python 3',
        'language': 'python', 'name': 'python3'}}, cells=[
        md('''# Sconto v2 · Consulta operativa

Este cuaderno reproduce las decisiones de la API sobre la misma copia SQLite de intradía, catálogo y hora de evaluación. Trabaja sobre copias transaccionales locales. El análisis histórico y el modelo retrospectivo siguen en el cuaderno 04.

Proporciona las rutas de las dos bases y una fecha ISO 8601 con huso. Puedes limitar por identificador de producto. Para reproducir la API pública deja `PRIVADAS = False`. La revisión privada requiere autorización de acceso a esa entrada. Mantén los archivos operativos en custodia privada.

La comparación actual ordena totales de ofertas online verificadas y vigentes con mismo GTIN, condición, moneda y contexto de entrega. La estimación de ahorro requiere historia previa del mismo anuncio. Capturas posteriores a la base no amplían su cobertura. El registro guarda versiones, hora, hashes de las copias, estado y motivos de abstención.'''),
        cell('''from pathlib import Path
import os

INTRADIA = Path(os.environ.get('SCONTO_OP_INTRADIA', 'intradia.sqlite3'))
CATALOGO = Path(os.environ.get('SCONTO_OP_CATALOGO', 'catalogo.sqlite'))
MOMENTO = os.environ.get('SCONTO_OP_MOMENTO', '2026-11-15T17:00:00-06:00')
PRODUCTOS = [p.strip() for p in os.environ.get('SCONTO_OP_PRODUCTOS', '').split(',') if p.strip()]
PRIVADAS = os.environ.get('SCONTO_OP_PRIVADAS') == '1'
SALIDA = Path(os.environ.get('SCONTO_OP_SALIDA', 'decision_operativa_v2.json'))'''),
        cell(f'''import base64, hashlib, io, json, re, sys, zipfile
from IPython.display import JSON, display

bundle = base64.b64decode({codigo_b64!r})
sha_codigo = {sha_bundle!r}
assert hashlib.sha256(bundle).hexdigest() == sha_codigo
raiz = Path('sconto_v2_operativo_' + sha_codigo[:12]).resolve()
with zipfile.ZipFile(io.BytesIO(bundle)) as archivo:
    for nombre in archivo.namelist():
        if not re.fullmatch(r'src/sconto/[a-z_0-9]+\\.py', nombre):
            raise ValueError('Ruta de código inesperada')
        destino = raiz / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(archivo.read(nombre))
sys.path.insert(0, str(raiz / 'src'))
import sconto
from sconto.cuaderno_operativo_v2 import reproducir
assert Path(sconto.__file__).is_relative_to(raiz), 'Reinicia el kernel para cargar la versión fijada'

resultado = reproducir(INTRADIA, CATALOGO, MOMENTO, productos=PRODUCTOS, privadas=PRIVADAS)
resultado['sha256_codigo'] = sha_codigo
SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
print('Regla', resultado['regla'], '· ofertas visibles', resultado['numero_ofertas'],
      '· con historia previa suficiente', resultado['numero_ofertas_con_historia_previa'],
      '· evaluables', resultado['numero_ofertas_evaluables'])
display(JSON(resultado))'''),
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modo', choices=('historico', 'operativo'), default='historico')
    parser.add_argument('--salida', type=Path)
    args = parser.parse_args()
    operativo = args.modo == 'operativo'
    nombre = '05_Sconto_Operativo_v2.ipynb' if operativo else '04_Sconto_CRISP_DM_v2.ipynb'
    nbf.write(crear_operativo() if operativo else crear(), args.salida or RAIZ / 'notebooks' / nombre)


if __name__ == '__main__':
    main()
