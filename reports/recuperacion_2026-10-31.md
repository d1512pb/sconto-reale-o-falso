# Revisión y recuperación · 31 de octubre de 2026

## Diagnóstico verificado

- **El colector de GitHub estaba vivo.** Las once corridas programadas del 21 al 31 de octubre terminaron bien.
  Cada archivo de metadatos de esos días contiene las 200 fichas de la lista fija; no se necesitó volver a pedirlas.
- La copia local de trabajo seguía en el snapshot del 21 porque no se había sincronizado.
- **La tarea de Windows estaba averiada desde el 22 de octubre.** Dos entornos añadieron archivos del mismo día
  y Git quedó con conflictos `add/add` en parquet y evidencias. Las siguientes ejecuciones fallaban antes de capturar.
- Se conservó intacta la copia averiada `data/operacion/repo/`, incluidos su historial, conflictos y capturas pendientes.

## Reparación aplicada y comprobada

- Nueva copia operativa `data/operacion/repo_servicio/`; mismo workspace privado de datos, sin borrar la evidencia anterior.
- Las capturas locales usan `*.local.parquet` y las proyecciones públicas usan `preciometro/local/`.
  No sobrescriben archivos cloud. Las tablas anuales de QQP conservan su convención de reemplazo anual.
- Recuperadas las capturas reales pendientes del 22 de octubre y realizada una nueva captura Liverpool el 31.
- Si falla la sincronización, el servicio intenta conservar la captura local en vez de abortar antes de recolectar.
- La PC publica particiones y solicita una corrida idempotente. **Sólo GitHub actualiza los ZIP diarios y `actual`**:
  se elimina la carrera que permitía reemplazarlos con un paquete local atrasado.
- Tarea Windows verificada con **`LastTaskResult = 0`**, finalizada a las 21:26 CDMX.
  Disparadores: 12:30, 20:30 y al iniciar sesión. El respaldo PM/ML se permite desde las 20:00 si falta éxito del día.
- Publicación cloud de recuperación **exitosa**:
  [corrida 41269172981](https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/41269172981).
- Repetición final **exitosa y sin nuevas consultas a tiendas**:
  [corrida 41269961768](https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/41269961768).
  GitHub aprobó 33 pruebas de infraestructura y 11 de dataset/exportación; omitió una prueba que requiere la
  evidencia privada local del Avance 1, sí aprobada dentro de las 244 pruebas locales.
- Se agregó alerta por más de dos días sin confirmación local, aunque la tarea no alcance a registrar un error.

## Datos listos para la siguiente fase

- **676,797 observaciones**, nueve tablas, cero filas excluidas en gold y cero errores en la auditoría del paquete.
- **244 pruebas locales aprobadas** después de sincronizar las capturas recuperadas y el paquete publicado.
- QQP CDMX: 409,138 filas históricas de 2018–2026; última fecha disponible 31 de agosto de 2026.
- Preciómetro: 248,736 observaciones históricas y 18,809 ofertas; ambas fuentes llegan al 31 de octubre.
- Liverpool: cuatro capturas reales, 20, 21, 22 y 31 de octubre. Wayback: 109 observaciones históricas.
  Se conserva una ficha piloto anterior de Amazon; la captura directa sigue desactivada.
- Avance 1 reproducido: **39,363 observaciones, 298 series con ahorro y 93 con alza**.
- El snapshot fijo, su SHA-256 y su URL están en `snapshot_analisis_2026-10-31.json`.
  Descargar esa versión para congelar el análisis; `actual` seguirá cambiando con las siguientes corridas.
- `cobertura_por_fuente_y_dia.csv` y `preparacion_siguiente_fase.json` se generan sin red con
  `python -m sconto.auditar_recoleccion`. El ciclo diario los actualiza automáticamente.

## Límites que no deben confundirse con reparación

- **No se inventaron precios de Liverpool del 23 al 30 de octubre**: siguen como faltantes. Un SKU no cubre su catálogo.
- El 31 de octubre el [índice oficial QQP](https://datos.profeco.gob.mx/datos_abiertos/qqp.php) y el enlace oficial
  guardado para el archivo 2026 respondieron **HTTP 404**. También falló la revisión del índice desde el colector.
  Se preservó el histórico, se añadió comprobación del enlace del manifiesto si el índice desaparece y se limita
  a un intento de revisión diario cuando falla. No se declaró actualizado QQP 2026 ni se recurrió a servicios de pago.
- Mercado Libre directo continúa sin autorización/token ni modelos confirmados. Amazon y ML del agregador son
  evidencia indirecta; no una verificación de sus APIs. No se registró ninguna app ni se solicitaron credenciales nuevas.
- La muestra está disponible para explorar históricos, cobertura y evolución diaria; no para concluir todavía
  sobre los descuentos del evento BF2026, que aún no se observa. Revisar variantes y suficiencia por serie.
- El paquete y sus celdas de carga se verifican localmente; no se afirma una ejecución en los servidores de Colab.
