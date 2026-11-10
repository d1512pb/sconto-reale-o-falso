# Sconto para Android

Edición académica **1.0.1**, Android 8.0 o posterior. El APK contiene la aplicación Android y carga la interfaz HTTPS de Sconto. Comparte el catálogo, las reglas y las actualizaciones de la web; no duplica la lógica de precios ni requiere una cuenta.

[Descargar APK firmado](https://github.com/d1512pb/sconto-reale-o-falso/releases/download/android-v1.0.1/Sconto-1.0.1.apk) · [Versión publicada y comprobaciones](https://github.com/d1512pb/sconto-reale-o-falso/releases/tag/android-v1.0.1)

## Instalar y compartir

1. Descargar **Sconto-1.0.1.apk** desde la versión publicada o la copia compartida en Drive.
2. Abrir el archivo en un teléfono Android. Si el sistema lo solicita, autorizar la instalación desde la aplicación que abrió el archivo. No requiere depuración USB.
3. Abrir Sconto con internet por primera vez. Buscar un producto y elegir su variante.
4. Consultar fecha, vendedor, historia y explicación de la señal antes de abrir la tienda.

Quienes instalaron la edición anterior **1.0.0-pruebas** deben desinstalarla una sola vez antes de instalar esta edición, porque cambió la firma. Esa operación elimina las fichas guardadas localmente; se vuelven a descargar. Las actualizaciones posteriores conservarán la firma de distribución. La versión 1.0.1 no es una publicación en Play Store.

Para compartir en Drive: subir únicamente el APK, habilitar lectura para las personas elegidas y compartir ese enlace. Para un QR público se puede usar el enlace de la versión en GitHub, que incluye las instrucciones y el archivo. No compartir la carpeta privada de firma.

## Funcionamiento y datos

El APK sólo solicita **INTERNET**. No usa cámara, micrófono, ubicación, contactos ni almacenamiento compartido. No incluye perfiles, anuncios ni analítica de búsquedas. Los enlaces de tiendas se abren en el navegador o en su app asociada por Android; esos servicios tienen sus propios permisos y condiciones.

El catálogo tiene información histórica y ofertas fechadas, no cotizaciones garantizadas. La app identifica evidencia insuficiente y deja de presentar como vigente una captura de más de un día. La web guarda el catálogo y hasta 40 fichas descargadas del mismo corte, sujeto al almacenamiento disponible. La primera apertura necesita red; la reapertura completamente sin conexión en Android sigue pendiente de verificación automatizada.

La interfaz se publica desde [web/](../web/), se prepara con [sconto.publicar_web](../src/sconto/publicar_web.py) y consume la salida de [sconto.mart](../src/sconto/mart.py). El APK no recolecta tiendas mientras se consulta.

## Compilar

Requiere **PowerShell 7**, JDK 17, Android SDK 36 y Build Tools 36.0.0. El wrapper fija Gradle 9.3.1 y AGP 9.1.1. Desde la raíz del repositorio:

~~~powershell
# Sólo al crear una firma propia para una nueva distribución:
./android/crear-firma.ps1

# Reutiliza la firma existente:
./android/build-apk.ps1

# Pruebas de desarrollo, sin firma privada:
./android/build-apk.ps1 -Variant debug
~~~

Para un SDK fuera de la ruta habitual, añadir -SdkPath 'RUTA/Android/Sdk'. El script compila, ejecuta pruebas y lint, firma y verifica el APK. Rechaza una salida release depurable o con permisos diferentes de INTERNET. Exporta a data/exportaciones/apk/ el APK, manifest.json y SHA256SUMS.txt. El manifiesto incluye huellas de las fuentes Android para asociar el binario con su código.

La firma se guarda en data/operacion/firma-android/, excluida de Git. La contraseña queda cifrada con DPAPI para este usuario y equipo. Conservar esta carpeta y preparar una copia privada recuperable antes de migrar de equipo: el archivo cifrado no se puede trasladar sin más a otro usuario o PC. No regenerar la clave para publicar actualizaciones. Otro colaborador puede compilar con su propia firma, pero ese APK no actualizará la instalación oficial.

GitHub Actions compila la variante release sin firmar, ejecuta pruebas y lint y conserva los reportes. La firma oficial y el APK distribuible se generan localmente. No se publica el APK sin firma como instalador.

## Evidencia de revisión

- [Pruebas físicas del 9 de noviembre](../reports/prueba_android_2026-11-09.md).
- [Publicación Android del 10 de noviembre](../reports/publicacion_android_2026-11-10.md).
- [Guía de revisión del proyecto](../REVISION_PROYECTO.md).

La edición de distribución desactiva la depuración de Android y WebView. Se rechazan archivos locales, contenido mixto y enlaces ejecutables; no se instala un puente JavaScript nativo. Referencias: [firma Android](https://developer.android.com/studio/publish/app-signing), [verificación de APK](https://developer.android.com/tools/apksigner) y [WebView](https://developer.android.com/develop/ui/views/layout/webapps/webview).
