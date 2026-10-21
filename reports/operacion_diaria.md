# Operación diaria · 21 de octubre de 2026

## Configuración desplegada

- Repositorio público existente: https://github.com/d1512pb/sconto-reale-o-falso.
- GitHub Actions: una pasada diaria a las 13:17 UTC / 07:17 CDMX. Lista fija de 200 productos, ocho familias.
- Windows: tarea `Sconto recoleccion diaria`, 12:30 CDMX y al iniciar sesión; sin contraseña almacenada.
- Respaldo: copia operativa independiente en `data/operacion/`. Espera las corridas cloud activas antes de sincronizar;
  sólo intenta Preciómetro/ML si no hay éxito del día. No reintenta bloqueos del mismo entorno ese día.
- Liverpool: una URL habilitada y verificada. Amazon directo desactivado. Sears no integrado.
- QQP: revisión semanal del archivo del año en curso; no descarga de nuevo todos los históricos.
- Alertas: `ALERTA.md` y un issue de GitHub para fallos/bloqueos dos días consecutivos; no hay envío de correo propio.
- Los ZIP fechados del release `datos` congelan un snapshot; `sconto_colab_actual.zip` apunta a la última publicación.

## Verificaciones realizadas

- Suite local completa: **229 pruebas aprobadas**.
- Avance 1 reproducido: **39,363 observaciones, 298 series con ahorro y 93 con alza**, matriz idéntica.
- Primer paquete público descargado sin autenticación y verificado: **664,446 observaciones y nueve tablas**,
  56,329,755 bytes; SHA-256 y conteos coinciden. Celdas del cargador ejecutadas localmente contra la URL pública.
- Esto no demuestra una ejecución en los servidores de Colab: el notebook de Drive no fue modificado.
- Windows capturó Liverpool el 21 de octubre: una fila real con precio actual y tachado, robots permitido.
- Revisión QQP del 21 de octubre: huella del archivo 2026 sin cambios; no se inventaron observaciones nuevas.
- Corrida cloud de prueba completa: https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/39569141291.
  Al iniciar este registro seguía en ejecución; su resultado definitivo debe consultarse antes de afirmar éxito.

## Límites que siguen vigentes

- Mercado Libre no tiene autorización/token ni IDs confirmados: la API no está integrada con filas actuales.
  No se registró una app. No compartir secretos en notebooks ni en el chat.
- Amazon se observa indirectamente mediante el agregador/archivo; no equivale a una ficha actual verificada por Amazon.
- QQP 2026 llega al 31 de agosto en la versión descargada; la revisión semanal depende de que PROFECO actualice el archivo.
- Los 200 productos diarios son identidades de la fuente, no empates exactos con los modelos QQP.
  Los cruces probables requieren revisión humana de capacidad, RAM, color y generación.
- Wayback tiene 109 observaciones históricas, pero ninguna durante los días de BF2024/BF2025.
- Los crudos locales permanecen fuera del repositorio público por privacidad. Los crudos nuevos de GitHub no se publican
  ni se respaldan fuera del runner: en esta configuración son efímeros; hashes y tablas normalizadas sí quedan publicados.
  Esto limita la auditoría posterior del HTML/JSON íntegro de esas capturas cloud.
- La PC debe estar encendida, con sesión iniciada e Internet; GitHub también puede retrasar u omitir cron.
  Un día sin observación permanece faltante. La ejecución automática no garantiza cobertura suficiente de cada serie.

## Uso y diagnóstico

1. Abrir el cargador de Colab del repositorio y ejecutar sus celdas; no requiere rutas de Windows.
2. Revisar `data/estado/github.csv`, `data/estado/local.csv` y los resultados de Actions para distinguir entornos.
3. Revisar `logs/servicio_<fecha>.log` y `data/operacion/workspace/logs/` en la PC.
4. `Get-ScheduledTaskInfo -TaskName 'Sconto recoleccion diaria'`: resultado 0 = cobertura exigida completa;
   2 = faltantes; 1 = error técnico; 267009 = todavía en ejecución.
5. Para pausar sólo la PC: `Disable-ScheduledTask -TaskName 'Sconto recoleccion diaria'`.
   Para pausar cloud: Actions → Recolección diaria de precios → Disable workflow.
