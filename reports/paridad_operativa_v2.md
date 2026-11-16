# Decisiones operativas de Sconto v2

La API y el cuaderno operativo comparten `sconto.consulta_v2.Consulta` y `sconto.decisiones_v2`. El cuaderno 04 conserva su ruta histórica y su versión de reglas. El cuaderno 05 usa copias transaccionales SQLite, registra sus hashes, el instante de evaluación con huso, la versión de regla y los motivos de abstención. Para comparar una repetición con la API hay que fijar las mismas entradas, hora y visibilidad. Los registros privados requieren custodia privada.

```powershell
python notebooks/crear_notebook_04.py --modo operativo
```

El cuaderno generado es `notebooks/05_Sconto_Operativo_v2.ipynb`. La primera celda permite indicar el archivo `intradia.sqlite3`, el catálogo, los productos y el instante de evaluación. La consulta pública corresponde a `PRIVADAS = False`. La selección automática omite productos cuyas ofertas están ocultas.

## Referencia preevento

La regla `precio-v2-provisional` exige cuatro días comparables en un lapso de al menos 21 días dentro de la base fijada en el catálogo. Cada día recibe el mismo peso. Los costos deben corresponder al mismo anuncio, variante, vendedor, moneda y contexto. El 5%, los cuartiles y la vigencia de dos horas siguen provisionales. Las capturas nuevas de noviembre no pueden cubrir retrospectivamente la base del evento 2026.

La salida `cobertura_previa` identifica la ventana, los días observados, su amplitud y si alcanzan los mínimos. Cuenta por separado las ofertas observadas con historia suficiente y las ofertas evaluables en el momento de la prueba. Una variante anterior archivada puede tener historia suficiente y resultar vencida. Con historia ausente, la decisión devuelve `evidencia_insuficiente`, `historia_insuficiente` y ahorro nulo.

## Comparación de totales actuales

`GET /v1/products/{producto_id}/comparacion-actual` y el cuaderno operativo calculan la misma tabla de totales actuales, por separado de la decisión histórica. Se requieren dos anuncios con evidencia directa vigente, identidad confirmada, stock, costo total en MXN y coincidencia de GTIN verificado, condición y contexto de entrega. Los anuncios con promoción condicionada o no aclarada quedan fuera. El campo `diferencia_vs_menor` mide pesos sobre el menor total de esa consulta. Con menos de dos ofertas comparables, la respuesta devuelve `evidencia_insuficiente`.

Las cotizaciones autorizadas pueden incluir el campo opcional `gtin` cuando el soporte identifica el código de barras del producto. El importador verifica el dígito de control y normaliza el código. Mantenerlo vacío cuando el proveedor no lo proporciona o la variante no está identificada. Esta comparación no cambia las ventanas ni los mínimos de la regla histórica.

## Pruebas

Las pruebas sintéticas fijan la misma hora y entradas para ambas rutas. Comparan las ofertas completas, los resultados históricos y los grupos de cotizaciones contemporáneas. Incluyen vencimiento, costo desconocido, cambio de variante, falta de historia y exclusión de una promoción condicionada. Son pruebas de software.

Pasaron 40 pruebas dirigidas. Se ejecutó también el cuaderno 05 en un kernel Jupyter local nuevo con el almacén real y el reloj fijado al 15 de noviembre de 2026 a las 17:00 CDMX. La salida y la API local coincidieron exactamente. La vista pública devolvió 0 ofertas online publicables. La revisión privada mostró 1 ficha archivada y 0 ofertas evaluables. Para esa ficha hubo 0 días comparables en la base del 14 de septiembre al 29 de octubre. La decisión fue `evidencia_insuficiente` y la comparación actual devolvió el mismo estado. La ficha archivada sigue sin validar una oferta online actual.

La copia intradía usada en la prueba tiene SHA-256 `04ba50194c4fde4271da1c466221a283cbdfe9a648cfe4fd575eb53043cc1af8`. El JSON con la decisión y el cuaderno ejecutado quedan en `data/operacion/v2/notebook_05_revision_20261116_004321/`, bajo custodia local. La repetición del 16 de noviembre conservó las mismas cifras.
