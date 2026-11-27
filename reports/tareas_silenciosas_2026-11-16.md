# Tareas locales sin ventanas — 16 de noviembre de 2026

Se revisaron las cinco tareas de Sconto registradas en Windows. La revisión del buzón corría cada 15 minutos con PowerShell en la sesión interactiva. Aunque usaba WindowStyle Hidden, el arranque de una consola podía producir el destello que reportó Daniel.

El buzón privado estaba vacío: cero JSON y cero soportes. Los últimos registros del 16 de noviembre indicaban cero entradas nuevas, repetidas, pendientes o rechazadas. No había trabajo que justificara revisarlo cada 15 minutos.

## Estado aplicado

| Tarea | Estado | Motivo |
|---|---|---|
| Sconto v2 Buzon de cotizaciones autorizadas | Desactivada | No hay cotizaciones que importar ni fuente online que lo alimente |
| Sconto v2 Reactivar buzon 20261115_221210 | Desactivada | Impedir que la tarea antigua revierta la decisión |
| Sconto recoleccion diaria | Activa, sin consola | Se conserva la operación existente y su horario |
| Sconto v2 Piloto PROFECO Buen Fin 2026 | Activa, sin consola | Conserva la consulta diaria de las 17:00 y el fin de campaña del 1 de diciembre |
| Sconto v2 Vigilancia QQP | Activa, sin consola | Conserva la revisión dominical de las 12:05 |

Las cuatro acciones principales usan ahora wscript.exe y scripts/ejecutar_tarea_sin_ventana.vbs. El lanzador sólo admite los modos diario, profeco, qqp, buzon y comprobar; inicia el script fijo correspondiente oculto desde el arranque, espera su término y devuelve su código de salida. No se añadieron procesos residentes.

Se actualizaron también los scripts de registro de la tarea diaria y de vigilancia QQP para que una reinstalación no restaure la apertura de PowerShell visible.

## Verificación y respaldo

La sintaxis de los scripts PowerShell pasó la comprobación. El lanzador completó una prueba sin red con código de salida 0 en el contexto Windows permitido. La consulta inicial del Programador requirió acceso fuera del entorno restringido; se realizó antes de modificar las tareas.

Se comprobaron los cinco estados finales y la conservación de todos los horarios y usuarios. Se guardaron las cinco definiciones originales y el estado aplicado en:
data/operacion/v2/tareas_silenciosas/20261116T191329271Z/

No se ejecutó una nueva captura de tiendas para probar el lanzador. No se borraron datos ni tareas.

## Dependencia de la computadora

La campaña PROFECO y la vigilancia QQP siguen ejecutándose en esta PC con la sesión de Daniel iniciada. Apagar la computadora impide la ejecución a la hora prevista; la configuración conserva la recuperación de una hora omitida. No hace falta mantener terminal, Colab ni app abiertos.

Fly sigue pendiente. Tener la API alojada no sustituirá automáticamente estos colectores: hay que migrar o sincronizar su operación y verificarla antes de retirar las tareas locales.

## Instrucción para el siguiente chat

Mantén el buzón y su reactivador desactivados mientras no haya entregas reales que procesar. Si se vuelve necesario, confirma primero el flujo real y conserva el lanzador sin ventana; no lo reactives sólo por terminar de desplegar una API.

Usa el mismo lanzador para cualquier tarea local nueva de Sconto. Prioriza desplegar y verificar el flujo completo antes de eliminar la dependencia de la PC. Evita registrar otra tarea que abra directamente PowerShell o CMD en la sesión del usuario.

