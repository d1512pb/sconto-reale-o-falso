# Sconto reale o falso · recolección multifuente de precios

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
   Crea **Sconto recoleccion diaria**, a las **12:30 hora local de Windows** (configurada en CDMX).
   Tiene **“Ejecutar lo antes posible si se perdió el inicio”**, disparador **al iniciar sesión**,
   ejecución oculta, límite de tres horas y una sola instancia. No guarda contraseñas.
3. Comprueba en **Programador de tareas → Biblioteca** que aparezca; clic derecho → **Ejecutar** permite probar.
   Revisa `logs/servicio_<fecha>.log`. Resultado 0 significa cobertura exigida completa; 2, faltantes; 1, error técnico.
4. La tarea usa `scripts/correr_local.ps1 -Publicar`. Sincroniza una **copia operativa independiente** en
   `data/operacion/`, conserva sus crudos y no modifica ni hace rebase sobre tu checkout de trabajo.
   Requiere `git`, `gh` autenticado, el entorno `.venv` instalado y acceso a Internet.
   Captura Liverpool, revisa QQP del año actual semanalmente y respalda Preciómetro/ML sólo si falta el éxito del día
   y no hay una corrida cloud activa. No reintenta una fuente bloqueada ese mismo día.
5. Para desactivar: `Disable-ScheduledTask -TaskName 'Sconto recoleccion diaria'`.

La PC debe estar encendida y con sesión iniciada en algún momento del día; un día sin corrida queda como faltante.

## Publicación para Colab

Los notebooks no dependen de rutas locales. Descargan un **único ZIP** para evitar mezclar tablas de distintas
corridas. Conserva el ZIP fechado para congelar una versión del análisis; el enlace `actual` cambia cada día:

```python
URL = 'https://github.com/d1512pb/sconto-reale-o-falso/releases/download/datos/sconto_colab_actual.zip'
```

Los crudos se conservan fuera del repositorio público: las respuestas de tiendas y agregadores pueden contener
campos ajenos a precios. Los paquetes públicos sólo llevan tablas de precios normalizadas y hashes de trazabilidad.
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
