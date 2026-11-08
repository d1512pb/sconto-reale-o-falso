# Sconto reale o falso · recolección multifuente de precios

## Avance 2: notebook completo y datos para la app

Abrir [03 · CRISP-DM y ETL en Colab](https://colab.research.google.com/drive/1bnrjKM-Wz0YPo8UuQKrEHBm4mtDrn3KP).
La copia en Drive contiene resultados de una **ejecución local completa**, sin errores. No se afirma una ejecución en la nube.
El cuaderno 01 original permanece intacto. El 03 fija código, dependencias y snapshot por hash para reproducir el avance.

La edición del 7 de noviembre ejecuta el ETL desde 1,015,811 capturas extraídas, reconstruye 683,942 observaciones,
reproduce el Avance 1 y documenta las seis fases de CRISP-DM. Incluye extracción de una evidencia pública real,
cobertura diaria, Isolation Forest temporal, búsqueda por nombre y reglas de precio con demo de Sears/Liverpool.

Produce `entrega_sconto.zip`: dataset limpio completo en Parquet/CSV.gz, auditoría, diccionario y un segundo ZIP
con SQLite, tablas de consulta, JSON de la app, índice de búsqueda y manifiestos. Ver [CONTRATO_APP.md](CONTRATO_APP.md).
La app instalable y la actualización diaria ya consumen este mismo contrato. La entrega académica permanece
congelada; el job `analitica` genera una edición nueva con cada snapshot. Conserva el [contrato web anterior](CONTRATO_WEB.md).

En Colab, ejecutar todas las celdas en CPU; al final se puede activar `DESCARGAR` o `GUARDAR_EN_DRIVE`.
El bootstrap descarga entradas públicas congeladas y verifica cada hash. Para repetir la comprobación local
con las entradas del corte disponibles: `python notebooks/ejecutar_notebook_03.py`.
El generador `notebooks/crear_notebook_03.py` mantiene el notebook a partir de `config/avance2.json`.

Consulta pública: [Sconto · Antes de comprar](https://d1512pb.github.io/sconto-reale-o-falso/).
GitHub Pages publica una proyección JSON del mart; no necesita servidor, nuevas cuentas ni costos.
El sitio muestra corte, historia, ofertas por vendedor y evidencia insuficiente. El código está en `web/`.
Construcción local: `python -m sconto.publicar_web`. El despliegue usa las
[acciones oficiales de Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
Para actualizar el sitio desde el último paquete sin hacer otra captura, ejecutar el workflow con
`solo_analitica=true`. La web enlaza a la copia pública del notebook en GitHub; el archivo en Drive conserva su acceso original.

Para ejecutar el mismo análisis en la PC:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-analitica.txt
gh release download datos --repo d1512pb/sconto-reale-o-falso --pattern sconto_colab_actual.zip --dir data/exportaciones --clobber
.\.venv\Scripts\python.exe -m sconto.mart --paquete data/exportaciones/sconto_colab_actual.zip
```

Para abrir el prototipo con SQLite:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

También acepta `SCONTO_WEB_DATOS` como carpeta de exportación o `SCONTO_WEB_URL` como URL HTTPS del
ZIP analítico publicado. El prototipo muestra fechas de corte y faltantes; no consulta tiendas al navegar.
La nube de Colab no aloja la aplicación. La revisión de variantes y de casos del modelo sigue pendiente.

**ESCOM-IPN · Minería de Datos** · Daniel Peredo Borgonio · Kevin Celis Torres · Igor Cappelli

Pregunta del proyecto: ¿los descuentos de **El Buen Fin** en productos de tecnología son reales o simulados?
El Avance 1 usó sólo PROFECO QQP 2025 (CDMX). Este repositorio añade más fuentes, más eventos (BF2024, BF2025,
BF2026), análisis por día y, sobre todo, **precio anunciado / tachado** para comparar lo que la tienda promete
contra lo que muestra el historial.

> Todo es gratuito y open source: sin APIs, proxies ni servicios de scraping de pago.
> La carpeta padre `Sconto/` (evidencia del Avance 1) sólo se lee; nunca se modifica.

## Estado y arranque · 21 de octubre de 2026

Este repositorio es la **recolección y preparación**; el análisis posterior se hace en Colab.
Se revisaron el proyecto y su plan en Notion, el notebook del Avance 1 en Drive y las salidas locales.
No se modificó el notebook de Drive ni la evidencia del Avance 1.

- Históricos: hay archivos y tablas QQP locales de 2018–2026; Preciómetro conserva el historial que realmente publica,
  y Wayback aporta las capturas localizadas. Tener un conector no garantiza que exista una captura para cada fecha.
- Actualidad: Preciómetro, API oficial de Mercado Libre y fichas de tiendas de una lista explícita.
  **La API ML requiere autorización**; sin token se registra el faltante, no se simulan datos.
- Amazon directo está **deshabilitado por decisión del equipo**. Sus precios se recuperan de las ofertas del
  agregador y de archivos históricos, siempre identificados como evidencia indirecta.
- Liverpool tiene un piloto real del configurador del SKU, con precio actual y tachado. Sears está preparado,
  pero **sin extracción real integrada**. Las fichas habilitadas están en `config/tiendas_objetivo.csv`.
- Los emparejamientos anteriores podían confundir Tab A9 y A9+. Ahora se conservan como `probable` hasta validar
  código, capacidad, RAM, color y generación. Los precios se conservan independientemente de ese cruce.
- La operación diaria utiliza una lista fija de **200 productos** de ocho familias; no rota productos entre días.
  Los demás productos conservan su backfill, pero no se promete captura diaria de sus ofertas.
  La evidencia de despliegue se registra en `reports/operacion_diaria.md`; un cron definido no prueba una corrida exitosa.

Desde esta carpeta, sin consultas de red:

```powershell
.\.venv\Scripts\python.exe -m sconto.backfill
.\.venv\Scripts\python.exe -m sconto.backfill --ejecutar --sin-red --fuentes qqp wayback commoncrawl
.\.venv\Scripts\python.exe -m sconto.run_diario --plan
.\.venv\Scripts\python.exe -m sconto.dataset
.\.venv\Scripts\python.exe -m sconto.exportar
```

Con red, empezar con una prueba acotada:

```powershell
.\.venv\Scripts\python.exe -m sconto.run_diario --fuentes preciometro --max-productos 3
.\.venv\Scripts\python.exe -m sconto.fuentes.mercadolibre --plan
.\.venv\Scripts\python.exe -m sconto.run_diario --fuentes tiendas
.\.venv\Scripts\python.exe -m sconto.backfill --fuentes qqp --anios 2026 --actualizar-qqp --ejecutar
```

El ZIP en `data/exportaciones/` contiene parquet, CSV y manifiesto SHA-256, **no crudos ni credenciales**.
Abrir `notebooks/00_Cargar_paquete_Colab.ipynb` en Colab: carga el ZIP público del release `datos` y verifica hashes.
También permite subir un ZIP local. `02_Sconto_multifuente.ipynb` es una base de análisis,
no sustituye al notebook del equipo ni demuestra una ejecución en Colab.

### Mapeos y tiendas nuevas

Revisar `reports/matches_para_revisar.csv`; anotar únicamente confirmaciones humanas en
`config/mapeos_validados.csv` (producto canónico, tipo e ID externo, `validado=1`, fecha, notas).
`python -m sconto.emparejar` aplica esas decisiones y rechaza IDs compartidos incompatibles.
No editar las columnas `*_candidatos` para habilitar una descarga.

En `config/tiendas_objetivo.csv`, una ficha sólo se consulta con `habilitado=1`, producto canónico y confianza
`exacto`/`verificado`/`alta`. Las dos URLs iniciales provienen de ofertas reales, no de un catálogo rastreado.
No habilitar Sears hasta resolver su URL final y validar su estructura sin evadir bloqueos.

## Estructura

```
config/     productos_objetivo.csv (lista fija), preciometro_lista.csv, eventos.yaml, fuentes.yaml
src/sconto/ cliente.py (HTTP respetuoso), almacen.py (crudos + bronze + estado), esquema.py, normalizar.py,
            emparejar.py (Fase 1), run_diario.py (Fase 3), dataset.py (Fase 5), fuentes/<fuente>.py
data/raw/<fuente>/<fecha>/   respuesta cruda comprimida (.gz) — su SHA-256 viaja en cada fila
data/bronze/<fuente>/        filas normalizadas por fecha de captura
data/gold/                   dataset final (ver DICCIONARIO.md)
data/estado/<entorno>.csv    ok / fallo / bloqueado / sin_credenciales por fuente y día
reports/                     cobertura por fuente, matches para revisar, resumen de recolección
notebooks/                   02_Sconto_multifuente.ipynb (CRISP-DM, corre en Colab)
```

## App instalable

Abre [Sconto](https://d1512pb.github.io/sconto-reale-o-falso/) y busca por nombre o modelo.
El catálogo aprovecha los **1,493 productos** con datos en línea ya recolectados: 233 celulares, 146 tabletas,
215 computadoras y laptops, 243 audífonos, 223 productos de audio, 275 pantallas, 110 cámaras y lentes,
8 proyectores, 23 dispositivos de streaming y 17 de hogar inteligente. Hay filtros de categoría, Sears y Liverpool; cada ficha muestra vendedores, precios fechados,
historia, referencia de mercado y una señal explicada. Los anuncios sólo aparecen cuando fueron observados.
No hay registro, perfiles, publicaciones ni seguimiento de búsquedas.

La interfaz incluye transiciones breves, filtros activos fáciles de quitar y accesos a tiendas e historial.
Al seleccionar Sears o Liverpool, tanto la tarjeta como el resumen usan las ofertas de esa plataforma.
Puedes tocar la gráfica o recorrer sus días con el control deslizante y las flechas del teclado. No se rellenan
fechas faltantes. Las animaciones respetan la preferencia de movimiento reducido del dispositivo.

- **Android / Chrome:** menú ⋮ → Instalar aplicación (o Añadir a pantalla de inicio).
- **iPhone / Safari:** Compartir → Añadir a pantalla de inicio.
- El botón **Instalar app** incluye las instrucciones y ofrece el instalador del navegador cuando está disponible.
- Abre la app con internet una vez. Guarda el catálogo y los resúmenes verificados para consultar sin conexión.
  El historial y las ofertas completas se descargan al abrir cada producto; se conservan hasta 40 fichas.
  Sin conexión sólo se pueden abrir las fichas guardadas que correspondan al mismo corte del catálogo.
  Si no puede actualizar, muestra un aviso. Los registros de más de un día dejan de tener indicador vigente,
  incluso si se abre una copia guardada. La fecha se calcula en CDMX.
- **Actualizar** consulta el último corte. **Actualizar app** aparece cuando hay una versión nueva de la interfaz.

La carga inicial del catálogo ampliado ocupa 8.87 MB antes de compresión HTTP en la prueba local del corte
7 de noviembre; cada ficha adicional ocupa una mediana de 13 KB. El tamaño cambia con el dataset. No requiere servidor propio:
`sconto.mart` genera las tablas y el índice del notebook; `sconto.publicar_web` verifica sus hashes y construye
la app en `data/analitica/site`. `snapshot.json` apunta a un JSON con nombre y contenido verificados por SHA-256;
una descarga incompleta no reemplaza la copia válida. Cada ficha también se valida por SHA-256, producto y corte.
El navegador conserva una copia del catálogo y hasta 40 fichas descargadas.

La lista de recolección diaria sigue siendo de **200 productos**. Ampliar la consulta no amplía las peticiones
a tiendas: la mayoría de las incorporaciones tiene su último registro en octubre y se presenta como historia.
El ETL diario incluye todos los productos nativos de Preciómetro con observaciones en línea; `--solo-seleccion`
limita `sconto.mart` a la lista diaria. El notebook 03 y su entrega académica de 200 productos permanecen congelados.

El workflow diario genera `sconto_web_actual.zip` y publica en Pages. Para actualizar desde el último dataset
sin recolectar otra vez: **Actions → Recolección diaria de precios → Run workflow → solo_analitica**.
La app no ejecuta scraping mientras la usas. La instalación real en Android/iPhone queda pendiente de probar
en un teléfono; búsqueda, diseño adaptable, actualización y reapertura sin conexión se prueban en navegador.

Para desarrollar localmente (después de generar el mart):

```powershell
.venv/Scripts/python.exe -m sconto.publicar_web
.venv/Scripts/python.exe -m http.server 8847 --bind 127.0.0.1 --directory data/analitica/site
```

Abre `http://127.0.0.1:8847/`. Las pruebas de búsqueda, vigencia y caché requieren Node.js 22:
`python -m pytest tests/test_app_movil.py tests/test_publicar_web.py tests/test_compra.py tests/test_catalogo.py -q`.
Ver [contrato de datos](CONTRATO_APP.md) y [reporte de implementación](reports/app_movil_2026-11-07.md).
La [ampliación del catálogo](reports/ampliacion_catalogo_2026-11-08.md) documenta los conteos, la antigüedad y las pruebas de la versión publicada.

## Instalación

```bash
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip install -e .
```

Copia `.env.example` a `.env` (está en `.gitignore`). Hoy sólo se usa `SCONTO_CONTACTO` (va en el user-agent).

## Cómo correr

```bash
# Fase 1: lista de productos objetivo y emparejamiento QQP ↔ Preciómetro ↔ ASIN/MLM
.venv/Scripts/python.exe -m sconto.lista_preciometro data/raw/preciometro_sitemap/2026-10-16/productos_sitemap.xml
.venv/Scripts/python.exe -m sconto.emparejar

# Fase 2: backfill (cada fuente es reanudable e idempotente; ver reports/cobertura_<fuente>.md)
.venv/Scripts/python.exe -m sconto.fuentes.preciometro_lote
.venv/Scripts/python.exe -m sconto.fuentes.qqp --help

# Fase 3: colector diario (lo lanzan GitHub Actions y el Programador de tareas)
.venv/Scripts/python.exe -m sconto.run_diario --entorno local

# Fase 5: dataset gold y validaciones
.venv/Scripts/python.exe -m sconto.dataset
.venv/Scripts/python.exe -m pytest -q
```

## Scraping responsable (reglas obligatorias)

1. **Lista fija de productos** (`config/productos_objetivo.csv`, `config/preciometro_lista.csv`). No se rastrean
   catálogos completos. La lista amplia de Preciómetro se tomó una sola vez de su `productos_sitemap.xml` público.
2. **Una petición cada 3–8 s por sitio, con jitter** (`sconto/cliente.py`). Wayback y Common Crawl: ≤ 1 por segundo.
3. **Una pasada diaria actualmente**. La segunda está reservada, pero desactivada hasta conservar ambas capturas
   intradía; no se anuncia como funcional cuando sólo reutiliza el crudo del día.
4. **User-agent honesto**: `ScontoRealeOFalso/0.1 (proyecto academico ESCOM-IPN, Mineria de Datos; uso no comercial; contacto: +https://github.com/d1512pb/sconto-reale-o-falso)`.
5. **robots.txt se respeta**: el cliente lo consulta antes de cada ruta y no pide lo que prohíbe.
6. **Nada de login, CAPTCHAs, proxies rotativos, cuentas falsas ni suplantar un navegador.**
7. **CAPTCHA, 403 o 503 persistente → `bloqueado`**: se registra, no se reintenta en bucle y se vuelve a intentar al día siguiente.
8. **Sólo datos públicos de precio**; nada de datos personales (nombres de reseñistas o de usuarios).
9. **Uso académico, no comercial**; cada fuente se cita en `reports/` y en el notebook.
10. **No se imputa**: un día sin dato es un faltante; no se rellena con 0 ni se borran valores extremos.

## Programación diaria

Esquema **híbrido**, sin un agente de IA en cada corrida:

- Preciómetro y ML: configuración para GitHub Actions; respaldo local explícito.
- Liverpool/Sears: lista fija en la PC, sólo fichas habilitadas y verificadas.
- Amazon directo: deshabilitado; no se configura una tarea para sortear sus bloqueos.

### GitHub Actions

`.github/workflows/recoleccion_diaria.yml` define una pasada a las **07:17 hora CDMX** (13:17 UTC).
GitHub puede retrasar u omitir un cron: no es una garantía horaria. El ciclo captura la lista fija,
reconstruye `data/gold/`, hace commit del snapshot y publica un ZIP consistente en el release
[`datos`](https://github.com/d1512pb/sconto-reale-o-falso/releases/tag/datos). Si una fuente falla dos días
seguidos, escribe `ALERTA.md` y abre un issue con la etiqueta `alerta-recoleccion`.
Para correrlo a mano: pestaña **Actions → Recolección diaria de precios → Run workflow**.

### Programador de tareas de Windows (PC de Daniel)

1. Abre **PowerShell** (no hace falta administrador) en la carpeta del proyecto.
2. Ejecuta una vez:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea_windows.ps1
   ```
   Crea **Sconto recoleccion diaria**, a las **12:30 y 20:30 hora local de Windows** (configurada en CDMX).
   Tiene **“Ejecutar lo antes posible si se perdió el inicio”**, disparador **al iniciar sesión**,
   ejecución oculta, límite de tres horas y una sola instancia. No guarda contraseñas.
3. Comprueba en **Programador de tareas → Biblioteca** que aparezca; clic derecho → **Ejecutar** permite probar.
   Revisa `logs/servicio_<fecha>.log`. Resultado 0 significa cobertura exigida completa; 2, faltantes; 1, error técnico.
4. La tarea usa `scripts/correr_local.ps1 -Publicar`. Sincroniza una **copia operativa independiente** en
   `data/operacion/repo_servicio/`, conserva sus crudos y no modifica ni hace rebase sobre tu checkout de trabajo.
   Requiere `git`, `gh` autenticado, el entorno `.venv` instalado y acceso a Internet.
   Captura Liverpool y revisa QQP del año actual semanalmente. El respaldo de Preciómetro/ML sólo se habilita
   desde las 20:00 CDMX y si falta el éxito del día, para dar margen a los retrasos del cron de GitHub.
   No reintenta una fuente bloqueada ese mismo día. La llamada de las 20:30 no duplica las fichas capturadas al mediodía.
   Las capturas de la PC se escriben como `*.local.parquet` y las evidencias bajo `preciometro/local/`:
   no sobrescriben archivos del colector cloud aunque ambos corran ese día.
   **Sólo GitHub publica el ZIP del release.** La PC envía sus particiones y solicita una corrida idempotente
   del workflow; así no puede reemplazar el paquete público con un snapshot local atrasado.
5. Para desactivar: `Disable-ScheduledTask -TaskName 'Sconto recoleccion diaria'`.

La PC debe estar encendida y con sesión iniciada en algún momento del día; un día sin corrida queda como faltante.
Si la PC deja de confirmar sus capturas más de dos días, el colector cloud también genera una alerta;
no depende de que la tarea averiada llegue a escribir un estado de error. El antiguo checkout `data/operacion/repo/`
se conserva intacto como evidencia del conflicto del 22 de octubre; el servicio nuevo no lo reutiliza.

## Publicación para Colab

Los notebooks no dependen de rutas locales. Descargan un **único ZIP** para evitar mezclar tablas de distintas
corridas. Descarga y conserva el ZIP con sus hashes para congelar una versión del análisis.
Los enlaces `actual` y fechado pueden actualizarse dentro del mismo día:

```python
URL = 'https://github.com/d1512pb/sconto-reale-o-falso/releases/download/datos/sconto_colab_actual.zip'
```

Los crudos se conservan fuera del repositorio público: las respuestas de tiendas y agregadores pueden contener
campos ajenos a precios. Los paquetes públicos sólo llevan tablas de precios normalizadas y hashes de trazabilidad.
`data/evidencia/preciometro/` preserva una **proyección de los campos de precios** de las respuestas, con el hash
del original, para reproducir el parser sin publicar reservas/cuentas. No se presenta como el JSON íntegro del servidor.
`python -m sconto.evidencia` genera esas proyecciones sin red; el ciclo programado también lo hace.
Las pruebas locales de carga no equivalen a haber ejecutado el notebook en los servidores de Colab.

## Criterios metodológicos

- **No se mezclan canales**: una serie es producto × vendedor/sucursal × canal; QQP (tienda física) y las fuentes en
  línea se comparan a nivel de producto canónico, con el canal como dimensión.
- **Un precio anunciado no prueba engaño.** `brecha_pp = descuento_anunciado_pct − ahorro_historico_pct`, y la
  etiqueta `regla_descuento_inflado_{5,10,15}pp` es una **etiqueta derivada por regla**, no una verdad. No se entrena
  un clasificador supervisado con ella.
- **Ventanas iguales al Avance 1**, relativas al primer día del evento (D0): base D-60..D-15, previo D-14..D-1,
  evento D0..último día, posterior 14 días (sólo diagnóstico; incluye Black Friday y Cyber Monday).
- **Mínimos de cobertura del Avance 1** (≥4 fechas base en ≥21 días, ≥1 en el evento, ≥2 en el previo), con tabla de
  sensibilidad para 2, 3, 4 y 5 fechas.
- **Reproducible**: manifiestos con URL, fecha y SHA-256; crudos guardados; scripts deterministas;
  `tests/test_dataset.py` reproduce exactamente el Avance 1 (39,363 / 298 / 93 y la matriz 93 × 3).
