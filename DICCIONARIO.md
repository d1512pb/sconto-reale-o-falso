# Diccionario de datos (`data/gold/`)

Tipos y rangos calculados sobre los datos actuales al generar este archivo (`python -m sconto.diccionario`). Los rangos describen lo observado, no límites teóricos.


## observaciones

Una fila por precio observado (formato largo). Todas las fuentes salvo QQP nacional. Clave única: (fuente, id_externo, fecha_precio, vendedor_o_cadena).

Filas: 672,678

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `obs_id` | Identificador estable de la observación (hash). | str | 672,678 valores distintos | todas |
| `fuente` | Origen: qqp_cdmx, preciometro, preciometro_ofertas, mercadolibre, amazon, wayback, commoncrawl, promodescuentos. | str | amazon, preciometro, preciometro_ofertas, qqp_cdmx, tiendas, wayback | todas |
| `metodo` | archivo_oficial \| api \| scraping \| wayback \| commoncrawl \| agregador \| comunidad. | str | agregador, archivo_oficial, scraping, wayback | todas |
| `canal` | tienda_fisica (QQP) \| en_linea. Nunca se mezclan en una serie. | str | en_linea, tienda_fisica | todas |
| `tipo_precio` | minimo_diario_multitienda (gráfico de Preciómetro: el más bajo entre tiendas ese día), oferta_vigente, precio_vigente, observado_sucursal, etc. | str | minimo_diario_multitienda, oferta_vigente, precio_registrado_qqp, publicado | todas |
| `fecha_precio` | Día al que corresponde el precio (en Wayback/Common Crawl, fecha del snapshot). | str | 2,178 valores distintos | todas |
| `fecha_captura` | Día en que se descargó. | str | 2026-10-16, 2026-10-20, 2026-10-21, 2026-10-22, 2026-10-23, 2026-10-24, 2026-10-25, 2026-10-26 … (9 distintos) | todas |
| `producto_canonico_id` | Producto canónico de config/productos_objetivo.csv; vacío si no se emparejó. | str | 1,724 valores distintos | derivado |
| `id_externo` | Id en la fuente: producto_id QQP, id de ficha u oferta Preciómetro, ASIN, MLM. | str | 13,032 valores distintos | todas |
| `tipo_id_externo` | qqp \| preciometro \| preciometro_oferta \| asin \| mlm \| mlm_item \| url. | str | asin, mlm, preciometro, preciometro_oferta, qqp, url | todas |
| `marca` | Marca según la fuente. | str | 413 valores distintos | todas |
| `modelo_normalizado` | Código o nombre de modelo en mayúsculas sin espacios ni guiones. | str | 980 valores distintos | derivado |
| `descripcion_original` | Texto original del producto en la fuente. | str | 12,244 valores distintos | todas |
| `plataforma` | Tienda o marketplace (Amazon, Mercadolibre, Elektra, …) en fuentes en línea. | str | Amazon, Bodega Aurrera, Chedraui, Costco, Cyberpuerta, El Palacio De Hierro, El Palacio de Hierro, Elektra … (21 distintos) | en línea |
| `vendedor_o_cadena` | Vendedor (en línea) o cadena + sucursal (QQP). | str | 2,593 valores distintos | todas |
| `sucursal_id` | Sucursal QQP (hash de cadena, nombre, dirección y alcaldía, igual que el Avance 1). | str | 185 valores distintos | QQP |
| `estado` | Entidad federativa (QQP). | str | CIUDAD DE MÉXICO, Ciudad de Mexico, Ciudad de México | QQP |
| `alcaldia` | Municipio/alcaldía (QQP). | str | AZCAPOTZALCO, Azcapotzalco, BENITO JUÁREZ, Benito Juárez, COYOACÁN, CUAUHTÉMOC, Coyoacán, Cuauhtémoc … (24 distintos) | QQP |
| `precio` | Precio observado de contado, MXN. Mayor que 0. | float64 | 29.00 – 989,999.00 | todas |
| `precio_anterior_anunciado` | Precio tachado / “Antes” / “Precio de lista” SÓLO si la fuente lo muestra. | float64 | 594.00 – 14,499.00 | en línea |
| `pct_descuento_anunciado` | % de descuento SÓLO si la fuente lo muestra; entre −100 y 100. | float64 | 2.00 – 47.00 | en línea |
| `moneda` | MXN. | str | MXN | todas |
| `disponibilidad` | Disponible, agotado, etc., según la fuente. | str | Disponible, Disponible 1 día después de tu compra, Disponible 5 días después de tu compra, Disponible 7 días después de tu compra, Disponible {"isInternal":false,"isRobot":false,"showFaceout":true,"merchantId":"A1AYA2LE3BV7SY","availableBadges":"","loggedIn":false,"asin":"B0CPL6NDWH","showBadge":false,"availableFaceouts":"TK_BOUGHT"}, Disponible {"isInternal":false,"isRobot":false,"showFaceout":true,"merchantId":"AVDBXBAVVSXLQ","availableBadges":"","loggedIn":false,"asin":"B09WNK39JN","showBadge":false,"availableFaceouts":"TK_BOUGHT"}, Disponible {"isInternal":false,"isRobot":false,"showFaceout":true,"merchantId":"AVDBXBAVVSXLQ","availableBadges":"","loggedIn":false,"asin":"B0CPL6NDWH","showBadge":false,"availableFaceouts":"TK_BOUGHT"}, Disponible {"isInternal":false,"showInsightsHub":false,"isRobot":false,"showFaceout":true,"merchantId":"A10YF1TK1RC4IY","availableBadges":"","loggedIn":false,"asin":"B0CPL6NDWH","showBadge":false,"ingressFaceout":"","availableFaceouts":"TK_BOUGHT"} … (16 distintos) | en línea |
| `condiciones` | JSON: MSI, cupón, envío, membresía (Prime), vendido/enviado por, marketplace. | str | 6,835 valores distintos | en línea |
| `url` | URL del producto/oferta/archivo oficial. | str | 12,057 valores distintos | todas |
| `ruta_raw` | Ruta del crudo (relativa a la raíz del repo; los voluminosos viven en la PC local). | str | 413,436 valores distintos | todas |
| `hash_raw` | SHA-256 del crudo sin comprimir. | str | 4,307 valores distintos | todas |
| `serie_id` | Serie = plataforma × id externo × vendedor/sucursal × canal (QQP: el serie_id del Avance 1). | str | 39,329 valores distintos | derivado |
| `preciometro_producto_id` |  | str | 2,780 valores distintos |  |
| `asin` |  | str | 2,406 valores distintos |  |
| `mlm_producto` |  | str | 1,116 valores distintos |  |
| `mlm_item` |  | object | vacío |  |
| `n_capturas` | Cuántas capturas trajeron esa misma clave (el historial de 90 días se repite cada día). | int64 | 1.00 – 9.00 | derivado |
| `precio_revisado_por_fuente` | True si capturas distintas dieron precios distintos para la misma clave. | bool | True 148 / False 672,530 | derivado |
| `plataforma_serie` | Plataforma con la que se agrupa la serie (Wayback de Amazon se agrupa con amazon). | str | amazon, liverpool, mercadolibre, preciometro, preciometro_ofertas, qqp_cdmx | derivado |
| `vendedor_serie` | Vendedor de la serie (MINIMO_MULTITIENDA para el gráfico de Preciómetro; sucursal en QQP). | str | 1,536 valores distintos | derivado |
| `revisar_captura` | True si el precio está fuera de 1.5×IQR de su serie: posible error, NO se borra. | bool | True 46,171 / False 626,507 | derivado |

