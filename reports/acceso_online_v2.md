# Precios actuales de Sears y Liverpool

Revisión del 14 de noviembre de 2026. El piloto de anuncios online está pendiente de evidencia autorizada. Las consultas a PROFECO describen establecimientos físicos con resolución diaria.

## Verificación de acceso

- Los términos consultados de Sears reservan la compilación de listas de productos o precios y el uso de herramientas de extracción. La ficha indexada del Lenovo IdeaPad Slim 3 15IRU8, SKU Sears 93492513, sirve para localizar el anuncio. La hora del dato, el inventario y el costo de la compra siguen sin verificar. [Términos de Sears](https://pwa-gamma.dev.sears.com.mx/terminos-condiciones/) · [Ficha del Lenovo](https://www.sears.com.mx/producto/3636085/laptop-lenovo-ideapad-slim-3-15iru8156-fhd-intel-core-i3-8gb-ram-512gb-ssd)
- La sección 2 de la licencia de Liverpool limita la reproducción fuera del uso personal no comercial. El índice permitió corroborar el modelo Sony HT-S20R negro y su código 1097521774. Las copias indexadas devuelven distintos valores y muestran una leyenda de envío gratis, con requisitos de ubicación para consultar existencias. La antigüedad que muestra el índice corresponde a su rastreo, y la leyenda de envío sigue pendiente de cotejo con los cargos del pedido. [Licencia de Liverpool](https://assetsia.liverpool.com.mx/assets/pdf/Terminos-Legales.pdf) · [Ficha del Sony](https://www.liverpool.com.mx/tienda/pdp/barra-de-sonido-sony-ht-s20r/1097521774)
- Las integraciones de vendedores requieren una relación comercial y acceso otorgado al vendedor. La información disponible del portal no documenta un permiso de consulta y redistribución para Sconto. La vía identificada es una cotización del vendedor con permiso de uso o un archivo del proveedor con alcance documentado de uso y publicación. [Portal de proveedores de Liverpool](https://portal-servicios.liverpool.com.mx/) · [Políticas de compra de Sears](https://www.sears.com.mx/politica-compra)
- El archivo abierto de comercio electrónico de PROFECO registra proveedores y reconocimientos. Sus campos cubren nombre, sitio, sector, vigencia y servicio. El monitoreo de tiendas virtuales lista si los comercios informan el monto total y métodos de envío. Esos recursos no dan el precio, el inventario ni la hora de un SKU. [Diccionario de PROFECO](https://datos.profeco.gob.mx/docs/comercio/diccionario_dataset.csv) · [Monitoreo de tiendas virtuales](https://www.profeco.gob.mx/tiendasvirtuales/)

## Ingreso de evidencia autorizada

`python -m sconto.importar_tienda_manual_v2 cotizacion.json --evidencia soporte.pdf` registra una cotización sin visitar la tienda. El soporte y el permiso se guardan en custodia privada. SQLite conserva su huella, la hora del dato normalizada a UTC y la versión del registro. El mismo registro reimportado se reconoce por su hash. Dos horas realmente observadas se conservan como observaciones diferentes.

El JSON incluye estos campos:

- `tienda` (`sears` o `liverpool`), `url` de la ficha sin sesión, `producto_id` del catálogo Sconto y `sku` comercial.
- `variante` con el modelo y atributos verificados, `vendedor`, `condicion` (`nuevo`, `reacondicionado`, `usado` o `desconocido`), `identidad_verificada` y `disponibilidad` (`disponible`, `agotado` o `desconocido`). Identidad confirmada exige variante, vendedor y condición verificables.
- `observado_utc` como instante ISO 8601 con segundos y huso. `actualizado_por_fuente_utc` queda vacío mientras la tienda no declare esa hora.
- `precio_publicado_mxn` y, cuando se comprueben, `precio_tachado_mxn`, `envio_mxn`, `otros_cargos_mxn`, `costo_total_mxn`, `contexto_costo` y `promocion_condicionada`. El contexto usa `envio_cdmx`, `envio_estado_de_mexico`, `retiro_sucursal` o `entrega_digital`. El total exige precio más cargos por el mismo contexto. Envío desconocido y envío de $0 son valores distintos. Las promociones condicionadas no alteran el total automáticamente.
- `tipo_evidencia` (`cotizacion_del_vendedor` o `archivo_autorizado`), `referencia_permiso` y `alcance_permiso` (`interno` o `publicacion`). La segunda opción requiere autorización explícita para publicación y campos sin información de compradores, domicilios, sesiones o medios de pago.

La validación técnica se realizó con una cotización sintética. La cuenta real de registros nuevos con vendedor, variante, disponibilidad, cargos y hora comprobados es cero. Falta el permiso por escrito de la tienda o un vendedor con derecho a suministrar la cotización y permitir el uso previsto.
