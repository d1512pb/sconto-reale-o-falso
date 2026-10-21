# Cobertura · Internet Archive Wayback Machine (CDX)

> Revisión del 20 oct 2026: se conservan 109 observaciones existentes, con fechas hasta
> 2025-10-17. No hay observaciones en el evento BF2024 ni BF2025 de este recorte.
> Los canónicos descritos en la corrida original no se consideran ahora confirmados:
> gold los recalcula con el matching conservador y deja vacíos los cruces ambiguos.
> Las cifras de duración/peticiones marcadas `None` no están disponibles y no son mediciones.

Fecha de la corrida: 2026-10-16 · Módulos: `src/sconto/fuentes/wayback.py`, `src/sconto/parsers_archivo.py` · Costo: **0** (API pública del Internet Archive, sin cuentas ni servicios de pago).

Todas las cifras salen de `data/bronze/wayback/*.parquet`, `data/cache/wayback/objetivos.parquet` y `data/cache/wayback/snapshots.parquet`, calculadas con `python -m sconto.fuentes.wayback cobertura`; ninguna es una estimación.

## Corrida real acotada

| Tramo | Comando | Minutos | Peticiones | Resultado |
|---|---|---|---|---|
| (a) fichas de producto | `backfill --prioridad-max 3 --sin-tiendas --limite-minutos 24` | None | None | None objetivos, None consultas CDX (None fallidas), None capturas procesadas, cortado por tiempo: no |
| (b) páginas Buen Fin | `backfill --sin-productos --max-paginas-tienda 2 --limite-minutos 11` | None | None | None tiendas, None páginas descargadas, None tarjetas con precio, cortado por tiempo: no |

Objetivos (a): todos los ASIN y MLM de `config/productos_objetivo.csv` con prioridad 1–3, en el rango completo 2024-09-01..2025-12-31 (no sólo las ventanas). Ritmo: pausa de 1.0–1.6 s por petición a web.archive.org.

## Verificado

### (a) Fichas de producto: capturas en el CDX

| Tipo | Objetivos consultados | Con ≥1 captura válida (ficha real, no CAPTCHA) |
|---|---|---|
| asin | 35 | 11 |
| mlm | 35 | 17 |

Capturas devueltas por el CDX (HTML, estado 200, `collapse=digest`): 715; días válidos (una captura por objetivo y día): 116. Consultas con 503 persistente u otro error: 0 objetivos afectados.

Objetivos con al menos una captura válida en cada ventana (ventanas de `config/eventos.yaml`, iguales al Avance 1):

| Evento | base | previo | evento |
|---|---|---|---|
| BF2024 (2024-09-16..10-31 / 11-01..11-14 / 11-15..11-18) | 6 | 9 | 0 |
| BF2025 (2025-09-14..10-29 / 10-30..11-12 / 11-13..11-17) | 6 | 0 | 0 |

### (a) Capturas descargadas y parseadas

- Capturas procesadas: 116 (descarga: {'descargado': 115, 'cache': 1}).
- Resultado del parser: {'ok': 109, 'sin_precio': 7}.
- Con precio: **109**; con precio tachado/anterior mostrado: **67**.
- `otro_id` (la captura era de otro producto, p. ej. redirección): 0.

### (a) Bronze `wayback` (fichas)

| Métrica | Valor |
|---|---|
| Filas (observaciones de precio) | 109 |
| Ids externos con dato | 28 |
| Productos canónicos con dato | 15 |
| Por plataforma | {'Mercadolibre': 88, 'Amazon': 21} |
| Rango de fechas (fecha_precio) | 2024-09-06 .. 2025-10-17 |
| Días distintos con dato | 81 |
| Puntos por id: mediana / máximo | 2.0 / 24 |
| Días con dato por id: mediana | 2.0 |
| Filas con precio anterior (tachado) mostrado | 67 |
| Filas con % de descuento mostrado | 67 |
| Filas por ventana | {'fuera_de_ventana': 67, 'BF2024:base': 23, 'BF2024:previo': 10, 'BF2025:base': 7, 'BF2024:posterior': 2} |
| Ids con dato en evento | {} |

Por producto canónico (ordenado por puntos):

