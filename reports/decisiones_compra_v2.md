# Decisiones de compra online · Sconto v2

La clasificación compara el costo total en MXN de un anuncio con el historial de ese mismo anuncio, vendedor, variante, condición y contexto de entrega o retiro. El importe de cada fecha base es la mediana de sus comprobaciones. La mediana y los cuartiles de esas fechas dan el mismo peso a los días con distinta frecuencia de consulta. La referencia requiere al menos cuatro fechas en un tramo de 21 días y una ventana base cerrada.

## Estados y evidencia requerida

- **Precio favorable.** El total es al menos 5% inferior a la mediana e igual o inferior al cuartil P25. La primera condición exige una diferencia relativa mínima y la segunda ubica el total en la parte baja de la distribución empírica. El riesgo de un falso favorable es inducir una compra prematura o con un ahorro menor al presentado.
- **Precio alto.** El total es al menos 5% superior a la mediana e igual o superior al P75. Los dos criterios cuantifican diferencia y posición. Un falso alto puede hacer que se pierda una oportunidad que convenía por inventario o condiciones.
- **Sin señal clara.** Se dispone de una observación vigente y evidencia comparable, pero el total no cumple ambos criterios de alguno de los extremos. El precio puede haber variado. Los datos disponibles dejan abierta la decisión de compra.
- **Evidencia insuficiente.** Se muestran los requisitos que faltan. La oferta necesita verificación directa, SKU, vendedor, condición, disponibilidad, hora real, moneda y costo total confirmados, además de referencias para el mismo contexto de costo. Las fuentes físicas y los registros indirectos conservan sus precios y fechas para consulta. Un costo desconocido se presenta como tal, aunque el precio publicado esté disponible.

La comprobación directa conserva una vigencia provisional de dos horas desde la observación, aplicada al leer la API y al mostrar la ficha. Se trata de una decisión operativa para evitar reutilizar un precio vencido. Aún falta medirla con capturas de tienda autorizadas. La hora de descarga, la hora de observación y la actualización declarada por la fuente se muestran por separado. Un levantamiento diario de PROFECO informa la fecha del precio físico.

## Sensibilidad y límites de transferencia

Se conserva el 5% como regla de diseño provisional. Con cuatro fechas base y mediana, en 2024 se clasificaron 544 series físicas de CDMX. Del conjunto, 205 permitieron simular el costo de comprar en la última fecha previa o la primera fecha del evento. Al 5% fueron 302 favorables, 46 altos y 196 sin señal clara. Al 7% pasaron a 287, 44 y 213. Ambos umbrales dieron una pérdida media de $39.16 frente al menor precio entre esas dos fechas, con 13 decisiones que resultaron más caras. El 2% y el 3% dieron $39.20, el 10% $54.30 y el 15% $49.38. Este ejercicio tiene precios observados y una política fija de espera. Desconocemos utilidad individual, stock, cargos y costo de esperar.

En 2024, cambiar de mediana a promedio o media recortada con el 5% llevó la pérdida estimada de $39.16 a $61.15 en las 205 series simulables. Los cuantiles se mantuvieron fijos en ese experimento. Falta una validación independiente de P25 y P75. Se retienen como salvaguarda provisional contra clasificar como extremo un precio situado dentro de la distribución usual.

Con dos, tres, cuatro y cinco fechas base, la cobertura descriptiva de 2024 fue 755, 691, 544 y 347 series de 2,766. Las muestras que admiten simulación fueron 240, 229, 205 y 152. Cambiar el mínimo cambia la población. Se conserva el requisito de cuatro días y 21 días de amplitud del Avance 1. Una fecha durante el evento y dos fechas del previo corresponden a la evaluación retrospectiva de alzas, con un objetivo diferente al de una consulta actual.

Con el criterio fijado al 5%, en 2025 hubo 201 favorables, 16 altos y 81 sin señal de 298 series elegibles. La simulación de 93 series arrojó $94.69 de pérdida media al 5% y $70.27 al 7%. Se informa la diferencia sin utilizar 2025 para ajustar la regla. Faltan cohortes online comparables para estimar la pérdida de cada decisión en checkout. El árbol supervisado de bajadas conserva su evaluación de 2025 y su estado experimental. Su objetivo es predecir una bajada de mediana durante el evento.

[Tabla completa de sensibilidad](sensibilidad_umbrales.csv) · [Protocolo de la prueba anual](protocolo_modelo_v2.json)
