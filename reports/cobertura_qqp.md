# Cobertura de PROFECO «Quién es Quién en los Precios» (QQP)

Generado 2026-10-21T01:12:45+00:00 con `python -m sconto.fuentes.qqp reporte`. Todas las cifras se calculan con código desde `data/bronze/qqp_*` (no son estimaciones). Costo: **0** (archivos oficiales gratuitos, sin cuenta).

- Fuente: archivos anuales oficiales (RAR con CSV quincenales/semanales) de [datos.profeco.gob.mx](https://datos.profeco.gob.mx/datos_abiertos/qqp.php); diccionario: https://datos.profeco.gob.mx/diccionarioDatosQQP.php.
- Método `archivo_oficial`, canal `tienda_fisica`, `tipo_id_externo='qqp'`, `id_externo` = `producto_id` del Avance 1 (producto+marca+presentación normalizados).
- `vendedor_o_cadena` = `CADENA | NOMBRE COMERCIAL | sucursal_id` (normalizados). Cadena + nombre comercial no basta: hay sucursales homónimas con otra dirección o alcaldía; con `sucursal_id` la CLAVE (fuente, id_externo, fecha_precio, vendedor_o_cadena) equivale a (serie_id, fecha) y es única.
- Recortes: `qqp_cdmx` (CIUDAD DE MEXICO / DISTRITO FEDERAL / CDMX + APARATOS ELECTRONICOS) y `qqp_nacional` (todas las entidades, misma categoría). Son tablas separadas; el nacional incluye a CDMX y no se mezcla con el análisis principal.
- Depuración idéntica al Avance 1: inválidos (identidad incompleta, precio no numérico o ≤ 0, fecha que no parsea o cuyo año no es el del archivo) → repeticiones (misma serie, fecha y precio) → conflictos (misma serie y fecha con precios distintos; no se elige ninguno) → limpias. Toda fila cruda termina en limpias o en `*_exclusiones` (columna `motivo_exclusion`). No se imputa ni se rellena nada.

## Reproducción exacta del Avance 1 (QQP 2025, CDMX)

RAR leído: `../datos_originales/QQP_2025.rar` (sólo lectura, SHA-256 verificado `41ca4cd962e696f9f19cca598566d11ce60b200e37b5a5ef46c3b6a1ae58dc59`; no se copió ni se volvió a descargar).

| cifra | esperado | obtenido | ¿igual? |
|---|---:|---:|:---:|
| originales | 39,989 | 39,989 | sí |
| invalidos | 0 | 0 | sí |
| repeticiones | 440 | 440 | sí |
| filas_en_conflicto | 186 | 186 | sí |
| serie_fechas_en_conflicto | 93 | 93 | sí |
| limpios | 39,363 | 39,363 | sí |
| referencias | 231 | 231 | sí |
| sucursales | 80 | 80 | sí |
| series | 4,551 | 4,551 | sí |
| series_cobertura_ahorro | 298 | 298 | sí |
| series_cobertura_alza | 93 | 93 | sí |

Comparación contra los archivos del Avance 1 (`../resultados_anuales_2025/`):

- `06_mismos_serie_id`: sí
- `06_columnas_numericas_iguales`: sí
- `06_coberturas_iguales`: sí
- `06_fechas_iguales`: sí
- `06_texto_igual`: sí
- `07_mismos_serie_id`: sí
- `07_valores_iguales`: sí
- `05_mismas_filas`: sí

**Resultado: reproducción exacta.**

## Archivos obtenidos

| año | archivo | bytes | SHA-256 (12) | CSV | cabecera | filas leídas (todas las categorías) | enlace descubierto en |
|---|---|---:|---|---:|:---:|---:|---|
| 2018 | QQP_2018.rar | 117,214,326 | `3c7ceaf192da` | 53 | no | 16,782,901 | Wayback → servidor oficial |
| 2019 | QQP_2019.rar | 95,579,130 | `fa7fef1ba19b` | 53 | no | 13,682,091 | Wayback → servidor oficial |
| 2020 | QQP_2020.rar | 75,025,808 | `6328faba0fb5` | 53 | no | 10,780,481 | Wayback → servidor oficial |
| 2021 | QQP_2021.rar | 89,568,402 | `30d9f80b776f` | 52 | no | 12,813,994 | Wayback → servidor oficial |
| 2022 | QQP_2022.rar | 100,514,126 | `366264d85e9f` | 52 | no | 14,449,481 | Wayback → servidor oficial |
| 2023 | QQP_2023.rar | 93,850,207 | `1b9eac2eacc8` | 24 | no | 14,782,812 | Wayback → servidor oficial |
| 2024 | QQP_2024.rar | 96,058,666 | `740e1498e9d7` | 24 | sí | 14,889,219 | qqp.php actual |
| 2025 | QQP_2025.rar | — | `` | 24 | sí | 13,270,524 | qqp.php actual |
| 2026 | QQP_2026.rar | 59,971,365 | `903f67db03c0` | 16 | sí | 9,388,457 | qqp.php actual |

## CDMX: observaciones por año

| año | filas crudas | limpias | inválidos (fecha/precio/identidad) | repeticiones | en conflicto | rango de fechas | días con dato | productos | sucursales | series | puntos por producto (mediana / máx.) | puntos por serie (mediana / máx.) |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 2018 | 45,786 | 45,710 | 0 (0/0/0) | 0 | 76 | 2018-01-02 – 2018-12-28 | 252 | 230 | 76 | 4,641 | 116 / 1,202 | 6 / 52 |
| 2019 | 49,208 | 49,186 | 0 (0/0/0) | 0 | 22 | 2019-01-02 – 2019-12-31 | 253 | 271 | 76 | 4,894 | 85 / 1,245 | 6 / 53 |
| 2020 | 30,680 | 30,664 | 0 (0/0/0) | 0 | 16 | 2020-01-02 – 2020-12-31 | 146 | 237 | 78 | 4,559 | 82 / 707 | 5 / 33 |
| 2021 | 53,676 | 53,459 | 0 (0/0/0) | 145 | 72 | 2021-01-04 – 2021-12-31 | 253 | 247 | 80 | 4,734 | 107 / 1,155 | 8 / 51 |
| 2022 | 52,211 | 51,914 | 0 (0/0/0) | 237 | 60 | 2022-01-03 – 2022-12-30 | 252 | 258 | 85 | 5,164 | 97 / 1,424 | 7 / 50 |
| 2023 | 63,612 | 63,024 | 0 (0/0/0) | 502 | 86 | 2023-01-02 – 2023-12-29 | 254 | 249 | 82 | 5,413 | 130 / 1,630 | 8 / 54 |
| 2024 | 57,896 | 57,590 | 0 (0/0/0) | 232 | 74 | 2024-01-02 – 2024-12-30 | 252 | 257 | 85 | 5,431 | 123 / 1,411 | 7 / 53 |
| 2025 | 39,989 | 39,363 | 0 (0/0/0) | 440 | 186 | 2025-01-02 – 2025-12-31 | 249 | 231 | 80 | 4,551 | 93 / 980 | 6 / 46 |
| 2026 | 18,783 | 18,228 | 0 (0/0/0) | 519 | 36 | 2026-01-02 – 2026-08-31 | 166 | 210 | 74 | 2,843 | 41.5 / 573 | 5 / 32 |

Filas crudas = limpias + exclusiones; coinciden con el conteo por CSV de `qqp_auditoria` en todos los años. Inválidos entre paréntesis: fecha / precio / identidad (una fila puede tener más de un motivo).

Pares cadena + nombre comercial con más de un `sucursal_id` (y filas que colapsarían en la CLAVE si `vendedor_o_cadena` no incluyera `sucursal_id`): 2018: 0 (0 filas), 2019: 0 (0 filas), 2020: 0 (0 filas), 2021: 0 (0 filas), 2022: 0 (0 filas), 2023: 0 (0 filas), 2024: 0 (0 filas), 2025: 0 (0 filas), 2026: 0 (0 filas).

### CDMX: series con cobertura para el Buen Fin del mismo año

| año | evento | series | con base (días) | base suficiente | con previo (días) | con evento (días) | cobertura ahorro | cobertura alza |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2018 | BF2018 | 4,641 | 1,913 (33 d) | 535 | 1,383 (9 d) | 1,803 (4 d) | **284** | **115** |
| 2019 | BF2019 | 4,894 | 2,486 (33 d) | 1,223 | 1,533 (10 d) | 2,172 (4 d) | **655** | **313** |
| 2020 | BF2020 | 4,559 | 1,626 (31 d) | 682 | 771 (8 d) | 2,199 (12 d) | **511** | **102** |
| 2021 | BF2021 | 4,734 | 2,415 (31 d) | 894 | 1,530 (9 d) | 1,728 (5 d) | **624** | **320** |
| 2022 | BF2022 | 5,164 | 2,609 (33 d) | 1,131 | 1,413 (10 d) | 1,755 (2 d) | **630** | **310** |
| 2023 | BF2023 | 5,413 | 2,501 (33 d) | 996 | 1,601 (10 d) | 1,783 (4 d) | **563** | **247** |
| 2024 | BF2024 | 5,431 | 2,502 (32 d) | 925 | 1,496 (10 d) | 1,756 (4 d) | **544** | **205** |
| 2025 | BF2025 | 4,551 | 1,938 (32 d) | 499 | 1,112 (10 d) | 1,316 (5 d) | **298** | **93** |
| 2026 | BF2026 | 2,843 | 0 (0 d) | 0 | 0 (0 d) | 0 (0 d) | **0** | **0** |

## Nacional (todas las entidades): observaciones por año

| año | filas crudas | limpias | inválidos (fecha/precio/identidad) | repeticiones | en conflicto | rango de fechas | días con dato | productos | sucursales | series | puntos por producto (mediana / máx.) | puntos por serie (mediana / máx.) |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 2018 | 616,216 | 615,708 | 0 (0/0/0) | 0 | 508 | 2018-01-02 – 2018-12-31 | 254 | 234 | 678 | 40,043 | 1,321 / 14,526 | 11 / 55 |
| 2019 | 462,756 | 462,602 | 0 (0/0/0) | 0 | 154 | 2019-01-02 – 2019-12-31 | 254 | 277 | 656 | 36,047 | 810 / 11,286 | 9 / 54 |
| 2020 | 214,953 | 214,844 | 0 (0/0/0) | 5 | 104 | 2020-01-02 – 2020-12-31 | 149 | 238 | 518 | 26,497 | 566 / 4,157 | 7 / 33 |
| 2021 | 336,714 | 336,229 | 0 (0/0/0) | 357 | 128 | 2021-01-04 – 2021-12-31 | 253 | 271 | 533 | 29,223 | 612 / 6,469 | 8 / 53 |
| 2022 | 316,795 | 316,103 | 0 (0/0/0) | 558 | 134 | 2022-01-03 – 2022-12-30 | 252 | 266 | 556 | 29,612 | 604 / 7,304 | 7 / 54 |
| 2023 | 363,692 | 362,545 | 0 (0/0/0) | 999 | 148 | 2023-01-02 – 2023-12-29 | 254 | 256 | 510 | 29,503 | 698 / 9,385 | 8 / 55 |
| 2024 | 359,419 | 358,769 | 0 (0/0/0) | 506 | 144 | 2024-01-02 – 2024-12-30 | 255 | 264 | 493 | 29,904 | 680 / 9,021 | 8 / 55 |
| 2025 | 237,405 | 236,308 | 0 (0/0/0) | 791 | 306 | 2025-01-02 – 2025-12-31 | 252 | 234 | 474 | 24,428 | 560.5 / 4,569 | 7 / 46 |
| 2026 | 130,295 | 129,219 | 0 (0/0/0) | 1,006 | 70 | 2026-01-02 – 2026-08-31 | 166 | 220 | 452 | 16,018 | 320 / 3,299 | 6 / 33 |

Filas crudas = limpias + exclusiones; coinciden con el conteo por CSV de `qqp_auditoria` en todos los años. Inválidos entre paréntesis: fecha / precio / identidad (una fila puede tener más de un motivo).

Pares cadena + nombre comercial con más de un `sucursal_id` (y filas que colapsarían en la CLAVE si `vendedor_o_cadena` no incluyera `sucursal_id`): 2018: 20 (7,566 filas), 2019: 20 (5,289 filas), 2020: 9 (1,311 filas), 2021: 9 (1,563 filas), 2022: 14 (1,230 filas), 2023: 11 (1,221 filas), 2024: 11 (1,261 filas), 2025: 11 (627 filas), 2026: 10 (325 filas).

### Nacional (todas las entidades): series con cobertura para el Buen Fin del mismo año

| año | evento | series | con base (días) | base suficiente | con previo (días) | con evento (días) | cobertura ahorro | cobertura alza |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2018 | BF2018 | 40,043 | 21,469 (34 d) | 9,167 | 14,977 (9 d) | 17,749 (4 d) | **7,363** | **3,576** |
| 2019 | BF2019 | 36,047 | 16,928 (33 d) | 10,955 | 13,288 (10 d) | 15,720 (4 d) | **8,694** | **4,063** |
| 2020 | BF2020 | 26,497 | 9,038 (31 d) | 4,247 | 5,446 (9 d) | 11,579 (12 d) | **3,198** | **558** |
| 2021 | BF2021 | 29,223 | 14,817 (31 d) | 5,589 | 9,412 (9 d) | 11,387 (5 d) | **4,424** | **1,784** |
| 2022 | BF2022 | 29,612 | 15,021 (33 d) | 7,308 | 10,142 (10 d) | 11,385 (2 d) | **5,249** | **2,948** |
| 2023 | BF2023 | 29,503 | 12,778 (33 d) | 5,775 | 9,443 (10 d) | 11,177 (4 d) | **4,243** | **2,158** |
| 2024 | BF2024 | 29,904 | 13,702 (32 d) | 5,483 | 9,698 (10 d) | 11,655 (4 d) | **4,234** | **2,037** |
| 2025 | BF2025 | 24,428 | 11,088 (32 d) | 3,325 | 6,882 (10 d) | 8,542 (5 d) | **2,579** | **1,108** |
| 2026 | BF2026 | 16,018 | 0 (0 d) | 0 | 0 (0 d) | 0 (0 d) | **0** | **0** |

Reglas (Avance 1): cobertura de ahorro = ≥4 fechas en la base que abarquen ≥21 días y ≥1 fecha en el evento; cobertura de alza = además ≥2 fechas en el previo. Base D−60…D−15, previo D−14…D−1, evento D0…fin. "Base suficiente" = sólo la condición de base (útil para el año en curso). Entre paréntesis: días distintos con algún dato en esa ventana.

## 2026: base previa al Buen Fin 2026

El archivo 2026 publicado hoy llega sólo hasta **2026-08-31** (CDMX; nacional: 2026-08-31; último CSV `2026/08-2026_Q2.csv`). Ventana base BF2026: 2026-09-14 – 2026-10-29 (evento 2026-11-13 – 2026-11-17; fechas de eventos.yaml: Prensa (Bloomberg Línea, SDP, N+); elbuenfin.org no legible sin JS. Ver reports/fechas_buen_fin.md). Por lo tanto la base BF2026 tiene **0 series** con dato en CDMX (0 días) y 0 a nivel nacional: el archivo todavía NO trae la base previa al BF2026. Diagnóstico: en los últimos 60 días del archivo (2026-07-03 – 2026-08-31) ya hay 687 series CDMX y 5,345 nacionales con ≥4 fechas en ≥21 días; si PROFECO publica septiembre–octubre con un muestreo similar, ese es el orden de magnitud esperable. `diario` detecta la versión nueva del RAR y re-extrae.

## Fechas del Buen Fin usadas

| evento | inicio | fin | fuente de las fechas |
|---|---|---|---|
| BF2018 | 2018-11-16 | 2018-11-19 | https://www.excelsior.com.mx/nacional/dan-a-conocer-las-fechas-de-el-buen-fin-2018/1269716 |
| BF2019 | 2019-11-15 | 2019-11-18 | https://www.xataka.com.mx/comercio-electronico/buen-fin-2019-se-realizara-mexico-15-al-18-noviembre |
| BF2020 | 2020-11-09 | 2020-11-20 | https://expansion.mx/economia/2020/09/08/buen-fin-2020-durara-12-dias-para-evitar-aglomeraciones |
| BF2021 | 2021-11-10 | 2021-11-16 | https://expansion.mx/finanzas-personales/2021/10/25/cuando-es-el-buen-fin-2021-mexico |
| BF2022 | 2022-11-18 | 2022-11-21 | https://vanguardia.com.mx/noticias/llega-el-buen-fin-2022-estas-son-las-fechas-oficiales-seran-4-dias-de-ofertas-AH3867121 |
| BF2023 | 2023-11-17 | 2023-11-20 | https://www.nmas.com.mx/economia/buen-fin-mexico-2023-tiene-fecha-empresas-ya-pueden-registrarse/ |
| BF2024 | 2024-11-15 | 2024-11-18 | Secretaría de Economía (anuncio oficial) |
| BF2025 | 2025-11-13 | 2025-11-17 | Avance 1 (QQP 2025) |
| BF2026 | 2026-11-13 | 2026-11-17 | Prensa (Bloomberg Línea, SDP, N+); elbuenfin.org no legible sin JS. Ver reports/fechas_buen_fin.md |

BF2018–BF2023 no están en `config/eventos.yaml`; se toman de `EVENTOS_HISTORICOS` (qqp.py) con la fuente de prensa indicada, que cita el anuncio de la Secretaría de Economía. El orquestador debe pasarlas a eventos.yaml. BF2020 duró 12 días por la pandemia y BF2021 7 días: la ventana de evento es más larga.

## Búsqueda de años 2018–2023

- `qqp.php` (página actual) sólo lista 2024, 2025 y 2026, más metadatos y diccionario.
- Wayback Machine: el CDX de `qqp.php` tiene capturas de 2023-12-04 a 2025-12-08; las de 2023-12 a 2025-12 listan "Base de Datos Histórica Quién es Quién en los Precios" 2015–2023 con sus enlaces `file.php?t=...`. Esos enlaces **siguen respondiendo hoy en el servidor oficial** con `application/x-rar` (`QQP_<año>.rar`). Se descargaron 2018–2023 desde datos.profeco.gob.mx (no desde Wayback); el manifiesto de cada RAR guarda la URL oficial, la captura donde se halló el enlace, bytes y SHA-256. 2015–2017 también existen, pero quedan fuera del alcance pedido.
- Portal de históricos (`profeco.gob.mx/precios/canasta/Dato_historico.aspx`): la base 1999+ sólo se entrega por solicitud escrita (formulario o correo a quienesquien@profeco.gob.mx); no hay descarga directa. No se envió ninguna solicitud.
- datos.gob.mx (API CKAN y ficha del conjunto): respondió 403 a nuestro user-agent; no se insistió.
- datamx.io: el conjunto "Quién es Quién en los precios" sólo enlaza un CSV en Google Drive actualizado en 2018-06 (histórico desde 2015) y una API de datos.gob.mx ya retirada; no aporta 2018–2023 completos.
- Los crudos de cada consulta están en `data/raw/qqp/2026-10-16/` y `data/raw/qqp/wayback/`.

## Diferencias de formato entre años

- 2024–2026: CSV con cabecera; 2018–2023: sin cabecera (mismas 15 columnas en el mismo orden). `fila_origen` es el número de línea del CSV en ambos casos.
- 2018–2022: un CSV por semana (`NNAAAA.csv`); 2023–2025: dos por mes; 2026: `MM-2026_Q1/Q2`.
- 2018–2023 vienen en MAYÚSCULAS; `normalizar` iguala mayúsculas/acentos, pero los `producto_id` de años distintos pueden diferir si PROFECO cambió la redacción de la presentación: el empate entre años se hace después por `modelo_normalizado`, no por `producto_id`.

## Límites

- QQP muestrea de forma esporádica: faltan días por serie y no hay precio diario; un día sin dato es faltante.
- Precio registrado en tienda física por verificadores de PROFECO; QQP no publica precio anterior ni porcentaje de descuento (esas columnas quedan vacías).
- Identidad provisional (texto de producto+marca+presentación), no EAN/GTIN.
- Filas con fecha de otro año dentro de un archivo (p. ej. la semana 53) se excluyen como inválidas, igual que en el Avance 1; quedan en `*_exclusiones`.

## Verificado / pendiente

- Verificado: reproducción exacta del Avance 1 (tabla arriba); CLAVE única, precio > 0 y fechas válidas en cada tabla bronze (`validar_observaciones` y tests); filas crudas = limpias + exclusiones = auditoría por CSV.
- Pendiente: pasar BF2018–BF2023 a `config/eventos.yaml`; re-extraer 2026 cuando PROFECO publique la versión con noviembre; emparejar `modelo_normalizado` con la lista fija de productos.

## Comandos

```
python -m sconto.fuentes.qqp backfill --anios 2018 2019 2020 2021 2022 2023 2024 2025 2026   # reanudable
python -m sconto.fuentes.qqp diario        # detecta versión nueva de 2026 y re-extrae
python -m sconto.fuentes.qqp reproduccion  # compara 2025 con el Avance 1
python -m sconto.fuentes.qqp reporte
```
