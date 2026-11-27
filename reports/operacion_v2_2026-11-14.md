# Sconto v2 · operación al 14 de noviembre de 2026

## Capturas y continuidad

- El piloto conserva las 25 consultas HTTP exitosas de la fuente especial de PROFECO y 17 capturas archivadas de una ficha de Liverpool. SQLite mantiene los historiales diarios de PROFECO separados de las comprobaciones horarias de la ficha web.
- Las dos consultas oficiales del Lenovo 82XQ0009LM fueron a las 14:17:51 y 14:28:12 CDMX. Las dos respuestas tienen su propio identificador y hora de consulta. Sus 104 precios fechados coincidieron. Se conservan 2,211 precios diarios únicos del piloto inicial, incluidos 367 del 13 de noviembre.
- Se verificaron la integridad y las claves foráneas de SQLite, los hashes de crudos y la idempotencia de la importación. La base local `data/operacion/v2/intradia/intradia.sqlite3` refiere a los crudos privados existentes. Una copia de la base por sí sola no conserva esos cuerpos.
- Se registró la tarea `Sconto v2 Piloto PROFECO Buen Fin 2026`, a las 17:00 CDMX del 15 al 18 de noviembre. Depende de la sesión iniciada en la PC. Usa la lista fija de 24 productos, separa cada día y conserva los errores. Se verificaron el disparador y la salida del programa fuera del intervalo. La primera ejecución programada queda pendiente.

## Operación existente y fases pendientes

- La tarea diaria de Windows reportó salida 0 el 14 de noviembre a las 12:30 CDMX. La corrida despachada por la tarea completó recolección, analítica y GitHub Pages. [Corrida de GitHub Actions](https://github.com/d1512pb/sconto-reale-o-falso/actions/runs/43627981436)
- El piloto v2 consulta únicamente la fuente especial de PROFECO. Los términos de las fuentes minoristas evaluadas impidieron ampliar la automatización directa. La operación diaria anterior conserva su programación. Sus condiciones de acceso están registradas en `fuentes_v2.csv`.
- Las capturas oficiales preservan fechas de levantamiento. La frecuencia intradía de precios en tienda sigue sin validarse. La API y el APK v2 quedan pendientes. La sesión de Fly.io tampoco estaba autenticada y el consumo de la organización quedó sin verificar.
- El análisis de 2026 cubre los primeros días observados. La ventana del evento cierra el 17 de noviembre y la posterior el 1 de diciembre. La evaluación requiere además que haya observaciones en cada población analizada.
