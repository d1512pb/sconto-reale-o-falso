# Salida del notebook para la app · sconto-app-v1

El notebook 03 produce `entrega_sconto.zip`: dataset limpio completo en Parquet y CSV.gz, auditoría, diccionario y `datos_app.zip`. El segundo ZIP contiene el catálogo de consulta de 200 productos, sus series y ofertas, resultados históricos de minería, SQLite, JSON y manifiesto. La app instalable se implementará en la siguiente fase.

## Flujo de consulta

1. Cargar `manifest.json` y comprobar hashes. Mostrar `fecha_corte`.
2. Buscar nombre/modelo en `catalogo_consulta`; el índice TF-IDF exportado permite recuperar candidatos. Normalizar mayúsculas, acentos y espacios. No unir registros por similitud. Respetar conflictos de variante y pedir elección cuando el nombre sea ambiguo.
3. Filtrar `ofertas_evaluadas` por el ID seleccionado. Mostrar plataforma, vendedor, precio publicado, fecha, condiciones y enlace. Las ofertas se ordenan por precio publicado; el orden no certifica total, disponibilidad ni condición equivalente.
4. Resolver `referencia_serie_id` en `series`, `referencias_base` y `precios_diarios` para explicar y graficar. No rellenar días sin precio ni presentar el mínimo multitienda como historia de Sears.
5. Recalcular edad con la fecha real de consulta en America/Mexico_City. Fuera de 0–1 días, ocultar el indicador favorable/alto, mostrar evidencia insuficiente y motivo de antigüedad. El precio queda como registro histórico. No reutilizar sin este control el indicador calculado al corte.

## Archivos y relaciones

| Archivo/tabla | Contenido y clave |
|---|---|
| `catalogo_consulta` | PK producto_canonico_id; nombre, familia, foco_compra, es_paquete, atributos_json |
| `ofertas_evaluadas` | PK obs_id → ofertas; referencia_serie_id → series; precio, contexto, indicador, explicación |
| `revision_identidades` | PK obs_id → ofertas_evaluadas; conflictos y descripciones insuficientes |
| `evaluacion_busqueda` | Casos de aceptación elegidos para la demo; no estimación de exactitud general |
| `sensibilidad_indicador` | Clasificación con umbrales 5% y 10% por obs_id |
| `app_feed.json` | Catálogo y ofertas evaluadas, versión, corte y reglas |
| `indice_busqueda.json` | Vocabulario, IDF y matriz CSR; TF-IDF char_wb 3–5, norma l2, coseno, mínimo 0.15 |
| `web_feed.json` | Contrato anterior conservado; incluye series y referencias de la lista diaria |
| `sconto_web.sqlite` | Todas las tablas de aplicación, con claves e integridad comprobadas |
| `modelo.json` | Dominio, muestra, semilla y límites de Isolation Forest |
| `casos_para_revision.csv` | Revisión humana de anomalías históricas, pendiente |

Las tablas originales de productos, eventos, series, observaciones, precios_diarios, referencias_base, ofertas, resultados_modelo, evaluacion_modelo, sensibilidad y calidad_fuentes conservan su contrato. Cada tabla se entrega en Parquet y CSV.gz. `esquema.csv` en el dataset limpio registra tipos y nulos; `DICCIONARIO.md` explica los indicadores de origen.

## Campos nuevos

| Campo | Tipo/valores | Significado |
|---|---|---|
| identidad_oferta | compatible_texto / pendiente / conflicto | Compatibilidad de títulos y atributos explícitos; no verificación independiente del SKU |
| motivo_identidad | texto | Evidencia o conflicto detectado |
| indicador | precio_favorable / precio_alto / sin_senal_clara / evidencia_insuficiente | Regla de precio versión precio-v1 |
| ahorro_referencia_pct | número o null | 100 × (1 − precio / mediana_base); negativo significa sobreprecio |
| contexto_referencia | minimo_multitienda / serie_vendedor / null | Alcance de la comparación histórica |
| brecha_pp | número o null | Anuncio explícito menos ahorro de consulta; sólo misma serie de vendedor y base suficiente |
| motivos | JSON lista de textos | Causas de evidencia insuficiente |
| edad_consulta_dias | entero o null | Diferencia entre fecha consultada y fecha del precio |
| tipo_vendedor | tienda / tercero / sin_confirmar | Según bandera marketplace reportada por la fuente, pendiente cotejo comercial |
| precio_total_verificado | número o null | Null si faltan cargos comprobados; nunca usar flag envio como importe |
| resumen | texto determinista | Precio, fecha, vendedor, comparación y pendientes; sin API generativa |
| condiciones_pendientes | texto | Inventario, envío, membresía y variante pendientes |
| regla_version / umbral_pct | texto / número | Versión y umbral reproducibles |

## Reglas y límites

Base del evento cerrada, ≥4 días observados en ≥21 días, misma moneda/canal y título compatible. Precio favorable si ahorro frente a mediana ≥5% y precio ≤P25; alto si sobreprecio ≥5% y precio ≥P75; resto sin señal clara. Sensibilidad al 10%. Esto es una señal provisional sobre precio publicado; no equivale a recomendación de calidad ni probabilidad de fraude.

Los paquetes se mantienen separados. Los atributos no extraídos quedan desconocidos; nunca se deducen RAM, generación o capacidad ausentes. Una coincidencia textual, incluso idéntica, requiere cotejo del SKU, condición y cargos antes de comprar. Los títulos y precios del agregador no son una confirmación de inventario por la tienda.

Isolation Forest se usa exclusivamente en QQP físico retrospectivo (entrenamiento 2024, evaluación 2025). No trasladar sus puntajes a ofertas en línea ni al evento 2026 incompleto. El indicador de consulta no entrena un clasificador con etiquetas derivadas.

## Actualización

La recolección diaria existente continúa generando gold y el contrato web anterior. Para la futura app hay que integrar la generación de `sconto-app-v1` con esa tarea y probar instalación y caducidad en el teléfono. Este notebook congela la entrega académica por revisión Git y hashes; volver a generar una edición con nuevas entradas, sin sobrescribir sus archivos congelados. No se necesita cuenta de usuario, base de datos de perfiles ni publicaciones.
