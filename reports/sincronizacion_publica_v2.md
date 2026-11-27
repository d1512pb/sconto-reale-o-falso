# Sincronización de cotizaciones publicables

El buzón local sigue guardando el soporte y su permiso. La sincronización selecciona únicamente cotizaciones online con permiso de publicación. Transmite campos normalizados en lotes de hasta 16 observaciones y 32 KiB. El contenido excluye documentos, crudos, precios físicos, referencias de permiso y texto privado de promociones. Una SQLite local registra cuáles recibió cada destino.

Fly Machines autentica la transferencia por HTTPS. Una credencial `machine-exec` de la aplicación se limita mediante `--command` a este comando exacto. El comando ejecuta el receptor como usuario `sconto` y lee exclusivamente de la entrada estándar. [Alcance de credenciales de Fly](https://docs.fly.io/flyctl/cmd/fly_tokens_create_machine-exec) · [Solicitud y respuesta en el SDK oficial](https://github.com/superfly/fly-go/blob/main/machine_types.go#L1279)

```text
/usr/sbin/runuser -u sconto -- /usr/local/bin/python -m sconto.sincronizar_publico_v2 recibir
```

Una vez desplegada la imagen actualizada y confirmada la máquina, el operador configura `SCONTO_SYNC_FLY_APP` y `SCONTO_SYNC_FLY_MAQUINA` para activar el envío en la tarea actual del buzón. `SCONTO_SYNC_FLY_TOKEN` debe quedar en el entorno privado de la tarea. Sale por HTTPS sólo como credencial de Fly y queda fuera de argumentos, archivo SQLite y bitácora. La aplicación web pública sirve consultas de lectura. [Autenticación de Machines API](https://docs.fly.io/machines/api/working-with-machines-api)

El receptor valida el esquema y tamaño, la huella, el permiso, los importes, la identidad y las fechas antes de confirmar el lote en el volumen persistente. Devuelve únicamente `sha256`, `recibidas` y `nuevas`. Si se pierde el acuse, el siguiente envío repite los datos. Una captura idéntica conserva su fila y un conflicto cancela la transacción. Después de restaurar un volumen anterior se puede repetir la sincronización con `enviar --app APP --maquina MAQUINA --reconciliar`.

La cotización puede usar `promocion_condicionada: false` cuando la ausencia de condiciones está documentada. El valor omitido o nulo conserva la incertidumbre y no habilita la comparación actual. Una condición documentada se transmite como valor verdadero sin incluir su texto privado.

Las pruebas locales usaron un almacén temporal denominado `sintetico_no_publicar` y ninguna credencial. El proceso remitente invocó al receptor por entrada estándar y una instancia de la API leyó la cotización sintética en otro proceso. También se comprobaron el reintento con un acuse perdido y el rechazo de contenido privado, un punto físico, una huella alterada y un lote fuera del límite. Un conflicto después de la primera inserción revirtió el lote entero. Pasaron 49 pruebas de API, decisiones y alimentación.

El comando exacto del receptor se ejecutó dos veces como `sconto` en Docker local sin red, en dos contenedores que compartían un volumen temporal. Los dos acuses informaron una fila recibida y conservaron la huella `2ed6f7be89942aea0876355afe35ebab221ffa066b098e3051b01f44d6cd8003`. Las inserciones nuevas fueron una en la primera ejecución y cero en la segunda. El volumen sintético se retiró al terminar. La autenticación, la recepción en un volumen Fly y el suministro real de cotizaciones quedan por comprobar cuando estén disponibles.