## series_evento

Una fila por serie × evento (BF2024, BF2025, BF2026). Medianas sobre fechas observadas, sin imputar.

Filas: 18,388

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `serie_evento_id` | Hash de serie_id + evento_id. | str | 18,388 valores distintos | derivado |
| `serie_id` |  | str | 17,341 valores distintos |  |
| `evento_id` | BF2024 \| BF2025 \| BF2026. | str | BF2024, BF2025, BF2026 | config/eventos.yaml |
| `fuente` |  | str | amazon, preciometro, preciometro_ofertas, qqp_cdmx, tiendas, wayback |  |
| `plataforma_serie` |  | str | amazon, liverpool, mercadolibre, preciometro, preciometro_ofertas, qqp_cdmx |  |
| `metodo` |  | str | agregador, archivo_oficial, scraping, wayback |  |
| `canal` |  | str | en_linea, tienda_fisica |  |
| `tipo_precio` |  | str | minimo_diario_multitienda, oferta_vigente, precio_registrado_qqp, publicado |  |
| `producto_canonico_id` |  | str | 1,716 valores distintos |  |
| `id_externo` |  | str | 12,244 valores distintos |  |
| `tipo_id_externo` |  | str | asin, mlm, preciometro, preciometro_oferta, qqp, url |  |
| `vendedor_serie` |  | str | 1,419 valores distintos |  |
| `marca` |  | str | 367 valores distintos |  |
| `modelo_normalizado` |  | str | 237 valores distintos |  |
| `descripcion_original` |  | str | 11,200 valores distintos |  |
| `estado` |  | str | Ciudad de Mexico |  |
| `alcaldia` |  | str | Azcapotzalco, Benito Juárez, Coyoacán, Cuauhtémoc, Gustavo a. Madero, Iztacalco, Iztapalapa, Miguel Hidalgo … (12 distintos) |  |
| `metodos` |  | str | agregador, archivo_oficial, scraping, wayback |  |
| `n_base` | Fechas distintas con precio en la base (D-60..D-15). | int64 | 0.00 – 44.00 | derivado |
| `mediana_base` | Mediana de precios de la base, MXN. | float64 | 35.00 – 629,999.00 | derivado |
| `minimo_base` |  | float64 | 31.00 – 629,999.00 |  |
| `inicio_base` |  | datetime64[us] | 2024-09-17 – 2026-10-27 |  |
| `fin_base` |  | datetime64[us] | 2024-09-17 – 2026-10-27 |  |
| `n_previo` | Fechas en el previo (D-14..D-1). | int64 | 0.00 – 3.00 | derivado |
| `mediana_previo` |  | float64 | 490.00 – 50,799.00 |  |
| `minimo_previo` |  | float64 | 390.00 – 50,799.00 |  |
| `inicio_previo` |  | datetime64[us] | 2024-11-01 – 2025-11-12 |  |
| `fin_previo` |  | datetime64[us] | 2024-11-01 – 2025-11-12 |  |
| `n_evento` | Fechas durante el evento. | int64 | 0.00 – 5.00 | derivado |
| `mediana_evento` |  | float64 | 440.00 – 55,553.00 |  |
| `minimo_evento` |  | float64 | 390.00 – 55,553.00 |  |
| `inicio_evento` |  | datetime64[us] | 2024-11-15 – 2025-11-17 |  |
| `fin_evento` |  | datetime64[us] | 2024-11-15 – 2025-11-17 |  |
| `n_posterior` | Fechas en los 14 días posteriores (diagnóstico). | int64 | 0.00 – 2.00 | derivado |
| `mediana_posterior` |  | float64 | 459.00 – 66,664.00 |  |
| `minimo_posterior` |  | float64 | 445.00 – 66,664.00 |  |
| `inicio_posterior` |  | datetime64[us] | 2024-11-19 – 2025-12-01 |  |
| `fin_posterior` |  | datetime64[us] | 2024-11-19 – 2025-12-01 |  |
| `amplitud_base_dias` | Días entre la primera y la última fecha base. | float64 | 0.00 – 43.00 | derivado |
| `cobertura_ahorro` | ≥4 fechas base en ≥21 días y ≥1 en el evento (Avance 1). | bool | True 842 / False 17,546 | derivado |
| `vendedor_confirmado` | Vendedor o sucursal presente; si falta, no se calcula ahorro de una supuesta tienda fija. | bool | True 18,386 / False 2 | derivado |
| `cobertura_alza` | cobertura_ahorro y ≥2 fechas en el previo. | bool | True 298 / False 18,090 | derivado |
| `ahorro_historico_pct` | 100 × (1 − mediana evento / mediana base). Sólo con cobertura_ahorro. | float64 | -84.59 – 63.18 | derivado |
| `alza_previa_pct` | 100 × (mediana previa / mediana base − 1). Sólo con cobertura_alza. | float64 | -50.24 – 74.62 | derivado |
| `bajada_desde_previo_pct` | 100 × (1 − mediana evento / mediana previa). Sólo con cobertura_alza. | float64 | -57.90 – 45.12 | derivado |
| `variabilidad_base_pct` | 100 × (P75 − P25) / mediana base. | float64 | 0.00 – 62.32 | derivado |
| `n_anuncio_evento` | Observaciones del evento con % o precio tachado mostrado. | int64 | 0.00 – 0.00 | derivado |
| `descuento_anunciado_pct` | Mediana en el evento del % mostrado o, si sólo hay tachado, 100 × (1 − precio/tachado). | float64 | vacío | derivado |
| `brecha_pp` | descuento_anunciado_pct − ahorro_historico_pct (puntos porcentuales). | float64 | vacío | derivado |
| `regla_descuento_inflado_5pp` | Etiqueta DERIVADA por regla: brecha_pp > 5. No es verdad verificada. | object | vacío | derivado |
| `regla_descuento_inflado_10pp` | Etiqueta derivada: brecha_pp > 10. | object | vacío | derivado |
| `regla_descuento_inflado_15pp` | Etiqueta derivada: brecha_pp > 15. | object | vacío | derivado |