| producto_canonico_id | puntos | días | desde | hasta | con tachado |
|---|---|---|---|---|---|
| Q1-AMAZON-FIRETVSTICK-976170 | 28 | 28 | 2024-09-09 | 2025-08-04 | 18 |
| Q1-ROKU-STREAMINGSTICK4K-64a55e | 18 | 18 | 2024-09-09 | 2025-07-12 | 12 |
| Q1-ALEXA-ECHOPOP-670730 | 13 | 13 | 2024-09-06 | 2025-10-07 | 5 |
| Q1-SAMSUNG-GALAXYTABA9-3ed764 | 9 | 9 | 2024-11-03 | 2025-09-07 | 8 |
| Q1-FUJIFILM-INSTAXMINI12-b1d9f2 | 9 | 9 | 2024-09-07 | 2025-10-08 | 6 |
| Q1-ALEXA-ECHOSPOT-ce61ab | 8 | 7 | 2024-09-30 | 2025-10-08 | 5 |
| Q2-LG-55UR7800PSB-801808 | 7 | 7 | 2024-12-13 | 2025-08-05 | 4 |
| Q2-ALEXA-ECHODOT-ae564c | 3 | 3 | 2024-09-06 | 2025-10-17 | 1 |
| Q1-SONY-SRSXB100-2e8589 | 3 | 3 | 2024-09-08 | 2024-11-02 | 3 |
| Q1-SAMSUNG-GALAXYA06-532823 | 3 | 3 | 2024-12-15 | 2025-06-20 | 1 |
| Q1-ALEXA-ECHOSHOW8-23b1d4 | 2 | 2 | 2024-12-09 | 2025-01-12 | 0 |
| Q1-SAMSUNG-GALAXYTABA9PLUS-1a6302 | 2 | 2 | 2025-04-05 | 2025-08-04 | 1 |
| Q1-SONY-HTS20R-faa93f | 2 | 2 | 2024-11-08 | 2025-05-30 | 1 |
| Q1-LG-55UA7500PSA-969e8f | 1 | 1 | 2025-08-14 | 2025-08-14 | 1 |
| Q1-ALEXA-ECHOSHOW5-09d542 | 1 | 1 | 2024-12-23 | 2024-12-23 | 1 |

### (b) Páginas Buen Fin de tiendas

| Tienda | Capturas buen-fin (oct 2024–nov 2025) | URLs distintas | Consulta fallida | Capturas elegidas por ventana |
|---|---|---|---|---|

Páginas descargadas: 0; con tarjetas de producto con precio: 0; tarjetas: 0 (con tachado: 0). Parser: {}.

### Validaciones del bronze (todas las particiones)

- Duplicados por CLAVE ['fuente', 'id_externo', 'fecha_precio', 'vendedor_o_cadena']: 0.
- Precio ≤ 0: 0; % fuera de [−100, 100]: 0.
- `metodo` = ['wayback'], `canal` = ['en_linea'], `moneda` = ['MXN'], `tipo_id_externo` = ['asin', 'mlm'].
- Total de filas en bronze: 109.

## Qué falló y por qué

