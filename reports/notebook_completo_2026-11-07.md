# Notebook completo · corte del 7 de noviembre de 2026

Se ejecutaron las 28 celdas (16 de código) en un kernel nuevo de Python 3.11 local, sin errores. La copia ejecutada se conserva en Drive en el mismo archivo del notebook 03. No se afirma haber ejecutado esta edición en la nube de Colab. El cuaderno 01 y la evidencia del Avance 1 no se modificaron.

[Abrir notebook](https://colab.research.google.com/drive/1bnrjKM-Wz0YPo8UuQKrEHBm4mtDrn3KP) · [Contrato para la app](../CONTRATO_APP.md)

## ETL y resultados reales

1,015,811 capturas extraídas → 683,942 observaciones limpias. Se consolidaron 331,869 capturas repetidas, con trazabilidad y sin imputación. Hubo cero exclusiones en estas entradas; el mecanismo de exclusión se comprobó además con casos inválidos en pruebas. Cada captura queda representada por `n_capturas` o un motivo de exclusión.

Se reconstruyeron las observaciones del snapshot publicado y las matrices de modelado. Avance 1 reproducido: **39,363 observaciones QQP 2025, 298 series de ahorro y 93 de alza**. Los valores faltantes de los metadatos se comparan como faltantes equivalentes, sin rellenar precios.

| Fuente | Filas limpias | IDs externos | Primera fecha | Última fecha |
|---|---:|---:|---|---|
| QQP CDMX | 409,138 | 1,022 | 2018-01-02 | 2026-08-31 |
| Preciómetro mínimos | 250,095 | 2,795 | 2026-07-18 | 2026-11-07 |
| Preciómetro ofertas | 24,588 | 9,516 | 2026-10-16 | 2026-11-07 |
| Wayback | 109 | 28 | 2024-09-06 | 2025-10-17 |
| Tiendas | 11 | 1 | 2026-10-20 | 2026-11-07 |
| Amazon directo, prueba antigua desactivada | 1 | 1 | 2026-10-16 | 2026-10-16 |

Los IDs de fuentes distintas no equivalen a productos canónicos únicos. El catálogo general tiene 1,724 productos. La lista de consulta tiene 200; las categorías foco son laptops/computadoras y audífonos. Amazon reciente se obtiene de forma indirecta. Las fuentes sin filas no se presentan como integradas.

## Minería, búsqueda e indicador

Isolation Forest conserva 300 árboles y semilla 42: 205 series QQP físicas BF2024 para entrenamiento, 93 BF2025 para evaluación temporal. Se documentan solapamiento de productos, estabilidad con otras semillas, coincidencia con reglas y sensibilidad. No hay etiquetas verificadas de fraude. BF2026 incompleto no se puntúa.

El buscador recupera AirPods Pro 3 y la Lenovo IdeaPad Slim 3 i3/8GB/512GB, tolera la errata «Lenobo» y rechaza la consulta inexistente de la demo. Los cuatro casos de aceptación pasan; no se extrapola una exactitud poblacional a partir de ellos. Las variantes explícitamente contradictorias se separan.

La salida contiene 1,457 últimas ofertas por serie, incluidas ofertas antiguas que se muestran con su fecha: 209 títulos compatibles, 1,221 pendientes y 27 en conflicto. Compatibilidad textual no significa SKU confirmado. Al exigir también vigencia e historia, 117 ofertas reciben una señal de precio: 3 favorables, 73 altas y 41 sin señal clara; **1,340 quedan con evidencia insuficiente**. Esta restricción es deliberada: los faltantes no se convierten en buenas ofertas.

En el piloto, Liverpool registra AirPods Pro 3 a $4,339 con señal sin cambio claro frente a la base de mercado; Sears registra $7,039 mediante un tercero y señal de precio alto. La Lenovo en Sears figura a $13,499, también por encima de su referencia de mercado. Son precios publicados del corte, sin total de envío ni inventario confirmados. No hay suficientes anuncios e historia comparables para evaluar brechas de evento: cero series con brecha. Se conserva la diferencia entre referencia multitienda e historial del vendedor.

## Entrega y validación

`entrega_sconto_2026-11-07_a8c0bac09a14.zip` (78,315,472 bytes) incluye dataset completo en Parquet/CSV.gz, esquema por capa, auditoría, diccionarios y `datos_app.zip`. Este último contiene 16 tablas, SQLite con claves verificadas, catálogo, 1,457 ofertas evaluadas, historial diario, referencias, índice TF-IDF, JSON de consulta y resultados de minería. Se verificaron hashes y conteos de todas las tablas exportadas.

SHA-256 de la entrega: `a8c0bac09a14103f6fc26f611a26a5b495a68ae3e4d0bd2c48d041d4195806f5`.

**38 pruebas pasan**: limpieza y contabilidad, reproducción del Avance 1, variantes, búsqueda, antigüedad, comparabilidad, aislamiento temporal del modelo y contrato SQLite. Se excluyó la prueba del prototipo Streamlit; no se cambió su interfaz. Se inspeccionó la gráfica de la demo. Las 16 celdas de código terminaron con resultados y sin errores.

La revisión humana de los casos de anomalía y la confirmación independiente de SKU/condiciones siguen pendientes. La siguiente fase es construir la app instalable, conectar este contrato con la actualización diaria y probar en el teléfono el vencimiento de ofertas. La recolección diaria y el sitio existente continúan con su contrato anterior.