## productos

Catálogo canónico (config/productos_objetivo.csv): prioridad 1 = modelos de las 93 series, 2 = de las 298, 3 = resto QQP, 4 = fichas de Preciómetro sin equivalente QQP. confianza_match: exacto | probable (revisión manual) | descartado | sin_candidato.

Filas: 1,724

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `producto_canonico_id` |  | str | 1,724 valores distintos |  |
| `origen` |  | str | preciometro, qqp |  |
| `marca` |  | str | 114 valores distintos |  |
| `modelo_normalizado` |  | str | 1,709 valores distintos |  |
| `codigos_alternos` |  | str | 64 valores distintos |  |
| `descripcion_qqp` |  | str | 232 valores distintos |  |
| `categoria` |  | str | 45 valores distintos |  |
| `familia` |  | str | asistente, audio, camara, celular, laptop, pantalla, streaming, tablet |  |
| `prioridad` |  | int64 | 1.00 – 4.00 |  |
| `qqp_producto_id` |  | str | 232 valores distintos |  |
| `observaciones_qqp_2025` |  | str | 161 valores distintos |  |
| `series_qqp_2025` |  | str | 55 valores distintos |  |
| `almacenamiento_gb` |  | str | , 1024.0, 128.0, 16.0, 256.0, 32.0, 512.0, 64.0 |  |
| `ram_gb` |  | str | , 1.0, 16.0, 2.0, 3.0, 4.0, 6.0, 8.0 |  |
| `preciometro_ids` |  | str | 1,494 valores distintos |  |
| `preciometro_url` |  | str | 1,494 valores distintos |  |
| `mlm_ids` |  | str |  |  |
| `asins` |  | str |  |  |
| `confianza_match` |  | str | descartado, probable, sin_candidato |  |
| `notas` |  | str | ASIN/MLM tomados de las ofertas que agrupa Preciómetro. , ASIN/MLM tomados de las ofertas que agrupa Preciómetro. Id externo compartido entre identidades incompatibles o sin confirmar. , Ficha de Preciómetro sin equivalente QQP confirmado; variante e ids externos pendientes., Ficha de Preciómetro sin equivalente QQP confirmado; variante e ids externos pendientes.Id externo compartido entre identidades incompatibles o sin confirmar. , QQP agrupa colores; cada ficha externa conserva su id. ASIN/MLM tomados de las ofertas que agrupa Preciómetro. , QQP agrupa colores; cada ficha externa conserva su id. Sin ficha externa emparejada todavía., Sin ficha externa emparejada todavía. |  |
| `descripcion_externa` |  | str | 1,490 valores distintos |  |
| `preciometro_ids_candidatos` |  | str | 1,511 valores distintos |  |
| `asins_candidatos` |  | str | 933 valores distintos |  |
| `mlm_ids_candidatos` |  | str | 601 valores distintos |  |

