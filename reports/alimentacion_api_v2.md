# Alimentación local de ofertas y preparación de Fly.io

El buzón privado acepta pares con el mismo folio. Un archivo JSON contiene una sola cotización normalizada y su referencia de permiso. El soporte es un PDF, PNG, JPG o TXT. El operador verifica que el permiso cubra el uso previsto antes de depositar la entrega. El JSON se escribe al final mediante un cambio de nombre para que el importador lea una entrega completa.

```powershell
python -m sconto.alimentar_api_v2 --buzon data/operacion/v2/buzon_cotizaciones_privado
python -m sconto.alimentar_api_v2 --corte-publico data/operacion/v2/revision_publicable/intradia.sqlite3
```

Cada revisión del par queda registrada por folio y huella. Un reintento conserva la captura anterior y reconoce la misma entrega. Un JSON sin soporte queda pendiente. Un conflicto con una captura existente se registra como rechazo. La API local puede consultar SQLite al confirmar la transacción de ingreso.

El Programador de tareas de Windows ejecuta `Sconto v2 Buzon de cotizaciones autorizadas` cada 15 minutos con la sesión local abierta. La comprobación del 15 de noviembre a las 15:58 CDMX terminó con estado 0, sin cotizaciones nuevas. Se verificaron con casos sintéticos la reimportación idempotente, la exclusión de cotizaciones de alcance interno y la eliminación de referencias y soporte privado de la copia pública. La proyección de los datos reales disponibles quedó con cero cotizaciones online.

El segundo comando genera un corte en un archivo nuevo. Admite únicamente registros de cotización marcados con alcance de publicación. Conserva los campos de precio, identidad, fecha, vigencia y costo que necesita la API. Las referencias de permiso, documentos, textos privados de promoción, errores de ejecución, rutas de crudos y precios físicos quedan fuera. El comando imprime un conteo y un SHA-256 para verificar cualquier traslado.

Para desplegar, aplicar el presupuesto y procedimiento de `servicio_api_v2.md`. El volumen remoto lleva un catálogo mínimo y el corte publicable. Antes de reemplazar un corte, respaldar el volumen y verificar el nuevo archivo y su hash con el servicio detenido. Después comprobar `/health`, el inventario de ofertas y su conservación tras reinicio. La carga automática en Fly depende de una cuenta habilitada y de evidencia publicable. Los documentos originales permanecen bajo custodia local.

La imagen local con motor compartido se recompiló y se verificó con un volumen poblado desde una recuperación de SQLite. `/history` devolvió los mismos 104 precios físicos antes y después del reinicio. `/offers` devolvió cero ofertas online y `/comparacion-actual` devolvió `evidencia_insuficiente`. Este recorrido verifica persistencia y separación de canales con evidencia física de PROFECO.
