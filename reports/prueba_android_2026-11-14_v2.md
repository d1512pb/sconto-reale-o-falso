# APK 2.0.0 y consulta web de Sconto v2

El APK de distribución `Sconto-2.0.0.apk` quedó en `data/exportaciones/apk/v2/` con el manifiesto y `SHA256SUMS.txt`. Usa el paquete `mx.sconto.app`, código de versión 3 y Android 8.0 como mínimo. Conserva la firma de la edición 1.0.1. Su SHA-256 es `a9c15efee6553f1de196424d1c9853859393acddfcebfafbfd326b0f2eb78ec0`.

- La compilación release terminó correctamente. Pasaron las tres pruebas de política de navegación y lint informó cinco advertencias. El artefacto se verificó con `apksigner` y `aapt`, quedó sin depuración y con INTERNET como único permiso.
- El manifiesto del artefacto contiene la huella del certificado público y hashes del código Android. El proceso de firma usa el almacén local excluido de Git. El manifiesto y el APK no contienen contraseñas ni claves privadas.
- La pantalla inicial conserva el origen HTTPS publicado de Sconto. Las fichas online y físicas usan fragmentos de esa misma URL. La API es una consulta de la interfaz web, por lo que la publicación tiene que configurar su origen y CORS. El APK admite que la interfaz cargue sin API configurada.
- `adb devices -l` ejecutó correctamente y no listó teléfonos. La revisión del SDK no encontró un emulador configurado. La instalación y las pruebas en un celular físico quedan pendientes.

La prueba en Chrome local con un viewport Pixel 7 consultó la API en Docker. Mostró 30 precios físicos reales del Lenovo 82XQ0009LM, la página online del Sony sin comprobaciones publicables y la actualización con HTTP 200. Una respuesta HTTP 503 controlada dejó accesibles los registros históricos. Se recargó la ficha sin conexión desde la copia verificada. La prueba terminó sin errores de JavaScript. Una respuesta de prueba controlada permitió adelantar el reloj y verificar que la vista cambia de favorable a evidencia insuficiente al vencer.

Para generar una publicación con API, pasar el origen autorizado a `python -m sconto.publicar_web --api https://api.example` o asignar `SCONTO_WEB_API`. El valor debe ser un origen HTTPS. Se admite `/` para alojar sitio y API en el mismo origen, y loopback HTTP para una prueba local.

[Firma de aplicaciones en Android](https://developer.android.com/studio/publish/app-signing) · [Integración de páginas en WebView](https://developer.android.com/develop/ui/views/layout/webapps/webview)
