# Resumen de la recolección

Generado 2026-11-09 desde `data/gold/` (construido 2026-11-09T23:20:16+00:00). Cifras calculadas,
no escritas a mano. Resultados de **ejecución local** salvo que se indique otra cosa; las corridas de GitHub Actions
quedan en `data/estado/github.csv` y las de Colab no se cuentan aquí.

## Cobertura por fuente

| fuente | metodo | canal | filas | ids_externos | productos_canonicos | desde | hasta | dias_con_dato | puntos_por_id_mediana | puntos_por_id_max | con_precio_tachado | con_pct_mostrado |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| amazon | scraping | en_linea | 1 | 1 | 0 | 2026-10-16 | 2026-10-16 | 1 | 1 | 1 | 0 | 0 |
| preciometro | agregador | en_linea | 250,477 | 2,795 | 1,493 | 2026-07-18 | 2026-11-09 | 115 | 90 | 114 | 0 | 0 |
| preciometro_ofertas | agregador | en_linea | 26,210 | 9,520 | 1,485 | 2026-10-16 | 2026-11-09 | 22 | 1 | 21 | 0 | 0 |
| qqp_cdmx | archivo_oficial | tienda_fisica | 409,138 | 1,022 | 231 | 2018-01-02 | 2026-08-31 | 2,077 | 93 | 1,803 | 0 | 0 |
| tiendas | scraping | en_linea | 12 | 1 | 1 | 2026-10-20 | 2026-11-08 | 12 | 12 | 12 | 12 | 0 |
| wayback | wayback | en_linea | 109 | 28 | 0 | 2024-09-06 | 2025-10-17 | 81 | 2 | 24 | 67 | 67 |

Una fuente sólo se considera integrada si tiene filas en `observaciones`. Detalle y límites de cada una en
`reports/cobertura_<fuente>.md`.

## Series por evento

| evento_id | plataforma_serie | series | cobertura_ahorro | cobertura_alza | con_anuncio | con_brecha |
|---|---|---|---|---|---|---|
| BF2024 | amazon | 4 | 0 | 0 | 0 | 0 |
| BF2024 | mercadolibre | 15 | 0 | 0 | 0 | 0 |
| BF2024 | qqp_cdmx | 3,296 | 544 | 205 | 0 | 0 |
| BF2025 | amazon | 5 | 0 | 0 | 0 | 0 |
| BF2025 | qqp_cdmx | 2,606 | 298 | 93 | 0 | 0 |
| BF2026 | amazon | 1 | 0 | 0 | 0 | 0 |
| BF2026 | liverpool | 1 | 0 | 0 | 0 | 0 |
| BF2026 | preciometro | 2,795 | 0 | 0 | 0 | 0 |
| BF2026 | preciometro_ofertas | 10,032 | 0 | 0 | 0 | 0 |

Mínimos del Avance 1 (≥4 fechas base en ≥21 días, ≥1 en el evento; alza: ≥2 en el previo). Sensibilidad con
2–5 fechas en `data/gold/sensibilidad`. El BF2026 aún no ocurre: sus series de evento se llenan del 13 al 17 nov.

## Qué cubre cada hueco del Avance 1

- **1. Precio anunciado / tachado**: amazon 1 filas (2026-10-16 → 2026-10-16, tachado 0); wayback 109 filas (2024-09-06 → 2025-10-17, tachado 67)
- **2. Más fuentes y eventos (BF2024–BF2026)**: amazon 1 filas (2026-10-16 → 2026-10-16, tachado 0); preciometro 250,477 filas (2026-07-18 → 2026-11-09, tachado 0); preciometro_ofertas 26,210 filas (2026-10-16 → 2026-11-09, tachado 0); qqp_cdmx 409,138 filas (2018-01-02 → 2026-08-31, tachado 0); wayback 109 filas (2024-09-06 → 2025-10-17, tachado 67)
- **3. Amazon / Mercado Libre, por día y en el tiempo**: amazon 1 filas (2026-10-16 → 2026-10-16, tachado 0); preciometro 250,477 filas (2026-07-18 → 2026-11-09, tachado 0); preciometro_ofertas 26,210 filas (2026-10-16 → 2026-11-09, tachado 0)
- **4. Días faltantes de QQP**: amazon 1 filas (2026-10-16 → 2026-10-16, tachado 0); preciometro 250,477 filas (2026-07-18 → 2026-11-09, tachado 0); preciometro_ofertas 26,210 filas (2026-10-16 → 2026-11-09, tachado 0)

## Estado de las corridas

| fuente | entorno | estado | dias |
|---|---|---|---|
| amazon | local | bloqueado | 1 |
| commoncrawl | local | bloqueado | 1 |
| mercadolibre | github | sin_credenciales | 20 |
| mercadolibre | local | sin_credenciales | 11 |
| preciometro | github | ok | 20 |
| preciometro | local | ok | 1 |
| preciometro | local | parcial | 2 |
| qqp_cdmx | local | fallo | 9 |
| qqp_cdmx | local | ok | 1 |
| qqp_nacional | local | fallo | 9 |
| qqp_nacional | local | ok | 1 |
| servicio_local | local | ok | 8 |
| servicio_local | local | parcial | 1 |
| tiendas | local | ok | 11 |
| tiendas | local | parcial | 1 |
| wayback | local | ok | 1 |

## Productos objetivo

| prioridad | confianza_match | productos |
|---|---|---|
| 1 | descartado | 3 |
| 1 | probable | 26 |
| 1 | sin_candidato | 24 |
| 2 | descartado | 1 |
| 2 | probable | 14 |
| 2 | sin_candidato | 18 |
| 3 | descartado | 10 |
| 3 | probable | 28 |
| 3 | sin_candidato | 107 |
| 4 | probable | 1,493 |

Los emparejamientos `probable` están en `reports/matches_para_revisar.csv` para validación manual (Igor y Kevin).
