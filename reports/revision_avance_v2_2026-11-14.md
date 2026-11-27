# Revisión del avance de Sconto v2 y pendientes
Fecha de revisión: 14 de noviembre de 2026.
Referencia: PLAN_SCONTO_V2.md. Revisión de archivos, código, notebook ejecutado y base SQLite; no se modificó la aplicación.

## Dictamen

La parte analítica avanzó sustancialmente. La base técnica para guardar capturas con hora existe, pero todavía no hay recolección intradía directa validada ni API desplegada ni APK v2. La mejora de actualidad de precios sigue abierta. El estudio del 5% aporta sensibilidad; aún no selecciona ni valida las cuatro decisiones de la app.

## Qué se comprobó

- El notebook ejecutado tiene siete celdas de código ejecutadas sin errores registrados.
- Su manifiesto declara 690,891 observaciones limpias. La metadata del Parquet confirma ese conteo.
- Los 56 archivos del manifiesto existen y sus hashes SHA-256 coinciden; verificación repetida en esta revisión.
- SQLite contiene 25 capturas exitosas de PROFECO y 17 capturas archivadas de una ficha de tienda. Conserva 2,211 precios diarios únicos de la consulta oficial. Esas 17 capturas no son un piloto nuevo cada 30 minutos.
- El almacenamiento distingue hora de consulta y resolución diaria; los datos oficiales diarios no adquieren resolución intradía por repetir la consulta.
- El código del modelo usa 205 series de 2024 y 93 de 2025. Selecciona dentro de 2024 mediante particiones por producto y deja la elección registrada antes de evaluar 2025. El resultado se declara retrospectivo.
- Existen sensibilidad de umbrales y cobertura, referencias alternativas, matriz numérica, probabilidades, calibración e intervalos por producto.
- El informe de 2026 diferencia CDMX, Estado de México, mínimo multitienda y ofertas online. Las tres series físicas con alza y rebaja pertenecen a Edomex; la muestra de 15 series es pequeña y preliminar.

Las 107 pruebas dirigidas y siete de app son resultados informados en el avance. Esta revisión no repitió toda esa suite. Sí repitió la prueba de conciliación que falla, detallada abajo.

## Estado frente al plan

| Bloque | Estado | Qué falta |
|---|---|---|
| P0: captura y auditoría | Parcial | Acceso permitido a anuncios actuales, validación de variante/vendedor/costo y piloto intradía real |
| P1: API y Fly | Pendiente | Servicio, credenciales de despliegue, presupuesto, persistencia, respaldo y pruebas |
| P2: app v2 | Pendiente | Conectar API, vigencia, recuperación ante fallos y pruebas de APK |
| P3: reglas y modelo | Avanzado, incompleto | Decisión documentada sobre umbrales, estabilidad/utilidad y límites de transferencia a compras online |
| P4: evaluación 2026 | Preliminar | Cierre de ventanas y datos comparables; no hay evaluación del modelo en 2026 |
| P5: entrega y continuidad | Parcial | Colab independiente de archivos locales, reproducción de limpieza, GitHub, APK y operación después del 18 |

## Hallazgos que requieren acción

### 1. La frescura de precios todavía no está resuelta

El piloto programado sólo consulta PROFECO una vez al día, del 15 al 18. Las dos consultas idénticas de Lenovo prueban preservación de consultas, no detección de variaciones entre horas.

La auditoría de fuentes documenta restricciones para automatizar o redistribuir información de minoristas/agregador. Resolver acceso permitido o usar una alternativa legítima; no aumentar frecuencia ni cambiar de servidor para eludir un bloqueo. Revisar también la operación anterior que sigue activa, dado que el informe identifica restricciones en esas mismas fuentes.

Validar primero anuncios concretos de Sears/Liverpool: SKU, vendedor, condición, stock, precio final y cargos. Si una fuente sólo permite precios de referencia diarios, conservar esa función y explicarlo en la app. No presentarla como precio vigente del anuncio.

### 2. Las cuatro decisiones siguen usando una regla provisional

El árbol predice si la mediana del evento bajará frente al periodo previo. No aprendió las cuatro respuestas de conveniencia de la app ni validó el 5%.

En la sensibilidad física CDMX con cuatro fechas base y mediana, 5% y 7% empatan en la pérdida media simulada de 2024: aproximadamente $39.16. En 2025 producen resultados diferentes. Este dato ilustra que todavía no hay un umbral universal demostrado. No escoger el ganador de 2025 y reutilizar ese año como prueba independiente.

Cerrar un informe por regla: objetivo, parámetros, origen, muestra, costo de error, cobertura, incertidumbre y condición de abstención. Diferenciar:
- Calidad suficiente o insuficiente.
- Precio favorable o alto frente a una referencia.
- Zona sin señal clara.
- Pronóstico de una bajada futura, que es otra tarea.

Usar validación interna 2024 o evaluación independiente para justificar ajustes. Si la evidencia no basta, mantener una regla provisional explícita. No forzar una regla nueva sólo para aparentar aprendizaje.

### 3. Interpretar correctamente las métricas

