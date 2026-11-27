# Respaldo externo y recuperación de Sconto

El trabajo diario puede copiar un almacén autorizado de Fly a un bucket privado Tigris. El código usa el endpoint S3 HTTPS oficial. Cada ejecución crea un objeto de `sconto-v2/v1/` con fecha UTC y SHA-256 del cifrado. El almacenamiento recibe sólo el archivo cifrado con age X25519. `If-None-Match: *` impide sobrescribir una versión y la operación confirma tamaño y metadatos con HEAD antes de reportar éxito. [Tigris](https://www.tigrisdata.com/features/) · [Creación condicional S3](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html) · [age](https://github.com/FiloSottile/age)

## Contenido y acceso

La copia SQLite usa la API de respaldo de SQLite y guarda crudos referidos por sus hashes. Incluye respuestas y metadatos de la consulta oficial dentro de `profeco/raw/YYYY-MM-DD`, las bitácoras y alertas de esa operación, y los JSON de seguimiento QQP cuando existen. La proyección SQLite del catálogo puede adjuntarse con `--catalogo`. Cada RAR aceptado de QQP conserva el recibo de validación en el respaldo diario y sus bytes cifrados en un objeto de `sconto-v2/qqp-v1/` por SHA-256 del archivo original. Los RAR rechazados y las exportaciones derivadas quedan fuera. Las credenciales, llaves de recuperación y el buzón privado de cotizaciones se mantienen fuera del volumen autorizado y del respaldo.

Hace falta `age` en PATH y `pip install -r requirements-respaldo.txt` para las operaciones S3. Configurar en Fly sólo el nombre del bucket, un rol con `PutObject` y `GetObject` sobre ambos prefijos, `ListBucket` restringido a `sconto-v2/qqp-v1/` y el destinatario público de age. Los nombres de variables son `SCONTO_BACKUP_BUCKET`, `SCONTO_BACKUP_ACCESS_KEY_ID`, `SCONTO_BACKUP_SECRET_ACCESS_KEY` y `SCONTO_BACKUP_AGE_RECIPIENT`. La identidad privada que genera `age-keygen` se conserva fuera de Fly. Para recuperar se usa otra credencial con `ListBucket` restringido a `sconto-v2/v1/` y `GetObject` sobre ambos prefijos. Si se rota la llave de cifrado, conservar también las identidades anteriores dentro del archivo privado de recuperación mientras existan objetos cifrados para ellas. [Permisos por prefijo en Tigris](https://www.tigrisdata.com/features/)

## Presupuesto y retención

El límite es de 64 MiB por objeto diario. Un objeto diario conservado 30 días ocupa como máximo 1.875 GiB en estado estable. QQP dispone de 251 MiB por objeto cifrado y un máximo de 1 GiB para su prefijo. El total proyectado de estos respaldos es de hasta 2.875 GiB, condicionado a una copia diaria y a aplicar la expiración de 30 días únicamente a `sconto-v2/v1/`. Los objetos QQP conservan sus referencias desde los respaldos diarios y no se vencen automáticamente. Si se agota su cuota, la tarea reporta un fallo sin borrar archivos ni continuar con una copia incompleta. Revisar el uso agregado de la cuenta y la salida de datos de Fly. La retención de objetos borrados y el versionado del proveedor pueden elevar el almacenamiento facturable. Conservar una copia de cierre de campaña verificada antes de que venza. [Precios Tigris](https://www.tigrisdata.com/pricing/) · [Precios Fly](https://fly.io/docs/about/pricing/)

## Ensayo de corte y recuperación

1. Con el recolector en pausa, preparar la copia de un volumen autorizado. Mantener la consulta pública y la recolección local durante la migración, asignando un único lanzador por intervalo de consulta.
2. Enviar desde Fly y registrar la clave devuelta. Un acuse confirma el objeto cifrado. La recuperación se comprueba en el paso siguiente.

   ```sh
   python -m sconto.respaldo_nube_v2 enviar --origen /data/intradia --catalogo /data/catalogo.sqlite
   ```

3. Desde una ubicación de recuperación independiente, listar con una credencial separada y recuperar la clave exacta en un destino nuevo.

   ```sh
   python -m sconto.respaldo_nube_v2 listar
   python -m sconto.respaldo_nube_v2 recuperar "$CLAVE" "$DIRECTORIO_NUEVO" --identidad "$ARCHIVO_PRIVADO_AGE"
   ```

4. La recuperación comprueba SHA-256 del objeto, autenticación age, SHA-256 de cada archivo, integridad y claves foráneas de SQLite, y el contenido de cada crudo referenciado. Descarga y verifica también todos los RAR QQP asociados antes de instalar la carpeta nueva. Iniciar la API de prueba con `SCONTO_API_DATOS` apuntando al directorio recuperado y `SCONTO_API_CATALOGO` a su `catalogo.sqlite`. Comparar estado, inventario, fechas y precios con la base anterior. Confirmar que las suspensiones y las bitácoras siguen disponibles.
5. Pasar la tarea a Fly cuando se observe una captura programada nueva y se haya descargado y recuperado su copia externa. Conservar el almacén local anterior como respaldo histórico. Si falla, mantener el lanzador local de recolección y corregir la configuración o los permisos.

Para un ensayo sin servicios externos se puede sustituir el envío por `crear ARCHIVO.age` y recuperar con `abrir ARCHIVO.age DESTINO --identidad LLAVE --sha256 SHA256`. Estas operaciones usan las mismas comprobaciones de cifrado y recuperación.

## Pruebas del 16 de noviembre

- Se recuperaron en otra carpeta local los 104 precios diarios reales de PROFECO para el Lenovo 82XQ0009LM a partir de una copia cifrada de 367,875 bytes. Coincidieron las filas SQLite, las huellas del catálogo y los seis archivos de consulta archivados. La copia salió de una verificación local anterior.
- Tres pruebas de regresión pasaron con age 1.3.2. El ensayo de transporte S3 en loopback usó almacén y RAR sintéticos. Verificó creación condicional, deduplicación del RAR por SHA-256, restauración, rechazo de contenido alterado y la ausencia de credenciales en el informe.
- Quedan pendientes un PUT en el bucket real, la recuperación desde otra ubicación fuera de la PC y el ensayo de corte una vez que se verifiquen las credenciales, las cuotas y el volumen Fly.
