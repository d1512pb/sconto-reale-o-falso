# Acceso online e historia comparable del Buen Fin 2026

Revisión del 15 de noviembre, hora de Ciudad de México. Se comprobó acceso y cobertura con la base operativa y el corte conciliado del 14 de noviembre. El recuento de anuncios online completos y aptos para publicar sigue en **cero**.

## Vías de acceso a anuncios actuales

- **Sears y Liverpool.** Continúan las condiciones documentadas para extracción y reutilización. Las alternativas son una cotización del vendedor con permiso de uso o un archivo acordado que identifique vendedor, variante y condiciones. El importador de cotizaciones ya admite esos registros. [Términos de Sears](https://pwa-gamma.dev.sears.com.mx/terminos-condiciones/) · [Licencia de Liverpool](https://assetsia.liverpool.com.mx/assets/pdf/Terminos-Legales.pdf)
- **Mercado Libre México.** `TokenML().configurado` dio `False`. La consulta de nombres de secretos del repositorio completó correctamente y no devolvió ninguno. La API contempla OAuth de sólo lectura y cotización de envío del comprador por código postal. Para comprobar anuncios se requiere una aplicación con acceso y un vendedor que autorice los datos pertinentes. La autorización técnica y el permiso de mostrar o conservar los datos deben cubrir el uso previsto. La cotización sólo puede verificarse para una unidad, variante, destino, perfil de comprador y modalidad concretos. Si hay costos adicionales desconocidos, el total sigue sin verificarse. [Permisos de Mercado Libre](https://developers.mercadolibre.com.mx/es_mx/permisos-funcionales) · [Costos de envío del comprador](https://developers.mercadolibre.com.mx/es_ar/api-docs-es/costos-de-envios)
- **CyberPuerta y Lenovo México.** CyberPuerta figura en la campaña `26280` de TradeTracker. La red permite consultar catálogos por API con aprobación de sitio y campaña. Lenovo acepta solicitudes a través de Impact para publicar sus catálogos. El proyecto carece de acceso confirmado a esas campañas y a los campos necesarios para el costo final por destino. [Campaña CyberPuerta](https://tradetracker.com/mx/campaigns/hardware-y-software-18/cyberpuerta-mx-26280/) · [Acceso a catálogos TradeTracker](https://tradetracker.com/mx/centro-de-formacion/para-afiliados/) · [Afiliados Lenovo México](https://www.lenovo.com/mx/es/afiliados/)
- **DD Tech.** `robots.txt` respondió HTTP 200 y permitía la ruta consultada. Una única petición directa identificada para el Logitech H390 blanco, MPN `981-001285`, devolvió **HTTP 403** a las **15:51:01 CDMX**. Se detuvo la comprobación de ese comercio. La copia indexada de la ficha remite al carrito para conocer el envío, de modo que aporta un candidato, sin comprobar el precio vigente ni el costo final. [Ficha pública](https://ddtech.mx/producto/audifonos-con-microfono-logitech-h390-alambrico-1-9-metros-usb-blanco-981-001285?id=15006) · [Condiciones de compra DD Tech](https://ddtech.mx/terminos_y_condiciones)

## Cobertura anterior al evento

La ventana base es del 14 de septiembre al 29 de octubre. La ventana previa va del 30 de octubre al 12 de noviembre. La regla exige como mínimo cuatro días de base que abarquen 21 días para el mismo anuncio y contexto de entrega, con totales y disponibilidad verificables. La edición en línea requiere vendedor y variante exactos.

| Evidencia conservada | Registros base | Registros en ventana previa | Uso comprobado |
| --- | ---: | ---: | --- |
| Precio diario del agregador | 50,941 | 2,708 | Mínimo histórico por producto. Puede cambiar de tienda o vendedor. |
| Anuncios del agregador | 12,838 | 11,474 | Precios publicados. De los 5,827 anuncios evaluados en el corte, ninguno tenía costo total o stock confirmado. |
| Corroboración directa archivada en gold | 3 | 13 | Una ficha Liverpool, Sony HT-S20R, SKU `1097521774`. El vendedor no quedó confirmado. |
| Capturas validadas de esa ficha en SQLite operativo | 2 | 13 | Mismo SKU y enlace. Las 17 capturas disponibles incluyen dos del evento y ninguna confirma stock, vendedor o total. |
| Cotizaciones autorizadas en SQLite operativo | 0 | 0 | Sin oferta completa para calcular un ahorro histórico online. |

Los universos gold y SQLite operativo se solapan. El 20 de octubre figura en gold y no en la base de capturas horarias. Los conteos reproducibles se obtienen con las consultas de abajo.

El índice CDX de Internet Archive devolvió HTTP 200 con **cero capturas HTML 200** para cada una de las dos URLs exactas consultadas en las ventanas base y previa. Se consultaron la ficha Sony de Liverpool y la Lenovo de Sears (SKU `93492513`). El resultado se limita a esas URLs, intervalo y filtros. No acredita ausencia de todas las versiones, de archivos privados del vendedor o de sus registros de checkout. [CDX de Internet Archive](https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md) · [Ficha Lenovo de Sears](https://www.sears.com.mx/producto/3636085/laptop-lenovo-ideapad-slim-3-15iru8156-fhd-intel-core-i3-8gb-ram-512gb-ssd)

El histórico de automatizaciones de Mercado Libre exige autorización y devuelve sólo cambios de precio generados por ese mecanismo para el ítem. El proveedor documenta que el resultado puede ser vacío. Si más adelante se obtienen registros originales del vendedor, sólo entrarán a la serie comparable las observaciones que acrediten fecha, SKU, vendedor, stock y costo total bajo el mismo contexto de entrega. [Historial de automatizaciones](https://developers.mercadolibre.com.mx/es_ar/descarga-de-categorias/automatizaciones-de-precios)

Se corrigió el normalizador local de Mercado Libre para conservar el inventario desconocido cuando falta el campo `available_quantity`, incluso si el anuncio está activo. El campo representa un rango en los recursos públicos y queda como señal de stock publicado. Verificar la compra requiere cotejar la variante y los costos del mismo contexto. [Ítems y búsquedas de Mercado Libre](https://developers.mercadolibre.com.mx/es_ar/gestiona-preguntas-respuestas/items-y-busquedas)

La **comparación actual** describe precios observados en un mismo momento y para las mismas condiciones de compra. El **ahorro histórico** compara el costo de un anuncio con su propia referencia válida. Si el precio actual fuese verificable y el historial siguiera incompleto, se conserva el dato actual con su fecha y la decisión mantiene `evidencia_insuficiente` por falta de referencia. El precio tachado, el mínimo agregado, los datos físicos diarios de PROFECO y el histórico online publicado quedan como contexto con procedencia visible.

## Reproducción local

Sobre `data/operacion/v2/entrega_notebook/sconto_v2_consulta.sqlite`:

```sql
SELECT o.fuente, COUNT(*) AS filas,
       SUM(o.fecha_precio BETWEEN '2026-09-14' AND '2026-10-29') AS base,
       SUM(o.fecha_precio BETWEEN '2026-10-30' AND '2026-11-12') AS previo
FROM observaciones o JOIN series s USING (serie_id)
WHERE s.canal = 'en_linea'
GROUP BY o.fuente;

SELECT COUNT(*) AS anuncios, COUNT(precio_total_verificado) AS con_total,
       COUNT(disponibilidad) AS con_disponibilidad
FROM ofertas_evaluadas;
```

Sobre `data/operacion/v2/intradia/intradia.sqlite3`:

```sql
SELECT o.fuente, COUNT(*) AS capturas, COUNT(DISTINCT o.offer_id) AS ofertas,
       COUNT(o.vendedor) AS con_vendedor, COUNT(n.disponibilidad) AS con_stock,
       COUNT(json_extract(n.condiciones_json, '$.costo_total_confirmado')) AS con_total,
       SUM(n.fecha_cdmx BETWEEN '2026-09-14' AND '2026-10-29') AS base,
       SUM(n.fecha_cdmx BETWEEN '2026-10-30' AND '2026-11-12') AS previo
FROM observaciones_intradia n JOIN ofertas o USING (offer_id)
GROUP BY o.fuente;
```

Las comprobaciones HTTP quedaron en `data/operacion/v2/acceso_online_2026-11-15/` con la hora y SHA-256 de cada respuesta. No se publicaron ni se incorporaron fichas bloqueadas al almacén de ofertas.
