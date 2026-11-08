# Salida del notebook y proyección de la app

El notebook 03 produce `entrega_sconto.zip`: dataset limpio completo en Parquet y CSV.gz, auditoría, diccionario y `datos_app.zip`. El segundo ZIP contiene el catálogo de consulta de 200 productos, sus series y ofertas, resultados históricos de minería, SQLite, JSON y manifiesto. La [app instalable](https://d1512pb.github.io/sconto-reale-o-falso/) consume una proyección verificada de estas mismas tablas.

## Flujo de consulta

1. Cargar `manifest.json` y comprobar hashes. Mostrar `fecha_corte`.
2. Buscar nombre/modelo en `catalogo_consulta`; el índice TF-IDF exportado permite recuperar candidatos. Normalizar mayúsculas, acentos y espacios. No unir registros por similitud. Respetar conflictos de variante y pedir elección cuando el nombre sea ambiguo.
3. Filtrar `ofertas_evaluadas` por el ID seleccionado. Mostrar plataforma, vendedor, precio publicado, fecha, condiciones y enlace. Priorizar ofertas recientes con título compatible, luego las pendientes y antiguas; las contradictorias van al final. Dentro de cada grupo, ordenar por precio publicado. El orden no certifica total, disponibilidad ni condición equivalente.
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
| `app_feed.json` | Catálogo, ofertas evaluadas, series, referencias e historial diario; versión, corte y reglas |
| `indice_busqueda.json` | Vocabulario, IDF y matriz CSR; TF-IDF char_wb 3–5, norma l2, coseno mínimo 0.15; ancla de palabra exacta (≥3 caracteres) o difflib ≥0.85 (≥4); excluir contradicciones |
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

La recolección diaria genera gold y `sconto.mart` usa `preparar_aplicacion` para obtener las ofertas evaluadas y el índice del notebook. Desde el 8 de noviembre, el ETL diario amplía la consulta a todos los productos nativos de Preciómetro con precios en línea ya recolectados (1,493 en el corte probado). No amplía la lista de 200 peticiones diarias ni mezcla las sucursales físicas de QQP. `--solo-seleccion` conserva el alcance anterior. La entrega académica congelada mantiene 200 productos y los archivos internos `app_feed.json` / `indice_busqueda.json` conservan su formato.

La proyección para navegador ahora es **sconto-app-v2**:

- `snapshot.json` identifica por SHA-256 el índice `datos.<hash>.json`.
- El índice incluye catálogo, búsqueda, categorías, ventanas, procedencia y resúmenes de ofertas. `series`, `referencias` y `precios_diarios` quedan vacíos; `detalles` relaciona cada producto con su archivo y SHA-256.
- `producto.<hash>.json` usa **sconto-producto-v1**: producto, corte, ofertas completas, serie de mínimos multitienda, referencias del evento actual y puntos diarios. Se descarga al abrir la ficha. Los historiales por vendedor permanecen completos en las tablas Parquet y SQLite del ETL.
- El catálogo añade `categoria_app`, `categoria_app_nombre`, `en_seguimiento_diario` y `ultima_fecha_observada`. La categoría organiza la consulta; nunca determina una coincidencia de SKU.
- Cada respuesta se verifica por hash; las fichas deben coincidir además con el producto y corte solicitado. Se conserva el último catálogo válido y hasta 40 fichas descargadas. Una ficha de otro corte no se usa para suplir datos faltantes. Sin conexión, los productos no guardados muestran un aviso y permiten volver al catálogo.

La app también puede leer una copia anterior **sconto-app-v1**. Los recursos de interfaz se versionan por su contenido en el service worker. Las variantes explícitas de iPhone, Galaxy y iPad se contrastan tanto en Python como en JavaScript; títulos incompletos de las categorías incorporadas quedan pendientes, aunque coincidan en capacidad.

La búsqueda en JavaScript reproduce el TF-IDF y los filtros de variantes de Python; se contrasta automáticamente contra el buscador del notebook. La interfaz recalcula la vigencia en CDMX al consultar y al cambiar de día. La instalación y las condiciones reales de almacenamiento en Android/iPhone siguen pendientes de prueba física. Este notebook congela la entrega académica por revisión Git y hashes; cada actualización diaria genera una edición nueva sin sobrescribirla. No se necesita cuenta de usuario, base de datos de perfiles ni publicaciones.
