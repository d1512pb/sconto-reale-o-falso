# Cobertura: Amazon México (`amazon`)

Fecha de la prueba: 2026-10-16, desde la PC local (IP residencial). Costo: **$0**.
Módulo: `src/sconto/fuentes/amazon.py` · Pruebas: `tests/test_amazon.py` (13 pruebas offline, pasan).
Todas las cifras de este reporte se calcularon con código sobre `data/bronze/amazon/`,
`data/bronze/amazon_capturas/` y `data/raw/amazon/2026-10-16/`.

## Resumen

| Concepto | Valor verificado |
|---|---|
| Estado registrado (`data/estado_fuentes.csv`) | `bloqueado` (2026-10-16, local) |
| ASINs seleccionados para la prueba | 12 (un ASIN por producto de prioridad 1, `config/productos_objetivo.csv`) |
| Peticiones a `/dp/` hechas | 3 (la corrida se detuvo tras 2 bloqueos seguidos; 9 ASINs no se pidieron) |
| Fichas válidas (HTTP 200 con `#productTitle`) | 1 de 3 (33 %) |
| Página de verificación (CAPTCHA "Haz clic en el botón de abajo para continuar comprando") | 2 de 3 (67 %), las dos con HTTP 200 |
| HTTP 503 / 403 / 429 | 0 |
| Filas en bronze (`data/bronze/amazon/2026-10-16.parquet`) | **1** (ASIN B0CLF3VPMV) |
| Productos con dato | 1 · rango de fechas 2026-10-16 a 2026-10-16 · 1 día con dato |
| Puntos por producto | mediana 1, máximo 1 |
| Filas con precio de lista o tachado (`precio_anterior_anunciado`) | 0 de 1 |
| Filas con % de ahorro mostrado (`pct_descuento_anunciado`) | 0 de 1 |
| Filas con "Vendido por" / "Enviado por" | 1 / 1 de 1 |
| Filas con MSI / plazos con costo / cupón / oferta | 0 / 1 / 0 / 0 de 1 |
| Validación del esquema (sin duplicados por CLAVE, precio > 0, fechas, pct) | sin problemas |

La única fila: Samsung Galaxy Tab A9 **Plus** 4GB 64GB, $5,650.00, vendido por un tercero y enviado por
Amazon, sin precio tachado ese día, plazos "$573.47 x12 meses" (la ficha no dice "sin intereses", así que no
cuenta como MSI).

## 1. robots.txt (descargado con `Cliente`, guardado en `data/raw/amazon/2026-10-16/robots.txt.gz`)

- Nuestro user-agent (`ScontoRealeOFalso/0.1 ...`) no aparece en ningún grupo, así que le aplica `User-agent: *`.
- **`/dp/<ASIN>` está permitida.** En `/dp/` sólo se prohíben `/dp/product-availability/`, `/dp/rate-this-item/`,
  `/dp/twister-update/` y `/dp/e-mail-friend/`. También se prohíben `/gp/offer-listing`, `/gp/cart`, `/ap/signin`,
  `/gp/aw/ol/` y otras rutas: el módulo no las usa.
- **`/s?k=` (búsqueda) está permitida** para `*`. Aun así, `buscar(texto)` sólo sirve para mapear a mano un modelo
  a sus ASIN candidatos (una página, con caché). El mapeo producto → ASIN de la lista fija viene de las ofertas de
  Preciómetro.
- En el mismo archivo, 99 agentes tienen `Disallow: /` (bloqueo total). Casi todos son agentes de IA:
  `ClaudeBot`, `Claude-User`, `Claude-Web`, `Claude-SearchBot`, `GPTBot`, `ChatGPT-User`, `Devin`, `Crawl4AI`,
  `Scrapy`, `CCBot` y otros. Nuestro agente no está en esa lista. Ver "Decisiones" abajo.
- El módulo evalúa robots con RFC 9309 (gana la regla más larga, con comodines `*` y `$`) **y además** con
  `urllib.robotparser`. Sólo pide una ruta si los dos la permiten. robots.txt se lee una vez por día, con caché.

## 2. Campos que extrae el parser (`parsear_ficha`)

Título, ASIN de la página (`input#ASIN` o `link canonical`) y precio a pagar (sólo del bloque de compra
`corePriceDisplay`/`apex`; los carruseles patrocinados se ignoran). También: precio "Precio de lista"/"Antes"/tachado
(`data-a-strike`, si es visible y está en el bloque de compra), etiqueta del tachado, % de ahorro **tal como se
muestra** ("-35%" se guarda como 35 y el texto original va a `condiciones.ahorro_texto`; no se calcula nada),
"Vendido por", "Enviado por", disponibilidad, oferta/oferta relámpago, cupón, promoción, MSI (sólo si dice
"meses sin intereses"), plazos con costo (sólo como texto), condición (nuevo, reacondicionado o usado), Prime,
mensaje de entrega, marca y modelo.

Cosas que se vieron en la ficha real y que el parser ya maneja:
- en el precio a pagar, `.a-offscreen` llega **vacío**, y en el precio de lista llega con el texto **"null"**.
  Por eso se usa la parte visible (entero + fracción, o `aria-hidden`);
- en la página hay precios tachados de **otros productos** (carrusel patrocinado: $1,999 → $1,077.70). Fuera del
  bloque de compra nunca se leen;
- la página trae texto genérico de "meses sin intereses" (ayuda de pagos) que no es una oferta del producto. No se
  toma.

Fixtures (sin datos personales): `B0CLF3VPMV.html` es la ficha real recortada a los bloques que lee el parser, sin
scripts, formularios, enlaces, `session-id`/csrf, reseñas ni la ubicación de entrega que Amazon estima por IP.
`captcha.html` es la página real de verificación, con sus tokens reemplazados por X. `robots.txt` es el real.
`sintetica_descuento.html` usa **números inventados** sobre la estructura real, para probar precio de lista, % de
ahorro, cupón, MSI y el diseño antiguo de "Vendido y enviado por".