| Métrica en 93 series de 2025 | Árbol | Referencia mayoritaria |
|---|---:|---:|
| Exactitud balanceada | 76.0% | 50.0% |
| Accuracy | 78.5% | 77.4% |
| Precision de “bajará” | 90.6% | 77.4% |
| Recall de “bajará” | 80.6% | 100.0% |
| F1 de “bajará” | 85.3% | 87.3% |

La mejora principal está en distinguir las dos clases, no en superar toda métrica. El árbol acierta 73 casos; la referencia, 72. Esto no invalida su mayor exactitud balanceada, pero impide venderla como una mejora general de 26 puntos de accuracy.

El intervalo de exactitud balanceada es amplio: 64.7%–86.2%. El corte raíz cambia entre particiones. Mantenerlo experimental y fuera de las decisiones online hasta validar dominio y estabilidad.

2026 tiene cero ejemplos evaluables del modelo en el protocolo actual. Los nuevos precios especiales de PROFECO están separados del archivo anual: estudiar comparabilidad de identificadores, sucursales, población y ventanas antes de incorporarlos. No asumir que ya permiten evaluar el modelo.

### 4. Hay un desfase reproducible entre etapas de datos

La prueba tests/test_dataset.py::test_toda_fila_bronze_termina_limpia_o_excluida falló de nuevo:
- Las observaciones limpias locales representan 1,015,811 capturas; cero exclusiones.
- La capa bronze local contiene 1,071,337 filas de esas fuentes.
- Diferencia: 55,526 capturas.

La tabla gold usada en esa prueba tiene 683,942 observaciones, distinta del paquete v2 de 690,891. No son pruebas sobre un único corte.

Fijar entradas, ruta de trabajo y manifiesto por ejecución. Reconstruir y verificar un corte nuevo en una carpeta separada; conservar la entrega académica anterior. No quitar la prueba, cambiar sus expectativas para que pase ni interpretar la diferencia como filas perdidas sin investigar.

### 5. Falta cerrar la reproducción completa en Colab

La celda de preparación del notebook 04 carga observaciones ya limpias del ZIP y transforma tablas para análisis/app. No vuelve a ejecutar la normalización y exclusiones desde el material de entrada. Añadir una ruta reproducible de preparación compartida, con entradas versionadas y conciliación por fuente; conservar un modo rápido que use el paquete ya preparado.

La consulta especial de PROFECO se carga sólo si existe un CSV local opcional. Si falta, se omite sin una advertencia visible. Incluir el archivo limpio y las 15 exclusiones en un paquete reproducible con hash y condiciones de publicación revisadas, o declarar claramente que ese bloque no se ejecutó. No mezclar físico y online.

El notebook exporta el inventario/resumen especial, no los 2,211 precios y sus exclusiones como tablas completas del paquete final. Agregar las tablas necesarias para reproducir ese análisis manteniendo su fuente separada.

El código empaquetado en el notebook difiere del actual en tres módulos de captura/importación. Los módulos analíticos comparados coinciden. No se encontró una inconsistencia de métricas por esto, pero registrar versiones y actualizar la copia cuando se integre captura/API.

Faltan gráficos dentro del notebook: hay reportes externos, pero no llamadas de gráficos en las celdas revisadas. Integrar matriz de confusión, sensibilidad de umbrales, cobertura, calibración y ejemplos de evolución de precios.

Probar todo en un Colab limpio; hasta entonces reportar “ejecutado localmente”, no “validado en Colab”.

### 6. Continuidad y publicación

El script de tarea sale sin recolectar fuera del 15–18 de noviembre. Definir campaña hasta el 1 de diciembre para el análisis posterior y un horario sostenible después, según la fuente.

El informe indica dependencia de sesión abierta y primera ejecución pendiente. La consulta del Programador de tareas en esta revisión falló por acceso a CIM; no se pudo confirmar su estado actual independientemente. Verificar ejecución real, recuperación de una hora omitida, errores y alertas.

Git muestra los archivos nuevos v2 sin seguimiento local. Revisar y registrar sólo código y resultados publicables; confirmar su presencia en el remoto. No subir crudos privados ni credenciales.

## Orden concreto para continuar

1. Resolver acceso permitido y activar captura real del piloto; conservar mientras tanto PROFECO diario con su resolución honesta.
2. Corregir la conciliación de cortes en paralelo, sin sobrescribir las entregas congeladas.
3. Completar API/Fly, persistencia y recuperación; probar una captura permitida y una consulta desde fuera.
4. Conectar la app, probar vigencia y fallos, generar APK v2 y verificarlo en celular.
5. Cerrar justificación de decisiones y notebook reproducible; mantener el pronóstico experimental mientras corresponda.
6. Al madurar datos, evaluar 2026 y cerrar el informe de hipótesis con evidencia y límites.
7. Publicar código y paquete final, enlace de Colab, APK y guía de mantenimiento.
8. Añadir Claude para explicar evidencia sólo después de asegurar datos y decisiones. La predicción a siete días sigue siendo opcional.

## Condiciones de aceptación

Una versión completa requiere: consultas nuevas conservadas sin sobrescritura, identidad y fecha fiables, limpieza conciliada, API y app funcionando, reproducción independiente y reglas explicadas. Pasar pruebas aisladas o generar muchas tablas no reemplaza estas comprobaciones.

