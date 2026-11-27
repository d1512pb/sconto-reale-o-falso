# Revisión del segundo avance de Sconto v2
Fecha: 15 de noviembre de 2026.
Referencia: PLAN_SCONTO_V2.md y revisión del 14 de noviembre.

## Dictamen

Se cerró la conciliación del corte y se amplió la reproducción de la preparación. Hay API local, recuperación probada y APK firmado. Sigue pendiente el servicio público con alimentación de datos real, el piloto online autorizado, la prueba móvil y la evaluación final.

Publicar código y APK es un hito de distribución; no equivale a demostrar recomendaciones online operativas.

## Comprobaciones realizadas en esta revisión

- Se recalcularon los hashes de los 69 archivos del manifiesto de notebook_04_conciliado/entrega: todos coinciden.
- El Parquet limpio contiene 690,891 filas. La conciliación documenta 1,145,401 filas bronze representadas y diferencia cero en las seis fuentes.
- El APK existe y su SHA-256 coincide con el reporte: a9c15efee6553f1de196424d1c9853859393acddfcebfafbfd326b0f2eb78ec0. La comprobación de firma se encuentra en el reporte de compilación; esta revisión no repitió apksigner.
- La bitácora real del 15 de noviembre reporta 24 modelos, 2,517 observaciones, 19 exclusiones, estado ok y último día de precio 14 de noviembre. El incremento frente a las 2,211 observaciones anteriores es 306.
- El informe ampliado contiene 17 series físicas comparables: seis CDMX y once Edomex. Tres de Edomex presentan el patrón de alza y rebaja. Es un resultado preliminar.
- El commit 1fffbb2 existe en la rama local sconto-v2-publicacion-local. El checkout principal sigue en otra revisión y mantiene cambios de trabajo: publicar desde la rama revisada y comparar su contenido, sin arrastrar cambios posteriores.
- Se revisaron los módulos de API y decisiones, el generador del notebook y los reportes de operación. No se repitieron todas las pruebas declaradas ni se realizó un despliegue.

## Pendientes prioritarios

### 1. Fuente online real y autorizada

El propio reporte acceso_online_v2.md declara cero cotizaciones nuevas reales con vendedor, variante, inventario, cargos y hora comprobados. El importador fue probado con una cotización sintética. La API local comprobó 104 precios físicos; su ruta de ofertas online devolvió cero.

Por tanto, todavía no está probada la cadena real de compra online. Obtener una primera fuente utilizable y verificar un anuncio completo es más importante que ampliar la interfaz.

La pausa de fuentes restringidas conserva el histórico; debe mostrarse la fecha real del último dato y no aparentar actualización. Resolver permiso, suministro autorizado o una alternativa válida sin evadir restricciones.

### 2. La API es de consulta; falta su alimentación operativa

api_v2.py y servicio_api_v2.md sitúan la recolección y escritura fuera del proceso HTTP. Esto es una separación técnica válida, pero hay que implementar y probar el circuito que lleve las nuevas observaciones hasta la base alojada.

El contenedor Fly no ejecuta un recolector. Iniciar el servicio no crea nuevas capturas. Definir dónde corre la recolección autorizada, cómo publica sólo datos permitidos, cómo sincroniza sin duplicados y cómo informa fallos. Si depende de la PC, comunicar esa dependencia.

En configuración pública, PROFECO especial está deshabilitado y las ofertas online se restringen a cotizaciones publicables. La prueba local con información privada habilitada no demuestra qué información mostrará el despliegue público. Probar también la configuración pública exacta y contar sus filas reales.

### 3. Alinear la decisión del notebook con la API

El generador del notebook llama preparar_aplicacion, conserva la ruta de tablas anterior y declara reglas='precio-v1 provisional'. La API llama evaluar_decision de decisiones_v2.py, que declara precio-v2-provisional e impone total confirmado, verificación directa y vigencia de dos horas.

La equivalencia_operativa del manifiesto verifica la reconstrucción del corte anterior; no acredita equivalencia con este nuevo motor de decisiones.

