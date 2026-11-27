"""Genera el notebook final 06 (CRISP-DM) con el código del proyecto y el piloto PROFECO anonimizado incrustados.

Los datos públicos (paquete del corte final) se descargan con verificación SHA-256 o se leen de una ruta local.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import nbformat as nbf

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
CORTE = RAIZ / 'data/operacion/v2/corte_final_20261126'
PAQUETE = 'sconto_colab_2026-11-26.zip'
NOMBRE_PUBLICO = 'sconto_corte_final_2026-11-26.zip'
ORIGEN = 'https://github.com/d1512pb/sconto-reale-o-falso/releases/download/datos/'
DEPENDENCIAS = ['numpy==2.4.6', 'pandas==3.0.6', 'pyarrow==26.0.0', 'scikit-learn==1.9.1', 'matplotlib==3.11.2',
                'PyYAML==6.0.3', 'tzdata==2026.5']
SALIDA = RAIZ / 'notebooks/06_Sconto_Final_CRISP_DM.ipynb'


def sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def codigo_zip() -> bytes:
    buffer = io.BytesIO()
    archivos = sorted((RAIZ / 'src/sconto').rglob('*.py')) + [RAIZ / 'config/eventos.yaml', RAIZ / 'config/preciometro_diarios.csv']
    with zipfile.ZipFile(buffer, 'w') as z:
        for ruta in archivos:
            z.writestr(zipfile.ZipInfo(ruta.relative_to(RAIZ).as_posix()), ruta.read_bytes(), zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def profeco_csv() -> bytes:
    from sconto.modelo_final import observaciones_piloto
    datos = observaciones_piloto(CORTE / 'piloto_profeco_intradia.sqlite3')
    return gzip.compress(datos.to_csv(index=False).encode('utf-8'), mtime=0)


def crear() -> nbf.NotebookNode:
    codigo, profeco = codigo_zip(), profeco_csv()
    paquete_sha = sha((CORTE / PAQUETE).read_bytes())
    md, cell = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
    reemplazos = {
        '__DEPENDENCIAS__': repr(DEPENDENCIAS), '__ORIGEN__': repr(ORIGEN), '__PUBLICO__': repr(NOMBRE_PUBLICO),
        '__PAQUETE__': repr(PAQUETE), '__SHA_PAQUETE__': repr(paquete_sha),
        '__CODIGO__': repr(base64.b64encode(codigo).decode('ascii')), '__SHA_CODIGO__': repr(sha(codigo)),
        '__PROFECO__': repr(base64.b64encode(profeco).decode('ascii')), '__SHA_PROFECO__': repr(sha(profeco)),
    }

    def code(texto: str):
        for k, v in reemplazos.items():
            texto = texto.replace(k, v)
        return cell(texto.strip('\n'))

    n = nbf.v4.new_notebook(metadata={'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                                      'language_info': {'name': 'python'}, 'colab': {'provenance': []}})
    n.cells = [
        md('''# Sconto reale o falso · Entrega final
### ¿Conviene esperar al Buen Fin? Precios de tecnología con historia y un modelo que lo predice

**Equipo:** Daniel Peredo Borgonio · Kevin Celis Torres · Igor Cappelli — Minería de Datos, ESCOM-IPN.
**Corte final de datos:** 26 de noviembre de 2026 (recolección detenida ese día).

| | |
|---|---|
| **Problema** | Un descuento anunciado no dice si el precio es realmente bajo. ¿Cómo saber si conviene comprar o esperar al Buen Fin? |
| **Datos** | 690,888 precios limpios de tecnología: QQP de PROFECO (sucursales físicas de CDMX, 2018–2026), Preciómetro (mínimo en línea entre tiendas, 2026) y la consulta oficial del Buen Fin 2026 de PROFECO. |
| **Modelo** | Árbol de decisión que predice si el precio de un producto bajará durante el Buen Fin, entrenado con 6 ediciones (2018–2023), elegido con 2022–2024, probado con 2025 y validado con 2026. |
| **Resultado** | Prueba 2025: accuracy 79.6 %, balanced accuracy 0.784 y F1 0.859 (la referencia que siempre dice "baja" da 0.500). Validación 2026 en precios en línea: accuracy 72.2 % y balanced accuracy 0.682. |
| **Despliegue** | App instalable y API con el modelo: [sconto-v2-api.fly.dev](https://sconto-v2-api.fly.dev) · [documentación interactiva](https://sconto-v2-api.fly.dev/docs) · [repositorio](https://github.com/d1512pb/sconto-reale-o-falso). |

Seguimos la metodología **CRISP-DM**: comprensión del negocio → comprensión de los datos → preparación → modelado → evaluación → despliegue. Cada decisión (por qué 5 %, por qué cuatro fechas, qué modelo) se justifica con los datos.'''),
        md('''## Cómo ejecutar este notebook

En Colab: **Entorno de ejecución → Ejecutar todo** (CPU, unos 10 minutos; la validación de 174 variantes de modelos es la parte más lenta). La primera celda instala las versiones fijadas, extrae el código del proyecto incrustado y descarga el paquete del corte final verificando su huella SHA-256. Si ya tienes el ZIP, súbelo al panel *Archivos* con el nombre indicado o define la variable de entorno `SCONTO_FINAL_PAQUETE` con su ruta. El piloto PROFECO viene incrustado y anonimizado (cadena comercial y un identificador cifrado por sucursal, sin direcciones).'''),
        code('''
import base64, gzip, hashlib, importlib.metadata, io, json, os, subprocess, sys, warnings, zipfile
from pathlib import Path
from urllib.request import urlopen

warnings.filterwarnings('ignore')
DEPENDENCIAS = __DEPENDENCIAS__
EN_COLAB = 'google.colab' in sys.modules
if EN_COLAB or os.environ.get('SCONTO_FINAL_INSTALAR') == '1':
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', *DEPENDENCIAS], check=True)
for dep in DEPENDENCIAS:
    nombre, version = dep.split('==')
    assert importlib.metadata.version(nombre) == version, f'{nombre} {importlib.metadata.version(nombre)} != {version}'

# Código del proyecto (src/sconto) incrustado y verificado
CODIGO = base64.b64decode(__CODIGO__)
assert hashlib.sha256(CODIGO).hexdigest() == __SHA_CODIGO__, 'El código incrustado no coincide'
DESTINO = Path('sconto_codigo'); DESTINO.mkdir(exist_ok=True)
zipfile.ZipFile(io.BytesIO(CODIGO)).extractall(DESTINO)
sys.path.insert(0, str(DESTINO / 'src'))
os.environ['SCONTO_RAIZ'] = str(DESTINO)

# Paquete público del corte final (observaciones limpias, productos y eventos)
SHA_PAQUETE = __SHA_PAQUETE__
candidatos = [Path(os.environ.get('SCONTO_FINAL_PAQUETE', __PUBLICO__)), Path(__PUBLICO__), Path(__PAQUETE__)]
ruta = next((p for p in candidatos if p.is_file()), None)
datos_zip = ruta.read_bytes() if ruta else urlopen(__ORIGEN__ + __PUBLICO__, timeout=300).read()
assert hashlib.sha256(datos_zip).hexdigest() == SHA_PAQUETE, 'El paquete no es el del corte final'
PAQUETE = Path(__PUBLICO__)
if not PAQUETE.is_file():
    PAQUETE.write_bytes(datos_zip)

# Piloto PROFECO Buen Fin 2026 (anonimizado)
PROFECO = gzip.decompress(base64.b64decode(__PROFECO__))
assert hashlib.sha256(gzip.compress(PROFECO, mtime=0)).hexdigest() == __SHA_PROFECO__

import numpy as np, pandas as pd, matplotlib.pyplot as plt
from sconto import modelo_final as M, v2_history as H
pd.set_option('display.width', 160); pd.set_option('display.max_columns', 30); pd.set_option('display.float_format', '{:,.3f}'.format)
SALIDA = Path('entrega_final_sconto'); SALIDA.mkdir(exist_ok=True)
CORTE = '2026-11-26'
obs = M.cargar_paquete(PAQUETE)
piloto = pd.read_csv(io.BytesIO(PROFECO), dtype={'serie_id': str, 'vendedor_serie': str})
print(f'Código {hashlib.sha256(CODIGO).hexdigest()[:12]} · paquete {SHA_PAQUETE[:12]} · {len(obs):,} observaciones · piloto PROFECO {len(piloto):,} precios')
'''),
        md('''---
## 1. Comprensión del negocio

**Contexto.** En el Buen Fin (México, noviembre) y el Black Friday las tiendas anuncian descuentos, pero el porcentaje anunciado se calcula contra un "precio antes" que la tienda elige. Al comprador le interesa otra cosa: *¿este precio es bajo comparado con lo que el producto ha costado?* y *¿conviene esperar al evento o comprar ya?*

**Alcance.** Nos limitamos a **tecnología** (pantallas, celulares, laptops, tabletas, audio, cámaras). La misma arquitectura podría aplicarse a otras categorías con fuentes equivalentes.

**Preguntas que queremos contestar**

1. ¿Los precios de tecnología realmente bajan durante el Buen Fin? ¿Cuánto y por cuánto tiempo?
2. ¿Qué tamaño de bajada distingue una oferta real de una variación normal? (¿por qué 5 % y no 2 % o 10 %?)
3. ¿Podemos **predecir**, con los precios anteriores al evento, qué productos bajarán?
4. ¿El modelo funciona con datos que nunca vio: un año nuevo (2026) y otras fuentes?
5. ¿La app puede detectar "estafas" como subir el precio antes del evento y luego bajarlo? ¿Con qué precisión?
6. ¿Es cierto que la mayoría de los precios no muestra una señal clara (menos de 5 %)?
7. ¿Existen precios señuelo que hacen parecer oferta a un precio normal?

**Criterio de éxito.** Un modelo sólo es útil si supera a una línea base simple en datos futuros. Como las clases están desbalanceadas (en 2025 bajó el 77 % de las series), usamos la **balanced accuracy**: un modelo que siempre dice "baja" saca 77 % de accuracy pero 0.5 de balanced accuracy. Reportamos también accuracy, precisión, recall, F1 y AUC.

**Costo de equivocarse.** Un falso "bajará" hace que alguien espere sin necesidad; un falso "no bajará" hace que compre antes de una rebaja. Por eso la app muestra la evidencia (casos parecidos, historia) y nunca promete un precio.'''),
        md('''---
## 2. Comprensión de los datos

| Fuente | Qué aporta | Periodo | Uso |
|---|---|---|---|
| **QQP · PROFECO** ("Quién es Quién en los Precios") | Precio por producto y sucursal física en CDMX | 2018 – ago 2026 | Entrenamiento y prueba del modelo (8 ediciones del Buen Fin) |
| **Preciómetro** | Mínimo diario entre tiendas en línea y anuncios por tienda | jul – 14 nov 2026 | Validación final 2026 y app |
| **Consulta Buen Fin 2026 · PROFECO** | Precio diario por sucursal de 24 modelos | sep – 17 nov 2026 | Validación final 2026 |
| Wayback Machine, tiendas, Amazon | Capturas históricas puntuales | 2024 – 2026 | Contexto; muy pocos datos |

La recolección se detuvo el **26 de noviembre de 2026**: las tareas automáticas quedaron desactivadas y cada archivo del corte tiene huella SHA-256.'''),
        code('''
fecha = pd.to_datetime(obs.fecha_precio)
resumen = (obs.assign(fecha=fecha).groupby('fuente')
           .agg(filas=('precio', 'size'), productos=('producto_canonico_id', 'nunique'), series=('serie_id', 'nunique'),
                desde=('fecha', 'min'), hasta=('fecha', 'max'))
           .sort_values('filas', ascending=False))
resumen['desde'] = resumen.desde.dt.date; resumen['hasta'] = resumen.hasta.dt.date
display(resumen)
print('Piloto PROFECO BF2026:', f"{len(piloto):,} precios únicos, {piloto.id_externo.nunique()} modelos, "
      f"{piloto.vendedor_serie.nunique()} anuncios (producto × sucursal), {piloto.fecha_precio.min()} a {piloto.fecha_precio.max()}")
'''),
        code('''
qqp = obs.loc[obs.fuente.eq('qqp_cdmx')].assign(anio=fecha[obs.fuente.eq('qqp_cdmx')].dt.year)
categoria = qqp.descripcion_original.str.split('|', n=1).str[0].str.strip().str.upper().str.normalize('NFKD').str.encode('ascii', 'ignore').str.decode('ascii')
fig, ejes = plt.subplots(1, 2, figsize=(12, 3.6))
qqp.groupby('anio').size().plot.bar(ax=ejes[0], color='#245d4d'); ejes[0].set_title('QQP CDMX: precios por año'); ejes[0].set_xlabel('')
categoria.value_counts().head(10).sort_values().plot.barh(ax=ejes[1], color='#789d44'); ejes[1].set_title('QQP: categorías de tecnología (top 10)')
plt.tight_layout(); plt.show()
'''),
        md('''### 2.1 ¿Qué le pasa al precio alrededor del Buen Fin? (pregunta 1)

Para cada serie (producto × sucursal) dividimos su precio diario entre la mediana de su **base** (de 60 a 15 días antes del evento) y promediamos por semana relativa al inicio del Buen Fin, en las 8 ediciones de 2018 a 2025.'''),
        code('''
estudio = M.estudio_evento(obs)
display(estudio)
ax = estudio.plot.bar(x='semana', y='promedio', legend=False, figsize=(9, 3.6),
                      color=['#ea580c' if s == 0 else '#2563eb' for s in estudio.semana])
ax.axhline(0, color='black', lw=.8); ax.set_ylabel('% frente a la mediana base'); ax.set_xlabel('Semanas (0 = días del evento)')
ax.set_title('Precio promedio alrededor del Buen Fin · QQP CDMX 2018–2025'); plt.tight_layout(); plt.show()
semana = estudio.set_index('semana').promedio
print(f"Semana previa: {semana.loc[-1]:+.2f} % · durante el evento: {semana.loc[0]:+.2f} % · semana siguiente: {semana.loc[1]:+.2f} %")
'''),
        md('''**Lectura.** Los precios están estables hasta dos semanas antes; empiezan a bajar la semana previa (≈ −2.8 %), caen en promedio **≈ 9 %** durante el evento y **se recuperan la semana siguiente**. La rebaja existe pero es temporal, y la mediana semanal (0 %) muestra que muchas series no se mueven: no todos los productos bajan. No vemos un "subir antes para bajar" generalizado (semana −2: +0.7 %).

---
## 3. Preparación de los datos

**ETL.** Las capturas crudas (*bronze*) conservan archivo y huella; *silver* normaliza precio, moneda, fecha, producto y vendedor; *gold* deduplica por clave (fuente, identificador, fecha, vendedor) y excluye con motivo. Comprobamos la integridad del paquete del corte:'''),
        code('''
from sconto.esquema import CLAVE
integridad = {
    'duplicados por clave': int(obs.duplicated(CLAVE).sum()),
    'precios no positivos': int((obs.precio <= 0).sum()),
    'fechas no válidas': int(fecha.isna().sum()),
    'series con canal mezclado': int(obs.groupby('serie_id').canal.nunique().gt(1).sum()),
    'reproduce Avance 1 (QQP 2025 = 39,363 filas)': int((qqp.anio == 2025).sum()) == 39363,
}
display(pd.Series(integridad, name='resultado').to_frame())
eventos = M.eventos_buen_fin()
display(eventos[['evento_id', 'base_inicio', 'base_fin', 'previo_inicio', 'previo_fin', 'evento_inicio', 'evento_fin']]
        .assign(**{c: lambda d, c=c: d[c].dt.date for c in ['base_inicio', 'base_fin', 'previo_inicio', 'previo_fin', 'evento_inicio', 'evento_fin']}))
'''),
        md('''**Ventanas.** Para cada edición usamos la misma estructura: **base** (60 a 15 días antes), **previo** (14 días antes) y **evento** (fechas oficiales; 2020 duró 12 días por la pandemia). Una serie es comparable si tiene al menos **4 días con precio en la base que abarquen 21 días o más**, **2 días en el previo** y **1 en el evento**.

**Variables** (todas con precios *anteriores* al evento, para no mirar el futuro):

| Variable | Significado |
|---|---|
| `cambio_previo_pct` | Cambio entre el primer y el último precio de las 2 semanas previas |
| `alza_previa_pct` | Mediana del previo frente a la mediana de la base |
| `iqr_base_pct`, `iqr_previo_pct` | Dispersión (rango intercuartílico) relativa a la mediana |
| `n_base`, `n_previo`, `amplitud_base_dias`, `dias_desde_precio` | Cantidad y cercanía de la evidencia |
| `log_precio_previo` | Nivel de precio (logaritmo de la mediana previa) |

**Etiqueta "bajó"**: la mediana del evento quedó por debajo de la mediana del previo.

### 3.1 Decisiones justificadas con datos: ¿por qué 5 %? (pregunta 2)

La app clasifica un precio como **favorable** si está al menos 5 % por debajo de la mediana histórica **y** en el cuartil inferior (P25). ¿Por qué 5 % y no 2 % o 10 %?

**Método (prueba placebo).** Comparamos las ventanas reales del Buen Fin contra ventanas idénticas colocadas en **semanas normales** (15 de febrero, marzo, abril, julio, agosto y 1 de octubre de cada año; lejos del Buen Fin, del Hot Sale y de diciembre). Para cada umbral *t* medimos qué porcentaje de ventanas cumple la regla en el Buen Fin y en semanas normales. La diferencia es la **J de Youden** (señal − ruido): el mejor umbral es el que más separa ambas.'''),
        code('''
ventanas_cmp = M.ventanas_comparables(obs, CORTE)
print(f"Ventanas del Buen Fin: {ventanas_cmp.real.sum():,} · ventanas de semanas normales: {(~ventanas_cmp.real).sum():,}")
regla = M.curva_umbral(ventanas_cmp, 'ahorro_base_pct', con_p25=True)
sin_p25 = M.curva_umbral(ventanas_cmp, 'ahorro_base_pct')
etiqueta = M.curva_umbral(ventanas_cmp, 'bajada_previo_pct')
tabla = (regla.set_index('umbral_pct')[['pct_buen_fin', 'pct_semanas_normales', 'youden_j', 'lift']]
         .join(sin_p25.set_index('umbral_pct')[['pct_semanas_normales', 'youden_j']], rsuffix='_sin_P25'))
display(tabla.loc[[1, 2, 3, 4, 5, 7, 10, 15]].round(1))
fig, ejes = plt.subplots(1, 2, figsize=(12, 4))
for ax, (titulo, c) in zip(ejes, [('Regla de la app: ahorro vs. mediana base + P25', regla), ('Etiqueta del modelo: bajada vs. 2 semanas previas', etiqueta)]):
    ax.plot(c.umbral_pct, c.pct_buen_fin, 'o-', color='#2563eb', label='Buen Fin')
    ax.plot(c.umbral_pct, c.pct_semanas_normales, 'o-', color='#9ca3af', label='Semanas normales')
    ax.axvline(5, ls='--', color='#ea580c'); ax.set_title(titulo, fontsize=10); ax.set_xlabel('Umbral (%)'); ax.legend(); ax.grid(alpha=.2)
plt.tight_layout(); plt.show()
mejor = regla.loc[regla.youden_j.idxmax()]
print(f"Máxima separación con P25 en {mejor.umbral_pct:g} % (J = {mejor.youden_j:.1f}); con 5 %: J = {regla.set_index('umbral_pct').youden_j[5]:.1f}")
'''),
        code('''
# Búsqueda fina: 30 umbrales de 0.5 % a 15 % con IC95 por remuestreo de series (500 repeticiones)
from sconto import conclusiones as C
fina = C.busqueda_umbral(ventanas_cmp)
display(fina.loc[fina.umbral_pct.isin([1, 2, 3, 3.5, 4, 4.5, 5, 5.5, 6, 8, 10, 15])].round(2))
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.fill_between(fina.umbral_pct, fina.j_ic95_inf, fina.j_ic95_sup, color='#2563eb', alpha=.15, label='IC95')
ax.plot(fina.umbral_pct, fina.youden_j, 'o-', color='#2563eb', ms=3, label='J de Youden')
ax.scatter(fina.loc[fina.equivalente_al_mejor, 'umbral_pct'], fina.loc[fina.equivalente_al_mejor, 'youden_j'], color='#ea580c', zorder=3, label='Empatan con el mejor')
ax.axvline(5, ls='--', color='#ea580c'); ax.set_xlabel('Umbral (%)'); ax.set_ylabel('Señal − ruido (J)'); ax.legend(); ax.grid(alpha=.2)
ax.set_title('Búsqueda fina del umbral de la regla (con P25)'); plt.tight_layout(); plt.show()
mejor_f = fina.loc[fina.youden_j.idxmax()]
print(f"Mejor: {mejor_f.umbral_pct:g} % (J = {mejor_f.youden_j:.1f}, IC95 {mejor_f.j_ic95_inf:.1f}–{mejor_f.j_ic95_sup:.1f}). "
      f"Empatan estadísticamente: {', '.join(f'{u:g} %' for u in fina.loc[fina.equivalente_al_mejor, 'umbral_pct'])}. "
      f"Con 5 % la regla se activa en {fina.set_index('umbral_pct').pct_semanas_normales[5]:.1f} % de las semanas normales.")
'''),
        md('''**Lectura.**
- La separación (J) es casi plana entre **1 % y 6 %** y alcanza su máximo en 4 % (37.4); **5 % (36.9) está en esa meseta**. Entre umbrales que separan igual, conviene el que da **menos falsas alarmas**: con 2 % la regla se activa en 24.6 % de las semanas normales y con 5 % en 21.3 % (lift 2.5 contra 2.7).
- Con **10 %** la separación cae (J = 31.7) porque se pierde una de cada cinco rebajas reales del Buen Fin (de 58 % a 47 %).
- **Búsqueda fina:** probamos 30 umbrales (de 0.5 % a 15 %, de medio en medio punto). El máximo está en 4 %, pero 2 %, 3.5 %, 4.5 % y 5 % empatan estadísticamente con él (la diferencia remuestreada incluye cero). Dentro de ese grupo, **5 % es el que da menos falsas alarmas** (21.3 % de semanas normales contra 22.7 % con 4 %) y el de mayor lift. Por eso usamos 5 %, y no 2 % ni 10 %.
- Exigir además el **cuartil inferior (P25)** mejora la separación en todos los umbrales: reduce las falsas alarmas en semanas normales sin perder rebajas del evento.
- Para la **etiqueta del modelo** cualquier bajada ya es 2.5 veces más frecuente en el Buen Fin que en semanas normales (J máxima cerca de 0–1 %), por eso "bajó" no lleva umbral adicional.

### 3.2 ¿Por qué cuatro fechas en la base?

Si la mediana de referencia se calcula con pocos días, su error puede superar el 5 % que queremos detectar. Para series con 6 o más días en la base, simulamos tener sólo *k* días al azar y medimos el error frente a usar todos.'''),
        code('''
precision = M.precision_referencia(obs)
display(precision.round(2))
'''),
        md('''Con **4 días**, la mediana se equivoca 5 % o más sólo en ≈ 10 % de los casos (percentil 90 del error ≈ 5 %); con 3 días el error del percentil 90 sube a ≈ 5.6 %, y con 1–2 días a 10–11 %. Pedir 5 días baja el error, pero deja fuera cerca del 40 % de las series que sí tienen 4. **Cuatro días es el punto de equilibrio entre precisión y cobertura.**

### 3.3 Conjunto de datos final para modelar

Una fila por serie y edición del Buen Fin. Entrenamiento y prueba con QQP; validación final 2026 con dos fuentes que el modelo nunca vio: Preciómetro (mínimo en línea; como la tienda del mínimo cambia, sólo se relaja la identidad de sucursal) y el piloto PROFECO.'''),
        code('''
datos = M.dataset_modelado(obs, piloto, CORTE)
conteo = (datos.groupby(['evento_id', 'poblacion', 'conjunto'])
          .agg(series=('y', 'size'), bajaron=('y', 'sum'), productos=('id_externo', 'nunique')))
conteo['% bajó'] = 100 * conteo.bajaron / conteo.series
display(conteo.round(1))
muestra = datos.sample(10, random_state=42)
display(muestra[['evento_id', 'poblacion', 'categoria', 'tienda', *M.VARIABLES_EXTENDIDAS, 'bajada_evento_pct', 'y']])
datos.to_csv(SALIDA / 'dataset_final_modelado.csv', index=False)
muestra.to_csv(SALIDA / 'muestra_10_instancias.csv', index=False)
print(f'Dataset final: {len(datos):,} filas × {datos.shape[1]} columnas')
'''),
        md('''---
## 4. Modelado (pregunta 3)

**Esquema temporal (nunca se usa el futuro para aprender):**

| Etapa | Ediciones | Uso |
|---|---|---|
| Entrenamiento | 2018–2023 | Ajustar los modelos |
| Validación | 2022, 2023, 2024 (cada año entrenado sólo con los anteriores) | Elegir hiperparámetros y el modelo |
| Prueba | 2025 | Medir el desempeño final; no participa en ninguna decisión |
| Validación final | 2026 (Preciómetro y PROFECO) | ¿Funciona en un año nuevo y en otras fuentes? |

**Modelos comparados**

- **Líneas base:** (a) clase mayoritaria ("siempre baja"); (b) regla de una variable, p. ej. "bajará si ya venía bajando en las dos semanas previas".
- **Regresión logística** (C, pesos de clase, con y sin nivel de precio).
- **Árbol de decisión** (profundidad 2–6, tamaño mínimo de hoja, pesos de clase).
- **Random Forest** (300 árboles; profundidad, hoja y pesos).
- **Isolation Forest** (no supervisado; 10 variantes de contaminación y variables) y una variante híbrida **Random Forest + puntaje de rareza de Isolation Forest**.

El Isolation Forest no aprende con etiquetas: detecta series raras. Para medir su accuracy, la etiqueta sólo se usa para decidir si "rara" significa "bajará" o "no bajará".'''),
        code('''
candidatos = M.candidatos()
print(len(candidatos), 'variantes:', pd.Series([c.familia for c in candidatos]).value_counts().to_dict())
folds, seleccion = M.validacion_movil(datos, candidatos)   # tarda varios minutos
elegidos = M.elegir(seleccion)
display(elegidos.round(3))
print('Variantes de Isolation Forest (validación):')
display(seleccion.loc[seleccion.familia.eq('Isolation Forest')].sort_values('bal_acc_validacion', ascending=False).head(6).round(3))
'''),
        md('''---
## 5. Evaluación (preguntas 3 y 4)

Cada familia usa su mejor variante de validación. Para la **prueba 2025** se reentrena con 2018–2024; para la **validación final 2026**, con 2018–2025. Los intervalos de confianza (IC95) se obtienen remuestreando productos completos (1,000 repeticiones).'''),
        code('''
finales, predicciones, modelos = M.evaluar(datos, candidatos, elegidos)
supervisados = elegidos.loc[~elegidos.familia.str.startswith('Línea base')]
ELEGIDO = supervisados.sort_values(['bal_acc_validacion', 'auc_validacion'], ascending=False).iloc[0]
print('Modelo elegido con la validación (antes de ver la prueba):', ELEGIDO.familia, '·', ELEGIDO.variante)
tabla = finales[['conjunto', 'familia', 'n', 'accuracy', 'balanced_accuracy', 'precision', 'recall', 'f1', 'auc', 'balanced_accuracy_ic95']].copy()
tabla['balanced_accuracy_ic95'] = tabla.balanced_accuracy_ic95.map(lambda v: f'[{v[0]:.2f}, {v[1]:.2f}]')
for conjunto, parte in tabla.groupby('conjunto', sort=False):
    print('\\n' + conjunto); display(parte.drop(columns='conjunto').sort_values('balanced_accuracy', ascending=False).round(3))
finales.to_csv(SALIDA / 'metricas_finales.csv', index=False)
'''),
        code('''
from sklearn.tree import plot_tree
pivote = finales.pivot_table(index='familia', columns='conjunto', values='balanced_accuracy', sort=False)
ax = pivote.plot.barh(figsize=(10, 4.5), color=['#2563eb', '#ea580c', '#9ca3af'], width=.8)
ax.axvline(.5, ls=':', color='black'); ax.set_xlim(.3, 1); ax.set_xlabel('Balanced accuracy (0.5 = adivinar)')
ax.legend(loc='upper center', bbox_to_anchor=(.5, -.15), ncol=3, frameon=False); plt.tight_layout(); plt.show()

sel = predicciones.loc[predicciones.familia.eq(ELEGIDO.familia)]
fig, ejes = plt.subplots(1, 3, figsize=(13, 3.6))
for ax, (nombre, p) in zip(ejes, sel.groupby('conjunto', sort=False)):
    m = pd.crosstab(p.y, p.prediccion).reindex(index=[0, 1], columns=[0, 1], fill_value=0)
    ax.imshow(m, cmap='Blues')
    for (i, j), v in np.ndenumerate(m.to_numpy()): ax.text(j, i, v, ha='center', va='center', fontsize=12)
    ax.set_xticks([0, 1], ['No bajará', 'Bajará']); ax.set_yticks([0, 1], ['No bajó', 'Bajó']); ax.set_title(nombre, fontsize=9)
plt.suptitle(f'Matrices de confusión · {ELEGIDO.familia}'); plt.tight_layout(); plt.show()

final = modelos[ELEGIDO.familia]
variables = next(c.variables for c in candidatos if (c.familia, c.variante) == (ELEGIDO.familia, ELEGIDO.variante))
display(M.importancias(final, variables).round(3))
if ELEGIDO.familia == 'Árbol de decisión':
    plt.figure(figsize=(18, 7)); plot_tree(final, feature_names=variables, class_names=['no baja', 'baja'], filled=True, fontsize=7, impurity=False, proportion=True)
    plt.title('Árbol final (entrenado con 2018–2025)'); plt.show()
'''),
        code('''
# ¿Ayudó agregar ediciones del Buen Fin? Mismo árbol elegido, distinto entrenamiento, misma prueba 2025
qqp_d = datos.loc[datos.fuente.eq('qqp_cdmx')]
cand = next(c for c in candidatos if (c.familia, c.variante) == (ELEGIDO.familia, ELEGIDO.variante))
prueba = qqp_d.loc[qqp_d.anio.eq(2025)]
filas = []
for nombre, entrenamiento in [('sólo Buen Fin 2024', qqp_d.loc[qqp_d.anio.eq(2024)]), ('Buen Fin 2018–2024', qqp_d.loc[qqp_d.anio.le(2024)])]:
    _, pred, prob = M._ajustar_predecir(cand, entrenamiento, prueba)
    filas.append(dict(entrenamiento=nombre, series=len(entrenamiento), **{k: v for k, v in M.metricas(prueba.y, pred, prob).items()
                                                                        if k in ('accuracy', 'balanced_accuracy', 'f1', 'auc')}))
display(pd.DataFrame(filas).round(3))
'''),
        md('''**Lectura de resultados**

- **El modelo supera claramente a la línea base que siempre dice "baja"** en datos que no vio: balanced accuracy ≈ 0.78 en 2025 y ≈ 0.68 en 2026 contra 0.50. En accuracy simple la diferencia parece pequeña (79.6 % contra 77.4 % en 2025) porque la mayoría de las series bajó; por eso elegimos con balanced accuracy.
- **La variable clave es la tendencia de las dos semanas previas** (`cambio_previo_pct`, ≈ 73 % de la importancia): si el precio ya venía bajando, probablemente baje en el evento. Le siguen la subida o bajada frente a la base y el nivel de precio.
- **La regla simple con esa variable compite con los modelos** (balanced accuracy 0.80 en 2025 y 0.72 en 2026) y sus intervalos se traslapan con los del árbol. Es un aprendizaje importante: la señal es simple y robusta; los modelos añaden matices (nivel de precio, alza previa) y probabilidades, pero no una mejora significativa.
- **Random Forest + puntaje de Isolation Forest** logra la mayor accuracy en 2025 (86 %), pero no fue la mejor en validación y baja en 2026: elegirlo por la prueba habría sido hacer trampa.
- **La regresión logística y el Isolation Forest no generalizan a 2026**: en Preciómetro predicen "baja" para todo (balanced accuracy 0.50). Las variables de conteo (`n_base`: mediana de 46 días en Preciómetro contra 5 en QQP) cambian de escala entre fuentes y los modelos lineales o de rareza extrapolan mal; los árboles son más robustos a ese cambio.
- **Isolation Forest sirve para detectar rarezas, no para predecir bajadas**: su mejor variante (contaminación 0.4) llega a 0.69 en validación, por debajo de los modelos supervisados.'''),
        md('''---
## 5.1 ¿La app detecta "estafas"? Rebajas reales, aparentes y precios señuelo

Nos interesan tres trucos comunes:

1. **Subir antes y bajar en el evento.** El precio sube en las semanas previas y "baja" en el Buen Fin, pero al final cuesta lo mismo o más que antes.
2. **Sin oferta real.** El precio cambia poco (menos de 5 % frente a su historia), aunque se anuncie como oferta.
3. **Precio señuelo.** Una tienda muestra el mismo producto mucho más caro; al compararte con ella cualquier otro precio parece una gran oferta.

Para cada serie comparamos el precio del evento contra **su historia** (la base) y contra **las dos semanas previas** (lo que recuerda un comprador). "Parece oferta" si está al menos 5 % por debajo de las dos semanas previas; es **rebaja real** si está al menos 5 % por debajo de su historia. Todo se contrasta con semanas normales.'''),
        code('''
patrones_bf = C.clasificar(ventanas_cmp)
s26 = C.clasificar(C.series_2026(obs, piloto, CORTE))
grupos = {'QQP sucursales · Buen Fin 2018–2025': patrones_bf.loc[patrones_bf.real],
          'QQP sucursales · semanas normales': patrones_bf.loc[~patrones_bf.real],
          'PROFECO sucursales · Buen Fin 2026': s26.loc[s26.fuente.eq('profeco_bf2026')],
          'Preciómetro en línea · Buen Fin 2026': s26.loc[s26.fuente.eq('preciometro')]}
patrones = C.resumen_poblaciones(grupos).set_index('poblacion')
display(patrones.T.round(1))
dispersion = C.resumen_dispersion(C.dispersion_tiendas(obs)).set_index('fuente')
display(dispersion.T.round(1))
C.figuras(SALIDA, patrones.reset_index(), C.dispersion_tiendas(obs))
from IPython.display import Image
display(Image(str(SALIDA / 'fig_patrones_precio.png'))); display(Image(str(SALIDA / 'fig_precio_senuelo.png')))
'''),
        md('''**Lectura (respuestas con datos)**

- **¿La mayoría no tiene una señal clara?** Depende del canal. En **sucursales físicas** (QQP 2018–2025) el 58 % de los precios del Buen Fin fue *favorable* (≥ 5 % bajo su historia y en el cuartil inferior), contra 21 % en semanas normales: ahí sí hay rebajas reales. **En línea** (Preciómetro, primeros días del Buen Fin 2026) sólo el 45 % fue favorable: **más de la mitad no mostró una oferta clara** (44 % sin señal y 10 % más caro que su historia). Tu hipótesis se confirma para las tiendas en línea.
- **Subir y bajar:** el 11 % de las series de sucursales subió al menos 5 % antes del Buen Fin y luego bajó; es 1.5 veces más frecuente que en semanas normales (7 %). En **22 % de esos casos el comprador terminó pagando lo mismo o más** que antes de la subida, y en 28 % no hubo ahorro real. En línea (2026) fue 27 % y 33 %.
- **Ofertas que engañan:** si comparas contra el precio de las dos semanas previas, 6 % de las "ofertas" del Buen Fin y **30 % de las de semanas normales no son ahorro real**. La regla de Sconto compara contra la historia y **no marcó ninguna de esas como favorable** (0 %): el truco de inflar el precio de referencia no la engaña.
- **Precio señuelo:** para el mismo producto el mismo día, la tienda en línea más cara está en mediana **17.5 % arriba** del precio típico, y en 30 % de los casos 30 % o más. Comparar contra ella produce un "descuento" aparente de 15 % sin ahorro real; entre la más barata y la más cara hay 40 % de diferencia. En sucursales físicas la dispersión es menor (11 % y 22 %).
- **¿Con qué precisión?** No existen etiquetas oficiales de "estafa", así que medimos la regla contra su definición operativa: 0 % de rebajas aparentes marcadas como favorables, y un costo de 21 % de falsas alarmas en semanas normales (precios favorables que no son del evento, pero sí son bajos frente a su historia). El modelo predictivo, por su parte, acierta con balanced accuracy de 0.78 (2025) y 0.68 (2026).'''),
        md('''---
## 6. Despliegue

**Arquitectura:** fuentes públicas → ETL bronze/silver/gold con huellas → modelo (scikit-learn) → **API FastAPI en Fly.io** (una máquina, volumen cifrado, límite de gasto) → **app web instalable** (PWA) y APK que funcionan sin conexión con el último corte.

**Qué hace la app v3**
- **"¿Qué precio ves hoy?"**: escribes el precio que encontraste y lo compara con la historia del producto usando la regla validada (5 % + cuartiles).
- **"¿Bajaría en el Buen Fin?"**: muestra la predicción del modelo para 187 productos y si acertó en 2026.
- **"El modelo"**: tarjeta con el esquema temporal, métricas, reglas justificadas y arquitectura.

**API pública** ([documentación interactiva](https://sconto-v2-api.fly.dev/docs)): `GET /v1/modelo`, `GET /v1/products/{id}/prediccion`, `GET /v1/products/{id}/evaluar-precio?precio=`, y `POST /v1/predecir`, que recibe el historial de **cualquier** producto de tecnología y responde si bajará en el Buen Fin, con la explicación del árbol. El servidor no necesita scikit-learn: el árbol se exporta a JSON y se evalúa con Python puro (las pruebas verifican que da exactamente lo mismo).'''),
        code('''
from sconto.app_modelo import exportar_arbol
from sconto import prediccion_ligera as L
from datetime import date
if ELEGIDO.familia == 'Árbol de decisión':
    arbol = exportar_arbol(final, variables)
    ejemplo = [(date(2026, 9, 15), 8999), (date(2026, 9, 22), 8999), (date(2026, 9, 29), 9199), (date(2026, 10, 6), 8999),
               (date(2026, 10, 13), 8999), (date(2026, 10, 20), 9099), (date(2026, 10, 27), 8999),
               (date(2026, 10, 31), 8799), (date(2026, 11, 7), 8499), (date(2026, 11, 11), 8399)]
    x = L.caracteristicas(ejemplo, date(2026, 11, 13))
    print('Pantalla de ejemplo · ¿bajará en el Buen Fin 2026?', 'sí' if L.evaluar_arbol(arbol, x) >= .5 else 'no')
    for paso in L.ruta_arbol(arbol, x): print('  ·', paso)
    print('Precio de $7,999 frente a la base:', L.regla_precio(7999, x['mediana_base'], x['p25_base'], x['p75_base'])['estado'])
try:
    tarjeta = json.loads(urlopen('https://sconto-v2-api.fly.dev/v1/modelo', timeout=15).read())
    print('API en línea · modelo:', tarjeta['modelo']['familia'], '· productos con predicción:', tarjeta['productos_con_prediccion'])
except Exception as error:
    print('La API pública no respondió (el servidor puede estar apagado después de la presentación):', type(error).__name__)
'''),
        code('''
import joblib
joblib.dump(dict(modelo=final, variables=variables, familia=ELEGIDO.familia, variante=ELEGIDO.variante), SALIDA / 'modelo_final.joblib')
seleccion.to_csv(SALIDA / 'seleccion_variantes.csv', index=False)
tabla_umbral = M.curva_umbral(ventanas_cmp, 'ahorro_base_pct', con_p25=True); tabla_umbral.to_csv(SALIDA / 'umbral_regla_app.csv', index=False)
manifiesto = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SALIDA.iterdir()) if p.is_file()}
(SALIDA / 'manifiesto.json').write_text(json.dumps(dict(corte=CORTE, sha256_paquete=SHA_PAQUETE, archivos=manifiesto), indent=2))
print(json.dumps(manifiesto, indent=1))
'''),
        md('''---
## Conclusiones y aprendizajes

| Pregunta | Respuesta con datos |
|---|---|
| 1. ¿Bajan los precios en el Buen Fin? | Sí, ≈ 9 % en promedio durante el evento, desde la semana previa, y se recuperan la semana siguiente. No todos bajan: la mediana semanal es 0 %. |
| 2. ¿Por qué 5 %? | Con el cuartil P25, 5 % está en la meseta donde mejor se separan las rebajas del Buen Fin de las variaciones normales (J máxima en 4 %). Frente a 2 % separa igual pero con menos falsas alarmas; 10 % pierde una de cada cinco rebajas reales. Cuatro días en la base mantienen el error de referencia por debajo de 5 % en 9 de cada 10 series. |
| 3. ¿Se puede predecir? | Sí: el árbol de decisión supera claramente a la línea base (balanced accuracy 0.78 contra 0.50 en 2025). La señal principal es si el precio ya venía bajando. |
| 4. ¿Funciona con datos nuevos? | Parcialmente: en 2026, con precios en línea que nunca vio, mantiene 0.68 de balanced accuracy y 72 % de accuracy. Los modelos lineales y el Isolation Forest no resistieron el cambio de fuente. |
| 5. ¿La app detecta "estafas"? | Sí para el truco de inflar la referencia: ninguna rebaja aparente (subir y bajar, o comparar contra el precio reciente) fue marcada favorable. 11 % de las series subió antes del Buen Fin y bajó; en 22 % de esos casos el precio final fue igual o mayor. |
| 6. ¿La mayoría no tiene señal clara? | En línea sí: en el Buen Fin 2026 más de la mitad (55 %) no mostró una oferta clara. En sucursales físicas no: 58 % fue favorable. |
| 7. ¿Existen precios señuelo? | Sí: la tienda en línea más cara del mismo producto está 17.5 % arriba del precio típico (30 % o más en 3 de cada 10 casos); compararte con ella simula un 15 % de descuento. |

**Aprendizajes**
1. **Validar en el tiempo cambia las conclusiones.** Elegir por la prueba habría inflado los resultados; la validación por años muestra el desempeño real.
2. **Más ediciones del evento dan modelos más estables.** Con el mismo árbol, entrenar con 2018–2024 en lugar de sólo 2024 subió la balanced accuracy de 2025 de 0.757 a 0.784 y el AUC de 0.76 a 0.79, y permitió validar año por año.
3. **Una regla simple bien justificada es una línea base exigente.** Si un modelo no la supera con claridad, la app debe explicar ambas cosas.
4. **Los umbrales se justifican con señal contra ruido** (prueba placebo), no por costumbre.
5. **Conservar los datos es parte del modelo:** sin capturas guardadas durante el evento no hay validación 2026.
6. **El descuento anunciado no es la referencia correcta.** Comparar contra la historia del producto, y no contra el precio reciente o la tienda más cara, es lo que separa una oferta real de una aparente.

**Límites y trabajo futuro.** QQP 2026 no se publicó con el evento, no hay datos después del 17 de noviembre y no hubo ofertas en línea verificadas con vendedor, inventario y total. La misma arquitectura (colector → ETL con huellas → modelo → API → app) puede aplicarse a otras categorías o fuentes autorizadas; en este proyecto nos limitamos a tecnología.'''),
    ]
    return n


def main():
    n = crear()
    nbf.write(n, SALIDA)
    print(SALIDA, len(n.cells), 'celdas')


if __name__ == '__main__':
    main()