## eventos

Eventos con D0 y ventanas base, previo, evento y posterior.

Filas: 3

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `evento_id` |  | str | BF2024, BF2025, BF2026 |  |
| `nombre` |  | str | Buen Fin 2024, Buen Fin 2025, Buen Fin 2026 |  |
| `d0` |  | datetime64[ms] | 2024-11-15 – 2026-11-13 |  |
| `fin` |  | datetime64[ms] | 2024-11-18 – 2026-11-17 |  |
| `base_inicio` |  | datetime64[us] | 2024-09-16 – 2026-09-14 |  |
| `base_fin` |  | datetime64[us] | 2024-10-31 – 2026-10-29 |  |
| `previo_inicio` |  | datetime64[us] | 2024-11-01 – 2026-10-30 |  |
| `previo_fin` |  | datetime64[us] | 2024-11-14 – 2026-11-12 |  |
| `evento_inicio` |  | datetime64[ms] | 2024-11-15 – 2026-11-13 |  |
| `evento_fin` |  | datetime64[ms] | 2024-11-18 – 2026-11-17 |  |
| `posterior_inicio` |  | datetime64[us] | 2024-11-19 – 2026-11-18 |  |
| `posterior_fin` |  | datetime64[us] | 2024-12-02 – 2026-12-01 |  |
| `fuente_fechas` |  | str | Avance 1 (QQP 2025), SAT, Sorteo El Buen Fin 2026 (verificado 2026-10-21); https://www.sat.gob.mx/minisitio/SorteoElBuenFin/tarjetahabientes.html, Secretaría de Economía (anuncio oficial) |  |

