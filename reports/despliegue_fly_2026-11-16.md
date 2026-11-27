# Despliegue de Sconto en Fly

## Público y verificado

- [Salud de la API](https://sconto-v2-api.fly.dev/health) y [versión pública](https://sconto-v2-api.fly.dev/v1/version). La API sirve `sconto-api-v1`, con motor `precio-v2-provisional` y revisión `colector-nube-20261116-dcc6ca85`. La búsqueda de Lenovo devolvió productos del catálogo revisado. La consulta de la ficha de prueba devolvió evidencia insuficiente y cero ofertas online. Los precios físicos permanecen en el almacén privado.
- [Web experimental](https://d1512pb.github.io/sconto-reale-o-falso/) conectada a Fly. [Publicación de GitHub Pages](https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/43957434316) completada con recolección omitida. Se comprobó el origen autorizado en CORS, el cambio a la caché `sconto-shell-85a1c71fdc45258f` y el aviso «Sin comprobaciones online para esta selección» en el navegador.
- [Notebook 05 operativo](https://github.com/d1512pb/sconto-reale-o-falso/blob/sconto-v2-operativo/notebooks/05_Sconto_Operativo_v2.ipynb). Permanece pendiente su ejecución en un Colab alojado con paridad contra la API pública. ADB no detectó un dispositivo Android autorizado para la prueba del APK.

## Datos reales y persistencia

La organización personal tenía método de pago y US$0.00 de consumo visible en Cost Explorer en el periodo de 30 días. Se desplegó una máquina de 512 MB en Ashburn, con un volumen cifrado de 1 GB e IPv4 compartida. La proyección del escenario de 31 días y 7 GB de transferencia saliente es US$4.11 frente a un límite acordado inferior a US$4.50. [Precios de Fly](https://docs.fly.io/about/pricing)

Se sembró el catálogo revisado de 1,493 productos y los crudos oficiales archivados del 15 de noviembre mediante la red privada de Fly. El primer reinicio conservó los 2,517 precios físicos de 24 modelos, la huella lógica del historial, el catálogo y los crudos que referencia SQLite.

El 16 de noviembre hubo una consulta nueva desde Fly que terminó a las 15:13:11 CDMX. Se verificaron 24 fichas nuevas, 2,803 precios físicos de 24 modelos en el almacén y 21 exclusiones de la captura. La última fecha de precio publicada por PROFECO fue el 15 de noviembre. Se verificó la integridad de SQLite, las claves foráneas y las huellas de los crudos. El número de ofertas online evaluables sigue en cero. La huella del historial físico actualizado es `650d07c98cce9db656548f884e8fd93bf1bb9c861b7b96845ca3466141ad6ae5`.

Se recuperaron y cotejaron 26 pares oficiales de crudos y metadatos de la captura del 16. Se depositaron en la carpeta local del día, que estaba vacía, para que el turno de Windows los reutilice. Se conservaron los horarios y el lanzador `wscript.exe`. El buzón de cotizaciones y su reactivador siguen deshabilitados.

## Respaldo externo preparado

Se verificó que el bucket dedicado `sconto-v2-respaldo-d1512pb` de Tigris es privado y que la retención de 30 días aplica al prefijo diario. Se configuraron escritor y lector con permisos limitados. Las credenciales del escritor quedaron preparadas en Fly, y las de recuperación y la identidad age quedaron protegidas con DPAPI para la cuenta de Windows que realizó la preparación.

La revisión automática de ejecución rechazó aplicar las credenciales y transferir al bucket la primera copia cifrada. Indicó que el destino Tigris requiere autorización explícita para los datos privados. Ninguna copia de producción salió a Tigris. Hace falta autorizar ese destino para SQLite, el catálogo y los crudos oficiales de PROFECO y QQP, todos cifrados. La transferencia excluye el buzón, las credenciales y otros archivos privados.

Tras la autorización, comprobar el envío desde Fly, restaurar el objeto en una ubicación independiente del volumen de origen y cotejar huellas y consultas. Después habilitar la recolección automática y verificar su primer ciclo y respaldo antes de retirar las tareas locales. La verificación de QQP requiere su siguiente turno dominical. Queda pendiente disponer de una copia protegida de la identidad de recuperación que pueda usarse si la PC se pierde.

La evidencia detallada, sin publicar, está en `data/operacion/v2/fly_despliegue_20261116/`. Las pruebas locales y simuladas anteriores están separadas en el informe de migración y en el procedimiento de recuperación.