- **Amazon: casi todo lo archivado es la página de CAPTCHA.** De 422 capturas CDX con URL de ficha (`/dp/<ASIN>`, `/dp/<ASIN>/ref=…`, `?tag=…`), 390 pesan menos de 15 KB comprimidas. La muestra descargada (B0C29CL98P, 2024-11-02, 2.3 KB) es la página `opfcaptcha` que Amazon le sirvió al rastreador del Internet Archive. Esas capturas se descartan sin descargarlas. Las fichas reales pesan más de 100 KB. Otras 10 capturas traen `length` negativo (dato corrupto del CDX): se conservan como tamaño desconocido y el parser decide.
- **La mayoría de los objetivos no tiene capturas.** El Internet Archive guarda lo que alguien (o un enlace de afiliado: `tag=…-20`) le pidió archivar; no rastrea todas las fichas de forma sistemática. Hay objetivos con 0 capturas en todo el rango 2024-09-01..2025-12-31.
- **Mercado Libre: la URL lleva un slug que no conocemos.** Se buscó `mercadolibre.com.mx/p/<MLM>` y además el prefijo de las 3 primeras palabras del nombre de catálogo (tomado de las ofertas de Preciómetro), filtrando el urlkey por el MLM. 65 de 65 MLM objetivo tenían nombre; se hicieron 36 consultas por slug. Si el nombre de Preciómetro no coincide con el slug de ML, la captura no se encuentra.
- **Mercado Libre: fichas sin stock.** Algunas capturas muestran "Este producto no está disponible": no hay precio y no se emite fila (estado `sin_stock`/`sin_precio` en `snapshots.parquet`).
- **Tiendas: las páginas Buen Fin se arman en el navegador.** Varias portadas archivadas (p. ej. Sanborns `/c/buen-fin/`) traen texto y banners, pero los productos se cargan después con JavaScript desde una API que el archivo no guardó. En esos casos no hay tarjetas que leer.
- **503 del CDX.** En el intento anterior el CDX respondió 503 varias veces seguidas (esperas de 15, 30 y 60 s). `Cliente` reintenta con espera exponencial; tras 4 bloqueos seguidos la corrida se corta y queda `parcial`/`bloqueado`. La consulta fallida no se guarda en caché, así que se reintenta en la siguiente corrida.

## Límites (leer antes de analizar)

- Wayback no es una serie diaria: da puntos dispersos en días que dependen de terceros. Por eso `dias_con_dato` es bajo y no se imputa nada.
- En Amazon, `precio_anterior_anunciado` es el precio tachado que mostraba la ficha. Su etiqueta va en `condiciones.etiqueta_anterior` ("Precio de lista" y, a veces, "Precio más bajo reciente"). `pct_descuento_anunciado` es el porcentaje que pintaba Amazon ("-31%" → 31), no un cálculo nuestro.
- En Mercado Libre, la ficha de catálogo muestra al ganador del buy box de ese día: `vendedor_o_cadena` cambia entre capturas. `precio_anterior_anunciado` = `original_value` y `pct` = `discount_label` del estado preinyectado. El ítem ganador queda en `condiciones.item_ganador`.
- Amazon: sólo se consulta el prefijo `amazon.com.mx/dp/<ASIN>`. Las URLs con slug (`/<slug>/dp/<ASIN>`) no se pueden buscar sin conocer el slug.
- Las tarjetas de tiendas (`objetivo='tienda'`, `tipo_precio='tarjeta_listado'`) no están emparejadas con `producto_canonico_id`; eso le toca a `emparejar`.
- `fecha_precio` es la fecha UTC del timestamp de la captura.
- Los HTML crudos (`data/raw/wayback/`, fuera de git) pueden contener reseñas públicas archivadas. El parser no extrae reseñas ni nombres de usuarios: sólo precio, vendedor comercial, disponibilidad y condiciones.

## Pendiente

- La corrida completa, que agrega prioridad 4, los ASIN y MLM de todas las ofertas de Preciómetro y más páginas por tienda (comando abajo).
- Volver a correr en diciembre de 2026 (captura `diario`) para tener puntos archivados del BF2026.

## Comandos (reanudables e idempotentes)

Las consultas CDX quedan en caché en `data/cache/wayback/cdx/`. Los HTML se guardan en `data/raw/wayback/<fecha snapshot>/<timestamp>_<hash>.html.gz`, una ruta que no depende del día de la corrida. El bronze no repite CLAVE entre particiones. Re-ejecutar sólo descarga lo nuevo; las consultas fallidas se reintentan.

```
PY="/c/Users/danie/Documents/ESCOM/Semestre 7/Mineria  de datos/Sconto/SCRIPTS/.venv/Scripts/python.exe"
# completa: todas las prioridades + ofertas de Preciómetro + 6 páginas por tienda
"$PY" -m sconto.fuentes.wayback backfill --prioridad-max 4 --desde-ofertas --max-paginas-tienda 6
# diaria/semanal: capturas de los últimos 10 días de las fichas objetivo
"$PY" -m sconto.fuentes.wayback diario --dias 10
# cifras de este reporte
"$PY" -m sconto.fuentes.wayback cobertura
```
