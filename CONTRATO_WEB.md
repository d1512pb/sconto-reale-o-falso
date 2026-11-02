# Entrega del análisis a la web

Contrato `sconto-mart-v1`. La captura construye gold; el notebook 03 y `sconto.mart` ejecutan el mismo ETL y modelo. La web sólo consulta el resultado. Colab no aloja un servidor ni programa las capturas.

## Archivos de entrega

`sconto_web.zip`: tablas Parquet y CSV.gz, `sconto_web.sqlite`, `web_feed.json`, `modelo.json`, `casos_para_revision.csv` y `manifest.json`. El manifiesto contiene fecha de corte del snapshot, SHA-256 de entrada, revisión del código, conteos y hashes de todos los archivos. Los campos ausentes conservan NULL; nunca son cero.

SQLite conserva claves primarias/foráneas y comprueba integridad. El lector de la web valida los hashes, abre SQLite en modo de sólo lectura y usa parámetros para los filtros. No hay pickle, credenciales ni HTML crudo en esta entrega. `ruta_raw` y `hash_raw` son trazabilidad del registro; el archivo crudo privado no se publica en el ZIP.

## Tablas

- `productos`: catálogo de identidades nativas/canónicas. PK `producto_canonico_id`. `en_catalogo_web` selecciona los 200 de captura diaria y `en_piloto` los primeros 30. `confianza_match` conserva la situación real; el ID nativo no prueba coincidencia con QQP ni con variantes de otra fuente.
- `eventos`: PK `evento_id`. D0, fin y ventanas base/previo/evento/posterior.
- `series`: PK `serie_id`. FK nullable a producto; fuente, plataforma, vendedor, canal, moneda, tipo de precio y contexto. No se une un mínimo multitienda a la historia de un vendedor.
- `observaciones`: PK `obs_id`, FK a serie. Precios, fechas, anuncio textual, condiciones y trazabilidad. Selección para el catálogo y los casos del modelo; no es una copia de toda la base nacional.
- `precios_diarios`: PK (`serie_id`, `fecha_precio`). Mediana de las observaciones reales de ese día, conteo y FK `obs_ejemplo_id`. No se añaden días ni se interpolan curvas.
- `referencias_base`: PK (`serie_id`, `evento_id`). Fechas base, mediana, mínimo/máximo, P25/P75, número de fechas, amplitud y flags. `cobertura_base` exige ≥4 fechas/≥21 días y vendedor identificado; la consulta exige también `base_cerrada`. P25/P75 es rango central observado, no intervalo de confianza. Un contexto `minimo_multitienda` sigue siendo sólo referencia de mercado.
- `ofertas`: última observación real por serie, FK a observación y serie. `edad_dias` respecto al corte y `observada_en_corte` evitan presentar una oferta antigua como captura de hoy. No se certifica disponibilidad ni entrega.
- `resultados_modelo`: PK `serie_evento_id`, FKs a serie y evento. Variables, puntaje, reglas, etapa y revisión pendiente. Sólo eventos terminados del dominio QQP CDMX físico. El puntaje no es probabilidad de fraude.
- `evaluacion_modelo`: experimento, métrica, valor, tamaño e interpretación. Estabilidad y coincidencia con reglas; ninguna métrica constituye exactitud supervisada.
- `sensibilidad`: tabla de cobertura del gold para mínimos 2/3/4/5 fechas.
- `calidad_fuentes`: filas, IDs, fechas extremas, última captura y cantidad de tachados de **todo el gold**. Se distingue del subconjunto publicado para consulta.

Los tipos concretos quedan en Parquet y en `PRAGMA table_info`. Fechas ISO `YYYY-MM-DD`, precios MXN positivos, porcentajes en puntos de porcentaje, faltantes NULL. El detalle completo de columnas se exporta en `reports/diccionario_mart.json`.

## Consulta y actualización

Una oferta introducida manualmente se compara con moneda, canal y referencia seleccionados. El ahorro frente a la mediana sólo se denomina ahorro del vendedor cuando coincide su serie. Una referencia multitienda nunca produce una brecha del anuncio de una tienda. El tachado produce un descuento **implícito** separado del porcentaje mostrado textualmente. La brecha de una consulta no equivale a la mediana de un Buen Fin ni demuestra engaño.

La web muestra el corte del snapshot y alerta si tiene más de un día. Los precios introducidos por el usuario no se guardan. Los anuncios indirectos, beneficios bancarios, cupones, envío o membresía requieren revisar las condiciones originales.

El job `analitica` corre después de `recolectar` y publica `sconto_web_actual.zip` y una copia por ejecución/hash en el release `datos`. Si falla el ETL, permanece el último paquete válido y la web muestra su antigüedad. La tarea Windows sigue capturando como respaldo; no publica un ZIP competidor. El notebook 03 queda fijado al snapshot del avance para reproducibilidad; los datos diarios continúan actualizándose por separado.

`sconto.publicar_web` deriva de esa entrega una proyección pública de 200 productos y sus días observados, con `snapshot.json` y hash de `datos.json`. El job `web` despliega esa proyección en GitHub Pages. El navegador compara su hash antes de habilitar consultas; una actualización incompleta no emite resultados. La base completa no se copia al sitio. Las reglas de consulta JavaScript se contrastan con Python mediante pruebas de paridad.
