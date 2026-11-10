# Prueba física de Sconto · 9 de noviembre de 2026

Dispositivo: POCO modelo 2412DPC0AG, Android 16. APK `mx.sconto.app`, versión 1.0.0 (1), firmado para pruebas. Tamaño: 870,449 bytes. SHA-256: `59bc4dd712ad97bf7c32c1e83e62f067fb50dd96db59a9ffb46bc27779ffe2f8`.

La instalación inicial del 8 de noviembre requirió que el usuario autorizara depuración e instalación USB. Se instaló correctamente después de esa autorización. La revisión física se retomó el 9 de noviembre. No se usó un emulador para los casos descritos.

## Verificaciones realizadas

| Caso | Resultado observado |
|---|---|
| Compilación y firma | APK generado; firma v2 verificada |
| Pruebas nativas | 3 aprobadas, sin fallos |
| Revisión estática Android | 0 errores; 5 advertencias no bloqueantes (JavaScript necesario, respaldo, icono y versión disponible de Gradle) |
| Permisos instalados | Sólo INTERNET; sin cámara, ubicación, contactos o almacenamiento compartido |
| Apertura física y reapertura al día siguiente | Correctas; catálogo de 1,493 productos, corte del 8 de noviembre |
| Disposición y teclado | Barras del sistema respetadas, teclado visible, botón Buscar accesible; se oculta al consultar resultados |
| Búsqueda de `ipad` | 89 resultados; abre ficha del iPad Pro 13 M5 1 TB Plata |
| Precios antiguos | Último registro del 16 de octubre identificado como histórico, sin indicador favorable vigente |
| Historial | Mediana $60,499, 33 fechas base y amplitud de 32 días; control cambió la fecha del 16 de octubre al 16 de agosto |
| Atrás de Android | Regresó a los resultados de iPad conservando la consulta |
| Computadoras + Sears | 14 productos; la Lenovo IdeaPad Slim 3 mostró precio en Sears de $13,499 del 8 de noviembre |
| Resumen de Sears | Mismo precio y tienda en tarjeta, resumen y oferta; 39.2% sobre la referencia multitienda; exige confirmar variante y cargos |
| Enlace de tienda | Android abrió la app Sears instalada; solicitó cámara y no se concedió. No se validó inventario ni precio final en Sears |
| Errores de proceso | Sin coincidencias de fallos fatales en los últimos 500 registros del proceso de Sconto consultados tras estas pruebas |

El pegado de texto desde la herramienta de visualización estaba desactivado para evitar sincronizar portapapeles personales. La escritura con teclas y el teclado del teléfono funcionaron; no se atribuyó ese comportamiento de la herramienta a la app.

## Pendientes

Prueba de reapertura sin red y ficha no descargada, y revisión humana del catálogo y de las variantes. El APK sigue siendo una edición de pruebas; no es una publicación en Play Store ni una certificación de las ofertas de las tiendas.