Preservar el modo histórico congelado y añadir un modo operativo v2 que utilice el mismo motor que la API. Exportar versión y motivos de cada decisión. Comparar ambos sobre idénticas ofertas y referencias, incluyendo vencimiento, costo desconocido, cambio de variante y falta de historia.

### 4. El historial exigido no puede crearse retroactivamente con capturas nuevas

La API selecciona la ventana base del Buen Fin del año actual. El motor sólo admite historia del mismo anuncio y contexto con costo total y verificación directa, cuatro fechas y amplitud de 21 días.

La base BF2026 ya cerró antes de iniciar esta nueva captura. Recoger precios desde el 15 de noviembre no basta para poblar esa base. Incluso una cotización actual perfecta puede seguir dando evidencia insuficiente.

Documentar el número real de anuncios que cumplen historia comparable. Buscar antecedentes autorizados si existen. Si no existen, mostrar comparación actual entre ofertas verificadas como una función diferente, cuando esté disponible, y conservar abstención sobre ahorro histórico.

Para funcionamiento fuera del Buen Fin, definir una referencia móvil separada y evaluada, con versión y cobertura explícitas. No cambiar ventanas ni mínimos sólo para lograr indicadores verdes.

### 5. Reglas explicadas, pero todavía provisionales

La explicación de las cuatro respuestas mejoró. Faltan validación independiente de los cuartiles, evidencia online sobre el 5% y medición de la vigencia de dos horas.

Conservar la distinción entre requisitos de calidad, conveniencia histórica y pronóstico. El árbol continúa prediciendo bajada durante el evento; no valida automáticamente las cuatro respuestas. Las muestras 2025 y 2026 no deben reutilizarse para ajustar y luego anunciar una prueba independiente.

### 6. Despliegue, pruebas y entrega

- Iniciar sesión en Fly y comprobar organización, consumo y presupuesto antes de crear recursos.
- Desplegar la configuración pública y verificar catálogo, ofertas reales, HTTPS, recuperación y respaldo externo privado.
- Configurar la URL pública en la web; el APK carga esa web y puede abrir aunque no exista API.
- Ejecutar el notebook en Colab alojado con acceso a las entradas privadas. Mantener advertencias explícitas cuando falten.
- Instalar el APK como actualización en celular y probar consultas, vigencia, ausencia de ofertas, desconexión y caída de API.
- Publicar desde el commit revisado, con manifiesto y APK, sin crudos, respaldos ni credenciales.
- Mantener observación hasta el 1 de diciembre y definir continuidad online posterior: la vigilancia semanal de QQP no reemplaza precios actuales de anuncios.

## Higiene del informe

El informe en mercado_2026-11-15 conserva encabezado del 14 y combina snapshot público del 14 con consulta oficial ampliada. Indicar ambos cortes explícitamente y actualizar fecha de generación; no usar un único “corte” que parezca aplicable a todas las fuentes.

## Cierre pendiente que depende del tiempo

2026 sigue abierto. Evaluar sólo después de cerrar las ventanas y disponer de observaciones comparables. La muestra especial de PROFECO no se debe unir al archivo anual sin comprobar identidad y población. La evaluación online necesita evidencia online.

Claude y el pronóstico a siete días permanecen después de resolver la fuente real, la alimentación de la API y la coherencia de decisiones.

## Orden recomendado para el siguiente chat

1. Publicar los artefactos revisados con su estado experimental claramente indicado, una vez satisfecha la autorización del chat que realiza el envío.
2. En paralelo, conseguir una primera fuente online utilizable y completar la alimentación del servicio.
3. Alinear notebook/API y resolver explícitamente la falta de historia previa.
4. Desplegar Fly y probar el conjunto en Colab y celular.
5. Cerrar evaluación e informe cuando maduren los datos; continuar operación con cobertura honesta.

El bloqueo de publicación comunicado por el otro chat es una revisión de autorización para el repositorio público, no una prueba fallida del código. Esta revisión no intentó publicar.

