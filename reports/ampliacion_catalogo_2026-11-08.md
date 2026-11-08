# Ampliación del catálogo de tecnología · 8 noviembre 2026

La consulta pasa de 200 a **1,493 productos** usando las observaciones en línea ya obtenidas. No se hicieron nuevas peticiones a tiendas para esta ampliación. Se conservaron los IDs nativos y las variantes; las 231 entradas QQP del catálogo general siguen separadas como evidencia física.

## Cobertura local comprobada

Entrada: `sconto_colab_2026-11-07.zip`, copia congelada usada por el notebook 03. Salida de prueba: `data/analitica/catalogo_ampliado`; sitio: `data/analitica/catalogo_preview`. Se generaron 5,694 ofertas por producto/vendedor y 134,885 puntos de mínimo diario multitienda para las fichas. Esto no equivale a tener 5,694 ofertas vigentes.

| Categoría de consulta | Productos |
|---|---:|
| Computadoras y laptops | 215 |
| Celulares | 233 |
| Tabletas | 146 |
| Audífonos | 243 |
| Bocinas y audio | 223 |
| Pantallas | 275 |
| Proyectores | 8 |
| Cámaras y lentes | 110 |
| Streaming | 23 |
| Hogar inteligente | 17 |
| **Total** | **1,493** |

La última fecha observada es 7 de noviembre para 191 productos, 16 de octubre para 1,289 y otras fechas para 13. La lista fija de seguimiento diario conserva 200 productos. El catálogo ampliado permite consultar historia; no demuestra vigencia, inventario ni cobertura diaria para todos. Los días sin datos siguen ausentes.

Las categorías se derivan de la familia, categoría de origen y nombre. Se separan proyectores de pantallas, audífonos de otros equipos de audio y televisores de dispositivos de streaming. La clasificación sirve para navegar y no resuelve identidad de producto.

## Aplicación y datos

- Filtros de celulares, tabletas y demás categorías, con conteos. Sears y Liverpool continúan filtrando por plataforma.
- Última fecha visible en tarjetas; prioridad a ofertas recientes comparables y después a registros más recientes. Los datos antiguos no reciben indicador vigente.
- Variantes explícitas de iPhone, Galaxy y iPad se contrastan en Python y JavaScript. Una búsqueda de modelo móvil explícito exige ese modelo; por ejemplo, Galaxy Tab A9 no devuelve Galaxy Buds ni Book. Títulos incompletos de nuevas categorías quedan pendientes. La coincidencia sólo textual no verifica un SKU.
- El índice inicial pesa 8,869,075 bytes antes de compresión HTTP; la versión anterior de 200 productos ocupaba aproximadamente 9.18 MB. Las fichas separadas tienen mediana de 13,051 bytes y máximo de 46,790; sólo se descargan al consultarlas.
- Se verifican SHA-256, producto y corte. Se guarda un catálogo y hasta 40 fichas descargadas. Sin conexión sólo se abre el detalle guardado del mismo corte; el resto muestra aviso y reintento.
- El ETL diario amplía automáticamente la proyección de consulta. `--solo-seleccion` conserva el alcance de la lista diaria. El notebook 03 y su entrega académica congelada no se modificaron.

## Verificación

Pruebas automatizadas locales: **47 aprobadas, 1 deseleccionada** (Streamlit). Cubren selección con observaciones, categorías, conflictos de variante, igualdad del buscador Python/JavaScript, vigencia, integridad de exportación, caché y rechazo de fichas de otro producto/corte. La caché se probó con 42 fichas para comprobar el límite de 40.

Prueba en navegador a 390 px: navegación entre celulares y tabletas, iPhone histórico sin indicador vigente, descarga de historial y ofertas de iPad. Con el servidor detenido se reabrió la ficha guardada; una ficha no descargada mostró el aviso esperado. Al restaurar el servidor, «Volver a cargar ficha» recuperó los datos. La instalación en un teléfono físico sigue pendiente.

La prueba opcional de la antigua interfaz Streamlit quedó atascada localmente y se detuvo; se excluye de la comprobación de esta PWA. No es evidencia de funcionamiento de esa interfaz antigua.

La revisión pública detectó que la actualización podía guardar archivos de interfaz de la caché HTTP anterior. El trabajador ahora solicita recursos nuevos al instalarse y su propio contenido participa en la versión de la caché. Se añadieron pruebas de ambas regresiones: caché HTTP antigua y cambios exclusivos del trabajador.

## Publicación

La publicación del corte **8 de noviembre** contiene **1,493 productos, 5,712 ofertas registradas y 135,076 puntos históricos**. El índice ocupa 8,874,749 bytes. Tiene 191 productos con último registro del 8 de noviembre, 1,289 del 16 de octubre y 13 de otras fechas. Se verificó el SHA-256 del índice público: `8c18b2896afdf582b57ffce5b0b59f7efdaea0b32d6b0e7cff5ec0c5525bb2a5`.

El [despliegue del catálogo y buscador](https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/42502462594) completó 47 pruebas y omitió una de Streamlit. En la app pública se comprobaron los filtros de tabletas/Sears, la descarga de una ficha y la separación entre su referencia multitienda y la oferta histórica de Sears. Las cifras públicas difieren de la copia local congelada porque incluyen un día adicional de recolección.

El [despliegue final con la corrección de actualización](https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/42514552591) también terminó correctamente: **47 aprobadas, 1 omitida**. Se comprobó la actualización desde una interfaz previamente guardada: «Galaxy Tab A9» pasó de 16 candidatos que incluían productos ajenos a 3 variantes A9, sin Buds, Book ni A9+. El índice público conservó el hash y las cifras indicados. Captura local de evidencia: `data/cache/sconto_catalogo_ampliado.jpg`.