## sensibilidad

Series con cobertura de ahorro/alza y con brecha, exigiendo 2, 3, 4 o 5 fechas base.

Filas: 36

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `evento_id` |  | str | BF2024, BF2025, BF2026 |  |
| `plataforma_serie` |  | str | amazon, liverpool, mercadolibre, preciometro, preciometro_ofertas, qqp_cdmx |  |
| `min_fechas_base` |  | int64 | 2.00 – 5.00 |  |
| `series_cobertura_ahorro` |  | int64 | 0.00 – 755.00 |  |
| `series_cobertura_alza` |  | int64 | 0.00 – 240.00 |  |
| `series_con_brecha` |  | int64 | 0.00 – 0.00 |  |

## matriz_modelo

Entrada a Isolation Forest: ahorro_historico_pct, alza_previa_pct, variabilidad_base_pct de las series con cobertura_alza. Índice serie_evento_id (no es variable).

Filas: 298

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `serie_evento_id` |  | str | 298 valores distintos |  |
| `ahorro_historico_pct` |  | float64 | -62.52 – 52.12 |  |
| `alza_previa_pct` |  | float64 | -50.24 – 74.62 |  |
| `variabilidad_base_pct` |  | float64 | 0.00 – 57.55 |  |

## matriz_modelo_brecha

Como matriz_modelo más brecha_pp, sólo donde hay anuncio.

Filas: 0

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `serie_evento_id` |  | str | vacío |  |
| `ahorro_historico_pct` |  | float64 | vacío |  |
| `alza_previa_pct` |  | float64 | vacío |  |
| `variabilidad_base_pct` |  | float64 | vacío |  |
| `brecha_pp` |  | float64 | vacío |  |

## metadatos_modelo

Descripciones, vendedores, fechas y conteos de las filas de matriz_modelo.

