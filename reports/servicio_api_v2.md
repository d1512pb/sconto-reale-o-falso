# API de consulta de Sconto v2

La API consulta SQLite con un solo proceso. La recolección y la normalización se ejecutan en la tarea local o en una importación administrativa fuera del proceso HTTP. Las rutas públicas aceptan identificadores de producto y filtros acotados. La administración del volumen requiere acceso autenticado a la máquina. No hay una ruta HTTP que reciba URLs ni credenciales de tiendas.

## Prueba local

```powershell
python -m pip install -r requirements-api.txt
python scripts/preparar_catalogo_api_v2.py data/operacion/v2/entrega_notebook/sconto_v2_consulta.sqlite data/operacion/v2/catalogo.sqlite
$env:SCONTO_API_DATOS = (Resolve-Path data/operacion/v2/intradia).Path
$env:SCONTO_API_CATALOGO = (Resolve-Path data/operacion/v2/catalogo.sqlite).Path
$env:SCONTO_API_PROFECO = '1'
$env:SCONTO_API_REVISION_PRIVADA = '1'
python -m uvicorn sconto.api_v2:app --factory --host 127.0.0.1 --port 8000
```

Los dos indicadores de revisión local permiten inspeccionar los datos conservados. Limitar esa configuración a la interfaz local. El contenedor ciñe la consulta online a cotizaciones con permiso explícito de publicación y sin campos privados. La consulta especial de PROFECO queda excluida por defecto del contenedor público. La base de catálogo sólo contiene nombres, categorías, identificadores y ventanas analíticas.

| Ruta | Resultado |
| --- | --- |
| `GET /health` | Comprobación SQLite para el balanceador |
| `GET /v1/version` y `GET /v1/status` | Versiones, fuentes habilitadas y última captura conservada |
| `GET /v1/products?q=Lenovo&canal=tienda_fisica` | Búsqueda física por sus identificadores PROFECO |
| `GET /v1/products/{id}/offers` | Ofertas online, hora de observación y hora de actualización declarada cuando existen, estado y motivos |
| `GET /v1/products/{id}/history` | Observaciones diarias del canal del producto |
| `GET /v1/products/{id}/decision` | La misma regla usada en `offers` |

La API no deduce cuándo cambió un precio a partir de la hora de descarga. Las cotizaciones autorizadas sin stock, costo total o referencia comparable retornan `evidencia_insuficiente`. Las observaciones diarias de PROFECO se leen por sucursal y no generan ofertas online.

El 14 de noviembre a las 17:31:17 CDMX una consulta real para el Lenovo 82XQ0009LM devolvió 104 observaciones diarias válidas, ocho con fecha 13 de noviembre, después de consolidar un duplicado. Desde un volumen Docker restaurado, la API devolvió las mismas 104 observaciones antes y después de reiniciar el contenedor. La ruta de ofertas online devolvió cero. Docker registró 33.77 MiB de memoria en ese punto, con límite local de 512 MiB. Esta medición local corresponde a una ficha física y a una consulta de lectura.

## Respaldo y recuperación

Generar la copia en una ubicación privada separada del volumen. El siguiente comando incluye los crudos archivados autorizados para la copia privada. El manifiesto verifica la base y cada cuerpo SHA-256. Restaurar en una carpeta nueva y comprobar consultas antes de sustituir rutas de operación.

```powershell
python -m sconto.respaldo_v2 respaldar data/operacion/v2/copia_privada.zip --raiz-crudos data/raw/piloto_p0_v2 --raiz-crudos data/operacion/workspace/data/raw/tiendas
python -m sconto.respaldo_v2 restaurar data/operacion/v2/copia_privada.zip data/operacion/v2/recuperacion
```

La copia empaquetada es privada. Conservarla en un destino privado externo antes de depender del volumen único. Las rutas se reescriben en la copia; el almacén original no cambia. Un rollback del servicio usa la imagen anterior con la base anterior restaurada en una ruta aparte. La versión de esquema introduce tablas separadas para no migrar las entregas congeladas.

## Flujo de despliegue

Comprobar en la organización personal el plan, la tarjeta registrada, el consumo existente y el costo proyectado en conjunto. La estimación en iad es US$3.69 por 512 MB, US$0.15 por 1 GB de volumen y US$0.02 por 1 GB de salida durante 30 días. El plan reserva margen manteniendo la proyección total por debajo de US$4.50. El descuento de Fly aplica a una cuenta personal elegible con factura menor de US$5. [Precios Fly](https://docs.fly.io/about/pricing) · [Condiciones del descuento](https://docs.fly.io/about/free-waiver)

Con una organización verificada, crear sólo la aplicación, un volumen `sconto_data` de 1 GB en `iad` y una máquina usando `fly deploy --ha=false` sobre `fly.toml`. Cargar un catálogo revisado y cotizaciones cuyo permiso cubra la publicación. Usar `/health`, buscar un producto y leer su historial o un caso de abstención. Verificar el consumo y reiniciar la única máquina para comprobar persistencia antes de configurar la URL HTTPS en GitHub Pages o el APK. La aplicación debe iniciar con la configuración privada apagada. [Volúmenes](https://docs.fly.io/volumes/overview)

El 14 de noviembre el CLI de Fly respondió que no tenía token de acceso. Cuenta, facturación, persistencia remota y recuperación desde un respaldo externo quedan por comprobar. El contenedor y el volumen se probaron en Docker Desktop local.
