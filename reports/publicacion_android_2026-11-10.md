# Publicación Android del 10 de noviembre de 2026

Versión académica 1.0.1, paquete mx.sconto.app, código de versión 2. Android mínimo 8.0 (API 26). Comparte la interfaz y los datos publicados de Sconto.

## Binario de distribución

- Archivo: Sconto-1.0.1.apk.
- Tamaño: 668,985 bytes.
- SHA-256 del APK: `74fdf714a812e57965085fc480c318f646d9eea758af77520a9228a60cef3fe4`.
- SHA-256 del certificado: `7a62c8c81137564488783efca0db60fc429c3fadbc851efcb409960e22525713`.
- Compilación release con depuración de Android y WebView desactivada.
- Firma propia local, verificada con apksigner. Las claves privadas y la contraseña cifrada están excluidas de Git.
- Único permiso solicitado: INTERNET.
- manifest.json incluye huellas de los archivos fuente Android.

La firma difiere de la edición 1.0.0-pruebas instalada durante las pruebas físicas. Para pasar de esa edición a 1.0.1 hay que desinstalarla una vez; se pierde su caché y se descarga de nuevo. Las siguientes actualizaciones deben reutilizar la firma de distribución.

## Verificación local

Compilación release completada. Las tres pruebas de navegación Java pasan mediante testDebugUnitTest; prueban la lógica compartida de rutas internas, dominios engañosos y enlaces externos. Lint de release: 0 errores y 5 advertencias. Las advertencias corresponden a JavaScript necesario para la interfaz, política de respaldo, formato y ubicación del icono y una versión disponible del complemento de Android. Se verificó que el APK no sea depurable y sólo solicite INTERNET.

Los recorridos en teléfono y la revisión humana corresponden a la versión anterior, documentada en [la prueba física](prueba_android_2026-11-09.md). La 1.0.1 mantiene las clases de interfaz y navegación; cambia versión, firma y configuración de distribución. No se afirma una nueva instalación física de este binario. La reapertura completa sin red en teléfono sigue pendiente de verificación automatizada.

## Publicación

El código completo está en android/, acompañado de la interfaz web, ETL, notebook, pruebas y documentación del repositorio. El workflow Verificar app Android compila sin la clave privada y conserva los reportes de pruebas y lint. El resultado de su ejecución se consulta en Actions; no se confunde con la comprobación local anterior.

[Descarga y notas](https://github.com/d1512pb/sconto-reale-o-falso/releases/tag/android-v1.0.1) · [Guía para revisar el proyecto](../REVISION_PROYECTO.md).

## Comprobación en GitHub Actions

La [ejecución 42859491638](https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/42859491638), sobre el commit 7e26b566c6c5dd2d49bf5b0d981c3096c406e43d, terminó correctamente: compilación release, tres pruebas de navegación y lint. El entorno se prepara explícitamente sin el paquete retirado tools. El APK firmado distribuido se construyó localmente; Actions comprueba la compilación sin recibir la clave privada.