Filas: 298

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `serie_evento_id` |  | str | 298 valores distintos |  |
| `serie_id` |  | str | 284 valores distintos |  |
| `evento_id` |  | str | BF2024, BF2025 |  |
| `fuente` |  | str | qqp_cdmx |  |
| `plataforma_serie` |  | str | qqp_cdmx |  |
| `metodo` |  | str | archivo_oficial |  |
| `canal` |  | str | tienda_fisica |  |
| `tipo_precio` |  | str | precio_registrado_qqp |  |
| `producto_canonico_id` |  | str | 114 valores distintos |  |
| `id_externo` |  | str | 114 valores distintos |  |
| `tipo_id_externo` |  | str | qqp |  |
| `vendedor_serie` |  | str | 2141f523b7dc6a529f6d, 26f22493b4e1edbde1e2, 2d8280258fb3705ef758, 35ff02203bc48e34ffaf, 362461c5dfac13b190cd, 4390c937ed27b9033fc6, 4b7c1fbfdb95915db919, 4ed89168c676b107e62a … (26 distintos) |  |
| `marca` |  | str | Alexa, Amazon, Canon, Fujifilm. Fine Pix, Ghia, Go Pro, Google, Hisense … (21 distintos) |  |
| `modelo_normalizado` |  | str | 112 valores distintos |  |
| `descripcion_original` |  | str | 114 valores distintos |  |
| `estado` |  | str | Ciudad de Mexico |  |
| `alcaldia` |  | str | Azcapotzalco, Benito Juárez, Coyoacán, Cuauhtémoc, Gustavo a. Madero, Iztapalapa, Miguel Hidalgo, Tlalpan … (9 distintos) |  |
| `metodos` |  | str | archivo_oficial |  |
| `n_base` |  | int64 | 4.00 – 7.00 |  |
| `mediana_base` |  | float64 | 895.00 – 39,999.00 |  |
| `minimo_base` |  | float64 | 695.00 – 39,999.00 |  |
| `inicio_base` |  | datetime64[us] | 2024-09-17 – 2025-10-07 |  |
| `fin_base` |  | datetime64[us] | 2024-10-11 – 2025-10-29 |  |
| `n_previo` |  | int64 | 2.00 – 3.00 |  |
| `mediana_previo` |  | float64 | 592.50 – 39,999.00 |  |
| `minimo_previo` |  | float64 | 390.00 – 39,999.00 |  |
| `inicio_previo` |  | datetime64[us] | 2024-11-01 – 2025-11-05 |  |
| `fin_previo` |  | datetime64[us] | 2024-11-08 – 2025-11-12 |  |
| `n_evento` |  | int64 | 1.00 – 5.00 |  |
| `mediana_evento` |  | float64 | 570.00 – 39,999.00 |  |
| `minimo_evento` |  | float64 | 390.00 – 39,999.00 |  |
| `inicio_evento` |  | datetime64[us] | 2024-11-15 – 2025-11-17 |  |
| `fin_evento` |  | datetime64[us] | 2024-11-15 – 2025-11-17 |  |
| `n_posterior` |  | int64 | 0.00 – 2.00 |  |
| `mediana_posterior` |  | float64 | 599.00 – 39,999.00 |  |
| `minimo_posterior` |  | float64 | 445.00 – 39,999.00 |  |
| `inicio_posterior` |  | datetime64[us] | 2024-11-19 – 2025-11-25 |  |
| `fin_posterior` |  | datetime64[us] | 2024-11-19 – 2025-11-27 |  |
| `amplitud_base_dias` |  | float64 | 21.00 – 42.00 |  |
| `cobertura_ahorro` |  | bool | True 298 / False 0 |  |
| `vendedor_confirmado` |  | bool | True 298 / False 0 |  |
| `cobertura_alza` |  | bool | True 298 / False 0 |  |
| `bajada_desde_previo_pct` |  | float64 | -57.90 – 45.12 |  |
| `n_anuncio_evento` |  | int64 | 0.00 – 0.00 |  |
| `descuento_anunciado_pct` |  | float64 | vacío |  |
| `regla_descuento_inflado_5pp` |  | object | vacío |  |
| `regla_descuento_inflado_10pp` |  | object | vacío |  |
| `regla_descuento_inflado_15pp` |  | object | vacío |  |

## exclusiones

Filas bronze que no pasaron validación, con motivo_exclusion.

Filas: 0

| Campo | Descripción | Tipo | Rango observado | Fuente |
|---|---|---|---|---|
| `obs_id` |  | str | vacío |  |
| `fuente` |  | str | vacío |  |
| `metodo` |  | str | vacío |  |
| `canal` |  | str | vacío |  |
| `tipo_precio` |  | str | vacío |  |
| `fecha_precio` |  | datetime64[us] | vacío |  |
| `fecha_captura` |  | datetime64[us] | vacío |  |
| `producto_canonico_id` |  | object | vacío |  |
| `id_externo` |  | str | vacío |  |
| `tipo_id_externo` |  | str | vacío |  |
| `marca` |  | object | vacío |  |
| `modelo_normalizado` |  | object | vacío |  |
| `descripcion_original` |  | str | vacío |  |
| `plataforma` |  | object | vacío |  |
| `vendedor_o_cadena` |  | object | vacío |  |
| `sucursal_id` |  | object | vacío |  |
| `estado` |  | object | vacío |  |
| `alcaldia` |  | object | vacío |  |
| `precio` |  | float64 | vacío |  |
| `precio_anterior_anunciado` |  | float64 | vacío |  |
| `pct_descuento_anunciado` |  | float64 | vacío |  |
| `moneda` |  | str | vacío |  |
| `disponibilidad` |  | object | vacío |  |
| `condiciones` |  | object | vacío |  |
| `url` |  | str | vacío |  |
| `ruta_raw` |  | str | vacío |  |
| `hash_raw` |  | str | vacío |  |
| `serie_id` |  | str | vacío |  |
| `preciometro_producto_id` |  | str | vacío |  |
| `asin` |  | str | vacío |  |
| `mlm_producto` |  | str | vacío |  |
| `mlm_item` |  | object | vacío |  |
| `motivo_exclusion` |  | str | vacío |  |
