# Auditoría del corte final de datos · 2026-11-26

Generada 2026-11-26T17:24:34+00:00 con `scripts/auditar_corte_final_v2.py`, sólo lectura sobre las copias congeladas en `data/operacion/v2/corte_final_20261126`.

## 1. Paquete histórico multifuente

`sconto_colab_2026-11-26.zip` · SHA-256 `e6e8b353942ca0f18996417910e72f513c796c5b68c819fe5fe931056d7a45e3` · exportado 2026-11-26T16:58:45+00:00.

**690,888 observaciones limpias**, 1,724 productos en catálogo.

| fuente | filas | productos | series | fecha_min | fecha_max | captura_max | canales |
|---|---|---|---|---|---|---|---|
| amazon | 1 | 0 | 1 | 2026-10-16 | 2026-10-16 | 2026-10-16 | en_linea |
| preciometro | 251,438 | 1493 | 2795 | 2026-07-18 | 2026-11-14 | 2026-11-14 | en_linea |
| preciometro_ofertas | 30,184 | 1485 | 10123 | 2026-10-16 | 2026-11-14 | 2026-11-14 | en_linea |
| qqp_cdmx | 409,138 | 231 | 26811 | 2018-01-02 | 2026-08-31 | 2026-10-16 | tienda_fisica |
| tiendas | 18 | 1 | 1 | 2026-10-20 | 2026-11-14 | 2026-11-14 | en_linea |
| wayback | 109 | 0 | 56 | 2024-09-06 | 2025-10-17 | 2026-10-16 | en_linea |

### Integridad

- Duplicados por clave: 0
- Precios no positivos: 0 · fechas no válidas: 0
- Descuentos anunciados fuera de ±100%: 0
- Series con canal mezclado: 0
- Filas marcadas para revisar captura: 46,886 · precio revisado por la fuente: 525 · exclusiones: 0
- Huellas de tablas contra `paquete.json`: todas coinciden
- Reproducción del Avance 1 (QQP 2025: 39,363 filas; BF2025: 298 ahorro / 93 alza): se conserva

### Observaciones por ventana del Buen Fin

**BF2024**

| fuente | base | previo | evento | posterior |
|---|---|---|---|---|
| qqp_cdmx | 7,456 | 1,916 | 4,489 | 1,282 |
| wayback | 23 | 10 | 0 | 2 |

**BF2025**

| fuente | base | previo | evento | posterior |
|---|---|---|---|---|
| qqp_cdmx | 4,967 | 1,411 | 3,275 | 994 |
| wayback | 7 | 0 | 0 | 0 |

**BF2026**

| fuente | base | previo | evento | posterior |
|---|---|---|---|---|
| amazon | 1 | 0 | 0 | 0 |
| preciometro | 93,589 | 2,708 | 379 | 0 |
| preciometro_ofertas | 17,132 | 11,474 | 1,578 | 0 |
| tiendas | 3 | 13 | 2 | 0 |

### Series por evento (`series_evento`)

| evento_id | plataforma_serie | series | cobertura_ahorro | cobertura_alza |
|---|---|---|---|---|
| BF2024 | amazon | 4 | 0 | 0 |
| BF2024 | mercadolibre | 15 | 0 | 0 |
| BF2024 | qqp_cdmx | 3296 | 544 | 205 |
| BF2025 | amazon | 5 | 0 | 0 |
| BF2025 | qqp_cdmx | 2606 | 298 | 93 |
| BF2026 | amazon | 1 | 0 | 0 |
| BF2026 | liverpool | 1 | 0 | 0 |
| BF2026 | preciometro | 2795 | 187 | 187 |
| BF2026 | preciometro_ofertas | 10123 | 0 | 0 |

Matriz del modelo: 485 filas, variables ahorro_historico_pct, alza_previa_pct, variabilidad_base_pct.

## 2. Piloto PROFECO Buen Fin 2026 (precios diarios por sucursal física)

`piloto_profeco_intradia.sqlite3` · SHA-256 `af593a741cc84d36339292fbf54912b216a2c0f76c40d9c01199705dd92ff0fc`.

- Capturas: 305 (primera 2026-10-21T08:29:30.000000Z, última 2026-11-26T17:21:58.336573Z). Días con captura PROFECO: 12 (2026-11-14 a 2026-11-26).
- Intentos con error: 0 · claves foráneas: correctas.
- Filas brutas 35,552 → **3,144 precios únicos anuncio·fecha de PROFECO**; 24 modelos, 85 sucursales.
- Fecha de precio de 2026-09-01 a **2026-11-17** (último día publicado).
- Misma fecha con precio distinto entre capturas: 0 (se conserva la captura más reciente).
- Zonas: {'plaza CDMX/ZMVM': 3144}.

| ventana | precios |
|---|---|
| evento | 1,300 |
| base | 1,238 |
| previo | 358 |
| fuera_de_ventanas | 248 |

