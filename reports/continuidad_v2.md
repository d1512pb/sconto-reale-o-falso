# Recolección local y alertas de Sconto v2

La tarea `Sconto v2 Piloto PROFECO Buen Fin 2026` se amplió al 1 de diciembre de 2026. Consulta los mismos 24 modelos una vez al día a las 17:00 CDMX. Windows confirmó la siguiente fecha del 15 de noviembre y `StartWhenAvailable=True`. Requiere que se inicie sesión en la PC. Una corrida recuperada registra el día real y señala los días omitidos. Cada día tiene sus propios crudos, exclusiones, precios limpios y JSON de ejecución. El precio conserva la fecha de levantamiento de PROFECO.

Se reprodujo la pasada archivada del 14 de noviembre desde crudos en una carpeta aislada. La rutina leyó 24 fichas, importó 25 consultas incluyendo la reconsulta de Lenovo y obtuvo 2,211 registros útiles y 15 exclusiones. También se comprobó la alerta para días omitidos, ejecución parcial y rezago del levantamiento. La primera corrida automática diaria está programada para el 15 de noviembre.

La bitácora de Windows queda en `logs/piloto_buen_fin_v2_<fecha>.log`. `data/operacion/v2/profeco_campana/ALERTA.md` y `ejecuciones/` muestran días faltantes, parciales o con bloqueos. La revisión de alertas funciona sin red con `python -m sconto.operacion_profeco_bf_v2 --revisar`. Los avisos quedan en la PC. La publicación de una alerta externa requiere un canal autorizado.

## Rutina posterior

`Sconto v2 Vigilancia QQP` quedó registrada cada domingo a las 12:05 CDMX desde el 22 de noviembre. Comprueba el enlace del nuevo catálogo oficial y consulta primero hasta 64 KiB y el tamaño HTTP. Si hay una versión que requiere descarga, se valida el RAR en `data/operacion/v2/publicacion_qqp/`. Un archivo válido queda como candidato para conciliación en un corte independiente. Los reportes actuales, el bruto completo anterior y las entregas congeladas siguen disponibles.

La consulta HTTP real del 14 de noviembre obtuvo `206`, con 20,772,376 bytes anunciados y los mismos primeros 64 KiB del RAR completo de 59,971,365 bytes. Devuelve un estado de revisión y conserva el archivo previo. Los validadores también leyeron 16 CSV en el RAR completo y rechazaron el RAR truncado archivado. [Catálogo oficial QQP](https://datos.profeco.gob.mx/index.php)

La consulta especial del evento se cierra el 1 de diciembre. La revisión semanal conserva el reporte de huecos hasta esa fecha. Las cotizaciones autorizadas de tiendas ingresan cuando se reciben, mediante el importador local. La programación automática online queda sujeta al alcance autorizado de una fuente y a su vigencia real.
