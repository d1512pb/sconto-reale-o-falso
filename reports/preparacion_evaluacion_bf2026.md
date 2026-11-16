# Criterios para cerrar el Buen Fin 2026

Revisión del 16 de noviembre de 2026, hora de Ciudad de México. Los datos del piloto físico y del archivo anual de PROFECO tienen poblaciones distintas. Para validar un anuncio online se necesita evidencia vigente de su vendedor y contexto de entrega. [Fechas oficiales del evento](https://www.sat.gob.mx/minisitio/SorteoElBuenFin/tarjetahabientes.html)

## Acceso a precios online

**Anuncios completos verificados al corte: 0.** El buzón privado estaba vacío tras su ejecución exitosa más reciente y el almacén operativo no contenía cotizaciones autorizadas. La única serie online archivada tiene 17 capturas sin vendedor, stock ni total confirmado. El histórico de mínimos y el precio tachado quedan como contexto. [Auditoría de acceso e historia](acceso_online_historia_v2_2026-11-15.md)

La vía que puede usar el importador actual es **recibir una cotización o un archivo autorizado de Sears o Liverpool**. Debe quedar documentado el alcance de uso y publicación. Para comparar precios se necesita un anuncio con SKU y variante, vendedor, condición, fecha y hora de observación, disponibilidad, moneda y total para el mismo destino, cantidad y modalidad de entrega. Los cargos deben venir desglosados, junto con las condiciones del descuento. Conservar cualquier soporte identificable en el buzón privado. La API pública sólo puede recibir la proyección revisada. [Entrada de cotizaciones](acceso_online_v2.md)

- **CyberPuerta en TradeTracker.** La campaña México `26280` es una vía oficial para catálogo. Requiere una cuenta aprobada, aprobación del sitio y acceso concedido por la campaña. Antes de activar la conexión, el titular debe confirmar que el alcance y los datos suministrados cubren Sconto, la visualización de precios y la retención histórica. Falta comprobar si el catálogo incluye stock por variante y el costo por destino. [Campaña CyberPuerta](https://tradetracker.com/mx/campaigns/hardware-y-software-18/cyberpuerta-mx-26280/) · [API para afiliados](https://tradetracker.com/mx/centro-de-formacion/para-afiliados/)
- **Lenovo México en Impact.** Lenovo admite publicar catálogos del programa tras aprobar la solicitud. El titular debe inscribir el sitio y, si aplica, la app en la campaña y confirmar que puede guardar los precios para análisis. El precio final y el envío se cotejan por destino en la cotización. La existencia de la campaña no confirma disponibilidad de esos campos ni acceso del proyecto. [Programa Lenovo México](https://www.lenovo.com/mx/es/afiliados/) · [Condiciones de venta y envío](https://static.lenovo.com/mx/2023/public/junio/terminos-y-condiciones-sitio-web-lenovo-mexico.pdf)
- **Mercado Libre México.** OAuth de lectura y autorización del vendedor son requisitos técnicos. Las cláusulas 2 y 7 restringen el propósito, la divulgación y la conservación del contenido. Un token de lectura no resuelve por sí solo la exposición a visitantes públicos de Sconto ni un archivo reutilizable. Confirmar con el proveedor el permiso aplicable a ese flujo antes de activar integración y publicación. `shipping_options` ofrece una cotización para el destino, con posibles diferencias frente al precio del pedido. [Términos del programa de desarrolladores](https://developers.mercadolibre.com.mx/es-mx-terminos-y-condiciones) · [Permisos funcionales](https://developers.mercadolibre.com.mx/es_mx/permisos-funcionales) · [Envío por destino](https://developers.mercadolibre.com.mx/es_ar/api-docs-es/costos-de-envios)
- **Datos abiertos de PROFECO.** El diccionario y los metadatos de comercio electrónico respondieron HTTP 200. El conjunto listado bajo precios contiene el registro de proveedores reconocidos. Sus siete campos carecen de SKU, precio y cargo de entrega. [Catálogo público](https://datos.profeco.gob.mx/index.php) · [Diccionario oficial](https://datos.profeco.gob.mx/docs/comercio/diccionario_dataset.csv)

## Modelo retrospectivo de QQP

El reloj del evento y la publicación de datos tienen cierres independientes. Para que una serie entre a la evaluación, debe pertenecer a `qqp_cdmx / tienda_fisica / MXN`, conservar la identidad de sucursal y cumplir los mínimos del protocolo. La base del 14 de septiembre al 29 de octubre exige cuatro fechas y un tramo mínimo de 21 días. El previo va del 30 de octubre al 12 de noviembre y exige dos fechas. El resultado del 13 al 17 de noviembre exige al menos una fecha de evento por serie, después del cierre. El cálculo conjunto requiere que el archivo anual alcance el cierre del evento y que existan ambas clases observadas.

Al corte del 16 de noviembre, el paquete conciliado del 14 conserva QQP anual CDMX hasta el 31 de agosto. Hay **cero series evaluables en 2026**. El piloto oficial tiene 2,517 precios diarios, con 367 el 13 y 306 el 14, en 24 modelos por fecha del evento. La tarea de las 17:00 CDMX del 15 terminó con código 0. El piloto se reporta de forma descriptiva mientras avanza su cobertura. La ventana posterior del 18 de noviembre al 1 de diciembre es un diagnóstico separado.

Ejecutar la comprobación sobre el paquete conciliado y guardado después de que el archivo anual cambie. El siguiente comando muestra el estado actual y se puede repetir con la ruta y la fecha del corte nuevo:

```powershell
python -m sconto.evaluar_bf2026 `
  --paquete data/operacion/v2/sconto_colab_2026-11-14.zip `
  --corte 2026-11-16 `
  --piloto-sqlite data/operacion/v2/intradia/intradia.sqlite3 `
  --entrenamiento-fijado data/operacion/v2/sconto_colab_2026-11-14.zip
```

1. Cuando la vigilancia QQP entregue un archivo completo nuevo, registrar su fuente pública, fecha de publicación y huella. Reconstruir un corte gold independiente y verificarlo antes de usarlo, conservando el histórico de entrenamiento. [Procedimiento de conciliación](conciliacion_corte_v2_2026-11-14.md)
2. Pasar el nuevo corte como `--paquete`. `--entrenamiento-fijado` conserva el ZIP del 14 de noviembre y comprueba la huella del código, las versiones de dependencias y la selección del árbol original. Las cifras de preparación se imprimen aun cuando falte evidencia para evaluar.
3. Si se cumplen los requisitos, reportar matriz de confusión, exactitud balanceada, precisión, sensibilidad y cobertura. Identificar la reconstrucción como **retrospectiva**. La tarjeta publicada conserva `fecha_emision_prospectiva: null` y el grupo 2025 permanece intacto. La evaluación de este modelo físico queda separada de la regla experimental de precios online y de su umbral provisional. [Protocolo fijado](protocolo_modelo_v2.json)