| indicador | anuncios |
|---|---|
| anuncios_producto_sucursal | 718 |
| con_precio_en_evento | 558 |
| con_base_previo_y_evento | 197 |
| con_previo_evento_y_posterior | 0 |

Precios únicos por fecha (últimos 10 días publicados): 2026-11-06: 39, 2026-11-09: 42, 2026-11-10: 30, 2026-11-11: 32, 2026-11-12: 16, 2026-11-13: 367, 2026-11-14: 306, 2026-11-15: 286, 2026-11-16: 286, 2026-11-17: 55.

## 3. Ofertas en línea

- Observaciones archivadas: 17 ({'liverpool': 17}, ['2026-10-21', '2026-11-14']). Con vendedor: 0 · con disponibilidad: 0.
- **Ofertas en línea completas y verificadas (vendedor, variante, inventario, total): 0.** Sears, Liverpool y Preciómetro quedaron en pausa desde el 14 de noviembre; Mercado Libre sin credenciales autorizadas; Amazon directo desactivado por decisión del equipo.

## 4. QQP anual 2026

- Último estado de la vigilancia: `sin_publicacion` · consultado 2026-11-26T17:22:10.792595+00:00 · última modificación del servidor None.
- El índice histórico de datos abiertos responde HTTP 404 desde el 9 de noviembre. El último dato QQP en el paquete es 2026-08-31: el archivo anual no cubre el Buen Fin 2026 y no hay series QQP 2026 evaluables.

## 5. Copia del volumen de Fly

`intradia.sqlite3` · SHA-256 `a63e87ac7b12bf508ba17fa48bdc8c24e21a79ea13091b068f37a4a20d230e17` · integridad SQLite `ok`.
- Tablas: {'trabajos': 48, 'intentos': 48, 'capturas': 48, 'ofertas': 689, 'observaciones_intradia': 0, 'observaciones_diarias_fuente': 5320}.
- Última captura 2026-11-16T21:13:11.461852Z · último día de precio 2026-11-15. El colector en la nube nunca se habilitó; la API sirve este almacén congelado.

## 6. Archivos congelados

| archivo | bytes | sha256 |
|---|---|---|
| estado_operacion/2026-11-26T112205010382.json | 334 | `90e390df5318c1e367c5e7a76d29e5cd8ab9aaa1cce0ae172ca71c34d5d3a198` |
| estado_operacion/ALERTA_diaria.md | 694 | `b1f8f4075357d43e16ce3335f5419b7b172c432a9f80d5718ab290de06a40a0d` |
| estado_operacion/ALERTA_profeco.md | 182 | `ac2e8406ffaf96151109f1124f435bfc765032776b928f4c30c7a2742d6efc7f` |
| fly/catalogo.sqlite | 188,416 | `30be5a4e137ec8ea3b73ee1373c7f9e3cfb3fabcf9dc78b17ed4e33cde349ee4` |
| fly/intradia.sqlite3 | 3,706,880 | `a63e87ac7b12bf508ba17fa48bdc8c24e21a79ea13091b068f37a4a20d230e17` |
| fly/presupuesto-fly-v2.json | 130 | `9c486a0c060e7cec9a3626ed6f8f6a99f3c5cb3aa149561cd0087b03c9edb47b` |
| piloto_profeco_intradia.sqlite3 | 22,433,792 | `af593a741cc84d36339292fbf54912b216a2c0f76c40d9c01199705dd92ff0fc` |
| qqp_estado.json | 111 | `8cfc5f13be711b7d4a0ad9f97ac8022b0d949806ea30369f6e1ae331a7597fe4` |
| sconto_colab_2026-11-26.zip | 60,516,573 | `e6e8b353942ca0f18996417910e72f513c796c5b68c819fe5fe931056d7a45e3` |
| tareas_antes/Sconto_recoleccion_diaria.xml | 2,035 | `7373ce8697ebbad812613eed171003dc30294913cd51ccc1b5a01182f3ce9fdb` |
| tareas_antes/Sconto_v2_Buzon_de_cotizaciones_autorizadas.xml | 1,860 | `a34e503f6ad44e0c1297e251017c1e7ea6cfc1a955ff3ca764ba95c838b19afc` |
| tareas_antes/Sconto_v2_Piloto_PROFECO_Buen_Fin_2026.xml | 1,870 | `855f9c1a21a3cdee5d5f103a1a16b15674782b7a20e3853614829aa014019338` |
| tareas_antes/Sconto_v2_Reactivar_buzon_20261115_221210.xml | 1,794 | `24f3e392b2135bd494c489852974d525373cf89eb83b0e9d623cbd0ec35b4d87` |
| tareas_antes/Sconto_v2_Vigilancia_QQP.xml | 1,851 | `d8776b1e6d437daf15725968dcb48f1fd4d8562592c49df64d22f3b558322afd` |