## 3. Bloqueo

- Amazon responde la verificación con **HTTP 200**, no con 503. Se detecta por marcas propias:
  `/errors/validatecaptcha` y "To discuss automated access to Amazon data", entre otras.
- Ante la verificación, el módulo **no** pulsa "Continuar", no cambia el user-agent y no reintenta. Guarda la
  página como `<ASIN>.bloqueo.html.gz` y registra `bloqueado`. El colector diario se detiene al primer bloqueo
  (`max_bloqueos=1`). La prueba usó 2 para medir si el bloqueo persistía, y sí persistió. Una vez registrado
  `bloqueado` ese día, las siguientes ejecuciones del mismo día no hacen ninguna petición (se verificó: 0
  peticiones). El cliente usa `reintentos=0`, así que un 503/429 se convierte de inmediato en `bloqueado`.
- La pausa entre peticiones al mismo host es de 3 a 8 s, medida de inicio a inicio. Se hace una petición por ASIN
  y por día. Re-ejecutar el mismo día reutiliza el crudo guardado (idempotente, probado offline).

## 4. Dónde programarlo (recomendación)

- **No en GitHub Actions.** No se probó (no se lanzó), pero si una IP residencial recibió la verificación en la
  2.ª petición, con una IP de centro de datos lo esperable es igual o peor. `config/fuentes.yaml` ya la tiene como
  `entornos: [local]`.
- **Programador de tareas de Windows, una vez al día**, con `run_diario --entorno local --fuentes amazon` o con el
  comando diario de abajo. Con 96 ASINs únicos en la lista fija al momento de la prueba, una corrida sin bloqueo
  tomaría alrededor de 9 a 11 min (pausa media de 5.5 s más la descarga de unos 2 MB por ficha).
- Expectativa realista: con el user-agent honesto, Amazon bloquea casi de inmediato. Lo más probable es tener
  **0 a 1 ficha por día**. Para el análisis, el precio de Amazon por ASIN sale con más cobertura de
  `preciometro_ofertas` (ofertas con `plataforma = Amazon` y su ASIN) y, como historial, de Wayback/Common
  Crawl. No hay API gratuita: PA-API 5 exige una cuenta de Afiliados con ventas calificadas, y Keepa (historial de
  Amazon) es de pago.

## Verificado y pendiente

**Verificado (con datos de hoy):** robots.txt (`/dp/` y `/s?k=` permitidas para `*`), 1 ficha real analizada
correctamente, 2 páginas de verificación detectadas, el registro de `bloqueado` y el alto el mismo día, la
validación del esquema y 13 pruebas offline.

**Pendiente o no verificado:**
- El precio tachado, el % de ahorro, el cupón, el MSI y la oferta relámpago **sólo están probados con la fixture
  sintética**. En una ficha real no se pudo, porque la única ficha obtenida no mostraba descuento.
- No hay serie (1 punto). No se sabe si el bloqueo depende de la hora o de la IP en otros días: hay que observar
  `data/estado_fuentes.csv` durante una semana.
- `backfill`: **no aplica**. Amazon no publica historial de precios en la ficha.

## Decisiones para el equipo

1. **Agentes de IA en robots.txt.** Amazon bloquea por completo a `Claude-User`, `ClaudeBot`, `Devin`, `Crawl4AI`,
   `ChatGPT-User` y otros. Nuestro colector se identifica con su propio user-agent académico, al que le aplica `*`
   (permitido). Sugerencia: que la recolección diaria la lance el Programador de tareas de la PC y no una sesión
   de un agente de IA.
2. **Condiciones de Uso de Amazon.** Prohíben el uso de robots o minería de datos, aunque robots.txt permita
   `/dp/`. El equipo debe decidir si mantiene la fuente, con 1 petición por ASIN y día, sólo precios públicos y uso
   académico, o si se queda únicamente con Preciómetro y Wayback para Amazon.
3. **Lista fija.** El ASIN B0CLF3VPMV corresponde a la Galaxy Tab A9 **Plus** (11"), pero está mapeado a
   `Q1-SAMSUNG-GALAXYTABA9-3ed764` (SM-X110 de 8.7") con confianza "exacto". Además, de 116 ASINs listados sólo 96
   son únicos: hay ASINs repetidos entre productos, y el módulo usa el primer producto. Conviene revisar el mapeo.
   La fila guarda el título y el modelo de la página para poder filtrar.
4. **Segunda pasada en temporada** (`pasadas_temporada: 2` en `fuentes.yaml`). Hoy no aporta datos: la CLAVE no
   distingue hora o pasada, y `diario()` no recibe el número de pasada. La segunda corrida reutiliza el crudo de la
   primera o se detiene por el bloqueo.

## Comandos

```bash
PY="/c/Users/danie/Documents/ESCOM/Semestre 7/Mineria  de datos/Sconto/SCRIPTS/.venv/Scripts/python.exe"
# diario (lista fija completa; se detiene y registra 'bloqueado' al primer CAPTCHA/503):
"$PY" -m sconto.fuentes.amazon diario --productos config/productos_objetivo.csv
# robots del día, prueba acotada, reconstrucción sin red y fixture:
"$PY" -m sconto.fuentes.amazon robots
"$PY" -m sconto.fuentes.amazon prueba --productos config/productos_objetivo.csv --max 12
"$PY" -m sconto.fuentes.amazon reparsear --fecha 2026-10-16
"$PY" -m sconto.fuentes.amazon fixture B0CLF3VPMV --fecha 2026-10-16
```
