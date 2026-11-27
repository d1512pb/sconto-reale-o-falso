# Sconto v2 — Plan de ejecución y entrega final

Fecha del plan: 14 de noviembre de 2026.
Repositorio: https://github.com/d1512pb/sconto-reale-o-falso
Carpeta: C:\Users\danie\Documents\ESCOM\Semestre 7\Mineria  de datos\Sconto\SCRIPTS

Este archivo es un plan para el siguiente chat. No certifica que la API, los nuevos colectores o los nuevos modelos ya estén desplegados.

## 1. Objetivo y alcance

Convertir Sconto en una herramienta que responda: **“¿Este precio conviene, con qué evidencia y qué incertidumbre queda?”** La entrega final tendrá dos resultados:

1. Una app de consulta que siga funcionando: producto, variante, vendedor, precio, historial, vigencia y explicación.
2. Un notebook reproducible y un análisis del Buen Fin: hipótesis, resultados, métricas, casos y limitaciones.

Prioridad comercial: Sears, laptops/computadoras y audífonos; después Liverpool y el catálogo tecnológico existente. Mantener búsqueda sin perfiles ni publicaciones.

“Sí conviene por precio” no significa que el usuario deba endeudarse, que el equipo sea apropiado para cualquier necesidad o que conozcamos su capacidad de pago. La app debe especificar condiciones y costo total cuando estén disponibles.

El Buen Fin 2026 ocurre del 13 al 17 de noviembre. Estamos dentro del evento: conservar observaciones nuevas es la primera prioridad. Los cambios intradía que no se capturaron no se pueden reconstruir por suposición. Fuente: [portal oficial](https://www.elbuenfin.org/preguntas-frecuentes).

## 2. Qué existe y qué hay que corregir

Leer primero README.md, CONTRATO_APP.md, config/fuentes.yaml, config/eventos.yaml, notebooks/03_Sconto_CRISP_DM_ETL_web.ipynb y los módulos de src/sconto. Revisar el estado real de GitHub Actions y de la tarea local antes de modificar horarios.

Hallazgos comprobados en el código:

- El colector de Preciómetro reutiliza el archivo crudo del día si ya existe. Ejecutarlo más veces no fuerza una nueva consulta.
- La clave de observación usa fuente, identificador, fecha y vendedor. No distingue horas. La escritura de bronze deduplica con esa clave.
- Los estados de ejecución también se consolidan por día. Hay que conservar los intentos individuales.
- Las ofertas del agregador reciben la fecha de captura. Eso no demuestra cuándo la tienda actualizó o verificó su precio.
- La regla vigente usa mediana histórica y cuartiles, no solamente un descuento de 5%. Con evidencia válida, marca favorable si el ahorro es al menos 5% y el precio está en el cuarto inferior del historial; alto si supera la referencia al menos 5% y está en el cuarto superior.
- La identidad actual puede ser “compatible por texto”; todavía no equivale a verificar exactamente el SKU, es decir, el código de la variante comercial.
- Amazon directo está desactivado por decisión del equipo. Mantenerlo así y usar fuentes indirectas.
- El catálogo amplio y los productos que se consultan diariamente son conjuntos diferentes. Mostrar ambas coberturas.

El reporte local leído tiene corte del 10 de noviembre: 409,138 observaciones físicas QQP, 250,668 del historial de Preciómetro, 27,011 de sus ofertas, 109 de Wayback, 14 de tiendas y una captura antigua de Amazon. **Son cifras de ese reporte, no el inventario actual.** Ese mismo reporte conserva texto anterior al evento: regenerarlo con fechas reales.

En dicho corte, QQP aporta 205 series con cobertura de alza para 2024 y 93 para 2025. Wayback no aporta cobertura suficiente del evento en esos años. Millones de capturas o cientos de miles de filas no equivalen a cientos de miles de ejemplos independientes para entrenar.

No afirmar aún que las diferencias vistas por Daniel se deben solamente a la frecuencia. También pueden intervenir cambios de vendedor, variante, envío, promociones condicionadas, datos antiguos del agregador o errores de selección.

## 3. Trabajo urgente: conservar precios durante el evento

### 3.1 Piloto verificable

Seleccionar 20–30 productos prioritarios con sus anuncios concretos. Revisar manualmente una muestra contra la ficha de la tienda y guardar:

- Modelo, capacidad, RAM, generación, condición y componentes del paquete.
- Tienda/plataforma y vendedor efectivo; distinguir tienda oficial de marketplace.
- Precio visible, precio tachado, envío, cupón, requisitos, disponibilidad y URL.
- Hora de consulta, procedencia y evidencia cruda.
- Diferencias entre app, agregador y tienda; causa confirmada o todavía desconocida.

Crear reports/auditoria_precios_v2.csv. Ningún anuncio ambiguo debe recomendarse como variante confirmada.

### 3.2 Frecuencia propuesta, sujeta a lo que permita cada fuente

| Grupo | Propuesta inicial | Condición |
|---|---|---|
| Anuncios prioritarios con consulta directa permitida | Cada 30 minutos; probar 15 si aporta cambios | Robots, condiciones, límites y prueba de carga aprobados |
| Resto de anuncios con precio actual accesible | Cada 2–6 horas | Presupuesto de solicitudes por dominio |
| Historial diario de Preciómetro | Una vez al día | No convertir un punto diario en varios puntos horarios |
| QQP | Revisar nuevas publicaciones periódicamente | No anunciarlo como precio en tiempo real |

Las cifras son parámetros del piloto, no un permiso de las fuentes ni una garantía de frescura. Una consulta cada 30 minutos a 20 URLs son hasta 960 consultas diarias, más comprobaciones auxiliares: medir si el proveedor lo admite y reducir si corresponde.

Mantener pausas y límites por dominio, lista fija, agente identificable y caché por intervalo. Detener CAPTCHA/403; aplicar la política conservadora del proyecto ante 503. Ante 429 respetar la espera indicada y suspender la fuente si persiste. No cambiar IP o identidad para sortear un bloqueo.

Si Fly.io o una fuente no están disponibles, continuar desde el entorno local autorizado. Un bloqueo se registra; nunca se transforma en un precio ni se sustituye silenciosamente por una fuente “equivalente”.

### 3.3 Fuentes y orden

1. **Sears y Liverpool:** verificar robots, condiciones y acceso público actual; probar pocos anuncios conocidos. Preferir datos estructurados públicos de la ficha. No prometer acceso antes de la prueba.
2. **Preciómetro:** conservar el historial disponible y comprobar si sus ofertas contienen hora de actualización. Un agregador no garantiza el mismo precio que el checkout.
3. **Mercado Libre:** probar acceso oficial y permisos de endpoints con las credenciales existentes. Si requiere registrar una app nueva, pedir autorización en ese punto; nunca suponer acceso a precios de cualquier vendedor.
4. **QQP:** actualizar lo disponible y auditar 2024/2025/2026. Mantener CDMX y nacional separados.
5. **Archivos web:** consultas dirigidas a URLs exactas para conseguir anuncios históricos. No dedicar el tiempo crítico del evento a rastreos masivos.
6. **INEGI y otras tiendas:** complemento posterior. INPC aporta tendencia, no el precio real de un SKU; publicaciones comunitarias son evidencia secundaria.

Crear reports/fuentes_v2.csv con filas reales, cobertura, permisos observados, frecuencia, bloqueos y límites. Una fuente sin observaciones utilizables sigue “evaluada”, no “integrada”.

## 4. Arquitectura mínima y compartida

Flujo:

Fuentes → capturas inmutables → normalización y validación → base de datos
→ indicadores/modelos → API → app.
El notebook importa los mismos módulos y reproduce la transformación con una versión fijada.

### 4.1 Capturas intradía

Añadir tablas nuevas; preservar los archivos de las entregas anteriores.

- **capturas:** capture_id, fuente, URL, fetched_at_utc, estado HTTP, resultado, hash y ruta cruda, versión del colector.
- **ofertas:** offer_id estable, producto/variante, plataforma, vendedor, condición y enlace.
- **observaciones_intradia:** capture_id + offer_id, observed_at, source_updated_at si existe, precisión temporal, precio, moneda, disponibilidad y condiciones.
- **trabajos:** intento, vencimiento, ejecución, reintento permitido y último error.
- **decisiones/predicciones:** hora de emisión, evidencia utilizada, estado, versión de reglas/modelo y resultado futuro cuando madure.

Guardar UTC y mostrar America/Mexico_City. Separar fecha del precio histórico, hora de descarga, fecha de actualización declarada por la fuente y fecha de publicación del dataset. Si la hora real del precio es desconocida, dejarla desconocida.

Usar crudos con fecha, hora y capture_id. Reintentar el mismo trabajo no duplica; una captura posterior sí constituye una nueva observación, aunque el precio siga igual. Conservar comprobaciones sin cambio para medir continuidad y vigencia.

Las tablas diarias serán una agregación explícita: último precio, mínimo observado, mediana, máximo y número de comprobaciones. Las estadísticas entre días deben dar el mismo peso a cada día; aumentar las consultas no debe cambiar artificialmente la referencia histórica.

No imputar faltantes ni inventar horarios de datos antiguos. Precios extremos se revisan, no se eliminan por ser extremos. Registrar exclusiones y consolidaciones con sus motivos y trazabilidad.

### 4.2 Servicio

Propuesta: FastAPI, un proceso de recolección ligero y SQLite con escritura transaccional en un volumen persistente. Una sola máquina inicialmente; cola persistida y exclusión mutua para evitar dos recolectores simultáneos. Si hay respaldo local, coordinarlo mediante trabajos identificados o asignar fuentes distintas.

Rutas iniciales:

- GET /health y /v1/status.
- GET /v1/products?q=...
- GET /v1/products/{id}/offers y /history.
- GET /v1/products/{id}/decision.
- GET /v1/version.
- Actualización administrativa protegida; la consulta pública sólo puede solicitar anuncios ya autorizados, con límites y solicitudes repetidas agrupadas.

No permitir consultas de URLs arbitrarias desde el servidor. Proteger secretos, administración, tamaño de respuestas y frecuencia de consultas. El APK nunca contiene claves de proveedores ni la clave administrativa.

Separar la API pequeña del ETL completo y del entrenamiento. Pandas sobre todo el histórico, navegadores y entrenamiento permanecen en Colab/PC/Actions. Medir memoria antes de alojar inferencia adicional.

### 4.3 Notebook y app coherentes

Extraer funciones reutilizables de limpieza, identidad, atributos y decisión, con dependencias fijadas. Notebook, actualización diaria y API deben llamar esas funciones; no mantener tres versiones de la misma regla.

Cada exportación incluirá versión del código, datos, esquema, reglas, modelo, fecha máxima por fuente y hashes SHA-256. Con igual entrada y configuración, notebook y API deben devolver igual resultado.

Mantener intacto el notebook 03 y su entrega congelada. Crear notebooks/04_Sconto_CRISP_DM_v2.ipynb. Probar compatibilidad del nuevo contrato con la app actual antes de publicar un APK nuevo.

## 5. Fly.io: despliegue pequeño, presupuesto comprobado

La documentación vigente confirma que se condona una factura **menor de US$5** de la organización personal, con modalidad Pay As You Go y tarjeta registrada. Si llega a US$5 o más, se cobra completa. No aplica a cualquier organización. [Política oficial](https://docs.fly.io/about/free-waiver).

Estimación de referencia para 30 días, región iad/ewr: una máquina de 512 MB US$3.69 + volumen de 1 GB US$0.15 + 1 GB de salida US$0.02 = **US$3.86**, antes de otros consumos. Es un escenario, no una cotización garantizada. Verificar espacio real de la base y crudos antes de elegir volumen. [Precios](https://docs.fly.io/about/pricing).

Comprobar la organización y el consumo total existente antes de desplegar. Objetivo operativo: mantenerse por debajo de US$4.50 proyectados, contando todos sus servicios. No activar escalado, segunda máquina, IP dedicada, base administrada ni ampliación automática de disco. Si falta tarjeta o se necesita asumir nuevos cargos, detener sólo ese paso y pedir decisión; seguir recolectando localmente.

Fly.io no ofrece un tope automático ni, según la documentación revisada, alertas de facturación. Vigilar factura y proyección desde el dashboard; si se implementa un monitor, comprobar que existe una vía oficial para consultarlas. Detener cómputo no elimina cargos de almacenamiento. [Gestión de costos](https://docs.fly.io/about/cost-management).

Una máquina que recolecta por temporizador debe permanecer activa durante la campaña; no confiar en que un temporizador interno despierte una máquina detenida. [Autostop](https://docs.fly.io/launch/autostop-autostart).

SQLite y crudos deben vivir en el volumen, no en el disco efímero. Una sola máquina reduce costo, pero permite interrupciones: no es alta disponibilidad. Guardar respaldo externo privado de crudos y base, y probar restauración; los volúmenes no se replican solos. No publicar HTML con información incidental de ubicación o sesiones. [Volúmenes y respaldo](https://docs.fly.io/volumes/overview).

Preparar Dockerfile, fly.toml, healthcheck, reinicio, migración reversible y procedimiento de recuperación. Hacer una prueba real en Fly: respuesta de API, captura permitida, persistencia tras reinicio, memoria y respaldo. Si no cabe en presupuesto/memoria, conservar API estática y recolección local; no aumentar recursos sin resolver el costo.

## 6. Cómo justificar o sustituir el 5%

El 5% actual es una decisión inicial de diseño. **Todavía no es un umbral aprendido ni una frontera universal entre oferta real y falsa.**

Separar tres preguntas:

1. ¿Tenemos datos comparables y suficientemente recientes? Es un requisito de calidad.
2. ¿Cuánto ahorro resulta relevante para una compra? Es una preferencia de utilidad, en pesos y porcentaje.
3. ¿Qué cambio es inusual frente a la variación normal? Es una pregunta estadística.

Un modelo puede aprender relaciones y estimar probabilidades. No puede deducir por sí solo cuánto le importa ahorrar al comprador.

Procedimiento:

- Congelar la regla actual como baseline, la referencia inicial contra la que comparar.
- Probar umbrales de 2, 3, 5, 7, 10 y 15%; conservar también el porcentaje continuo.
- Justificar también los mínimos de cobertura: el protocolo actual exige al menos cuatro fechas base distribuidas en 21 días, una del evento y dos del previo para calcular alza. Conservarlo como referencia y comparar mínimos de dos a cinco fechas; varias capturas en una fecha no equivalen a varios días. No bajar requisitos sólo para producir más recomendaciones.
- Estudiar mediana, cuartiles y dispersión por categoría y vendedor. El promedio aritmético puede subir por unos pocos precios altos: mantener mediana como referencia principal y comparar con promedio y media recortada como sensibilidad.
- Para aprender una política de compra, usar resultados futuros observados de la misma oferta o una revisión humana independiente y documentada. Nunca usar “cumple 5%” como etiqueta y después presentar accuracy contra esa misma etiqueta.
- Comparar la regla fija con un árbol pequeño, de profundidad 2–3, que permita mostrar qué cortes aprendió. Evaluar estabilidad de esos cortes entre particiones y tamaños de muestra.
- Medir pérdida por comprar antes de una bajada, ahorro frente a la referencia, oportunidades omitidas y proporción de casos donde se puede decidir. La simulación necesita un horizonte y una política de compra/espera fijados; “no comprar nunca” no puede ganar por defecto.
- Elegir umbrales usando sólo validación interna de entrenamiento. Priorizar el costo de una recomendación equivocada y mostrar sensibilidad a distintas preferencias, no solamente el mejor F1.
- Si no hay etiquetas o cobertura suficientes, entregar la sensibilidad y mantener el 5% declarado como provisional. No fabricar una justificación estadística.

El umbral sobre una probabilidad del modelo es distinto del porcentaje de ahorro. La selección de ese umbral debe responder al uso de la decisión. [Ajuste de umbrales en scikit-learn](https://scikit-learn.org/stable/modules/classification_threshold.html).

Entregables: reports/justificacion_reglas.md, sensibilidad_umbrales.csv, reglas_v2.json y una gráfica de beneficio/error/cobertura frente al umbral. Cada regla deberá indicar origen, muestra, objetivo, versión y límites.

## 7. Modelos: una pregunta útil antes que una métrica vistosa

Conservar Isolation Forest para detectar patrones atípicos de precios y priorizar revisión. Su puntaje no representa probabilidad de engaño ni, por sí mismo, una recomendación.

### 7.1 Modelo supervisado de primera prioridad: esperar al evento

Pregunta: **“Con lo observado antes del Buen Fin, ¿el precio de esta misma serie será menor durante el evento?”**

Este objetivo se ajusta mejor al historial esporádico QQP que prometer una predicción horaria.

- Unidad: producto × sucursal/vendedor × canal × evento.
- Momento de predicción: cierre del día anterior al inicio del evento.
- Variables: nivel relativo, tendencia previa, dispersión, cobertura y antigüedad; solamente datos disponibles entonces.
- Resultado observado: mediana del precio del evento menor que la mediana del periodo previo. Conservar también la diferencia continua en pesos y porcentaje.
- No usar el ahorro calculado con precios del evento como predictor.
- No introducir 5% en la etiqueta principal; estudiar después si las diferencias son económicamente relevantes.
- Exigir cobertura previa y del resultado; reportar sensibilidad a exigir más fechas del evento. Sin observaciones posteriores suficientes, etiqueta desconocida.
- Comparar clase mayoritaria, regresión logística y árbol pequeño. Añadir un modelo más complejo sólo si aporta mejora verificable.

Esta predicción responde a una disminución observada de precio, no prueba “fraude” ni resume por sí sola toda la conveniencia de comprar.

### 7.2 Modelo operativo posterior: esperar siete días

Pregunta: **“¿Se observará un precio comparable más bajo durante los próximos siete días?”**

Sólo implementarlo si una auditoría demuestra series suficientemente frecuentes y comparables. Las series online disponibles desde 2026 no satisfacen automáticamente entrenamiento online 2024 y prueba online 2025.

Guardar la predicción antes del resultado. Precio futuro mínimo observado no es el mínimo absoluto del mercado. Definir cobertura futura de antemano, incluyendo observaciones hasta el cierre del horizonte; ausencia de registros no significa que no bajó. Considerar costos de esperar y riesgo de perder disponibilidad.

Este segundo modelo es una ampliación, no un requisito para que la app opere ahora. Si no es viable, documentarlo y concentrar el esfuerzo en reglas verificables y en el primer modelo.

### 7.3 Separación temporal obligatoria

| Conjunto | Uso |
|---|---|
| 2024 | Entrenamiento y validación temporal interna para variables, parámetros, calibración y umbrales |
| 2025 | Prueba congelada del modelo elegido; no ajustar tras ver su resultado y seguir llamándolo prueba independiente |
| 2026 | Evaluación final al cerrar ventanas y disponer de resultados observados |

En validación, ordenar por fechas y agrupar las observaciones relacionadas. No dividir filas horarias al azar. Purgar horizontes futuros que crucen particiones; calcular cada atributo sólo con el pasado. Transformaciones y calibración se ajustan dentro del entrenamiento. [Validación y separación de datos](https://scikit-learn.org/stable/modules/cross_validation.html).

Para un único ejemplo anual por serie y pocos datos 2024, no inventar muchas particiones temporales: justificar la validación posible por productos, reducir complejidad y declarar la limitación. Años anteriores pueden aportar un experimento secundario separado si se autoriza cambiar el protocolo principal.

Reportar productos compartidos y nuevos entre años, tiendas y categorías. QQP físico y marketplace online son poblaciones distintas: no trasladar automáticamente las métricas de una a otra.

2025 y parte de 2026 ya fueron explorados por el proyecto. Declararlo. Un modelo creado ahora para predecir desde el 12 de noviembre es una reconstrucción retrospectiva; no se puede afirmar que se emitió realmente ese día. Las predicciones nuevas sólo son prospectivas desde su registro y congelación.

No prometer evaluación BF2026 de QQP antes de que se publique y tenga cobertura. Si sólo existen datos online nuevos, presentar esa evaluación separada; no rellenar la falta con otra población.

### 7.4 Métricas y criterio de publicación

Para la clasificación supervisada: matriz de confusión con conteos, accuracy, balanced accuracy, precision, recall, F1 y distribución de clases. Mostrar intervalos de incertidumbre y tamaño efectivo de muestra; agrupar por producto/serie al remuestrear.

Definir cuál es la clase positiva: “se observó una bajada”. Explicar qué significa cada error. Una matriz de confusión evalúa esa predicción, no certifica engaño.

Para probabilidades: curva de calibración y Brier, error cuadrático de probabilidades. Brier no mide sólo calibración. Para una regresión opcional: MAE en pesos, RMSE y comparación contra mantener el último precio. [Calibración](https://scikit-learn.org/stable/modules/calibration.html).

Separar calidad del modelo de cobertura: cuántos casos quedaron fuera y por qué. “Falta evidencia” es abstención, no una clase real que el modelo haya acertado.

Si el modelo no mejora la referencia en el objetivo predefinido, es inestable o no tiene prueba comparable, queda experimental. La app sigue con reglas transparentes. No fijar un porcentaje de accuracy como promesa antes de analizar los datos.

## 8. Qué mostrará la app y qué hará Claude

Conservar cuatro respuestas, con texto prudente:

| Estado | Condiciones para usarlo |
|---|---|
| Sí: precio favorable según la evidencia | Variante y condiciones comparables, precio vigente, cobertura suficiente y criterio de beneficio validado |
| No conviene a ese precio | Evidencia comparable de precio alto o alternativa verificable mejor; indicar cuál de las dos |
| Sin señal clara | Evidencia suficiente, pero sin diferencia concluyente |
| Falta evidencia | Identidad, vigencia, costo, historial o disponibilidad impiden decidir |

La pantalla separará precio publicado de costo total confirmado. Un envío desconocido no vale cero. Cupones, membresías, bonificaciones bancarias, topes y MSI se describen como condiciones; no se suman automáticamente al ahorro efectivo.

Mostrar siempre: precio, vendedor, variante, hora de consulta, antigüedad real conocida de la fuente, referencia utilizada, ahorro calculado y motivos. Una referencia mínima entre tiendas no demuestra cómo cambió el precio de Sears. Un pronóstico futuro, si está validado para ese dominio, aparece separado del indicador histórico.

La vigencia será específica por fuente. Consultar un agregador ahora no convierte su oferta en verificada ahora en la tienda. Si vence el dato, bajar la confianza y ofrecer el enlace original; no mantener un “sí” verde por el corte general del catálogo.

Claude será una capa opcional de explicación:

- Recibe sólo evidencia estructurada y la decisión calculada.
- Explica en pocas líneas y cita identificadores/enlaces permitidos.
- No inventa precios, historial o disponibilidad; no reemplaza los controles de calidad.
- La salida estructurada ayuda a validar formato, pero no garantiza veracidad: comprobar cifras y referencias contra la entrada y usar texto determinista si falla. [Documentación de Claude](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
- Clave únicamente en el servidor; sin HTML no confiable tratado como instrucciones.
- Caché por huella de evidencia y versiones; límite de tokens, llamadas y presupuesto independiente de Fly.
- La app funciona sin Claude. Activarlo después de que datos, reglas y API pasen las pruebas.

Mantener funcionamiento sin conexión con la última copia válida y su antigüedad. Si falla la API, usar el snapshot publicado y avisar qué fecha se está consultando.

## 9. Análisis de mercado: hipótesis, no conclusiones anticipadas

“Hubo pocas ofertas reales” y “subieron precios para bajarlos” son hipótesis del equipo. El estudio debe poder refutarlas.

| Hipótesis/patrón | Evidencia necesaria y límite |
|---|---|
| Alza previa seguida de rebaja | Mismo producto y vendedor, base, previo y evento; no atribuir intención a una curva |
| Precio tachado inflado frente a lo habitual | Precio anunciado y referencia histórica comparable; distinguir lista del fabricante de precio anterior |
| Aumentó el porcentaje anunciado sin bajar el precio pagable | Capturas sucesivas de ambos precios y mismas condiciones |
| Promoción condicionada parece descuento general | Términos del cupón, banco, membresía, mínimo, tope y fecha del beneficio |
| Envío o cargos absorben el ahorro | Costo total comparable para el mismo contexto de entrega |
| Cambio de variante/vendedor parece una rebaja | Identificadores, atributos, condición y vendedor |
| Oferta fugaz, agotada o desactualizada | Comprobaciones de disponibilidad y duración; distinguir fallo de captura de agotamiento |
| Descuento verificable y útil | Precio menor que referencias comparables, costo y disponibilidad comprobables |

No prometer encontrar “todos los trucos”. Diferenciar anomalía, error de datos, cambio legítimo y patrón compatible con una promoción engañosa; ninguno demuestra intención por sí solo.

Calcular frecuencia y magnitud de cambios, duración observada de ofertas, ahorro respecto a mediana y mínimo observado, brecha anunciada/histórica y cobertura por tienda/categoría. No ponderar más a un producto por haberlo consultado más veces.

Reportar denominadores, faltantes, sesgo de selección e incertidumbre. No extrapolar los productos vigilados al mercado mexicano completo. Comparar periodos posteriores con cuidado por Black Friday y Cyber Monday.

Cada afirmación final tendrá: hipótesis, definición, tabla/gráfica, muestra, resultado, explicación alternativa y límite. Entregables: hipotesis.csv, hallazgos.csv, informe_mercado.md/PDF y gráficos reproducibles.

## 10. CRISP-DM y notebook final

| Fase | Aplicación concreta |
|---|---|
| Comprensión del negocio | Decidir por precio con evidencia; costo de equivocarnos y cuándo abstenernos |
| Comprensión de datos | Cobertura por año/fuente, variantes, tiendas, faltantes y vigencia |
| Preparación | ETL compartido: extraer, transformar y cargar; trazabilidad, exclusiones y tablas comparables |
| Modelado | Regla base, sensibilidad, modelo supervisado e Isolation Forest con tareas diferenciadas |
| Evaluación | Prueba 2025, evaluación 2026 cuando madure, métricas, revisión manual y utilidad |
| Despliegue | API, app, versiones, exportaciones, monitoreo y recuperación |

El notebook 04 ejecutará el proceso con datos accesibles desde Colab, sin rutas de Windows. Debe mostrar la preparación real, aunque reutilice funciones del paquete; incluir un modo de reproducción offline con datos congelados y otro de actualización explícita.

Exportaciones: observaciones limpias CSV/Parquet, productos, ofertas, precios diarios/intradía, decisiones, predicciones, resultados, métricas, manifiestos y base SQLite para consulta. Incluir diccionario con unidades, rangos y significado de faltantes.

Demo breve: buscar producto → comprobar variante/vendedor → ver historial y actualidad → explicar indicador → mostrar el modelo y su evaluación → abrir la app con la misma versión de datos.

## 11. Orden de ejecución y criterios de terminado

| Prioridad | Trabajo | Evidencia de terminado |
|---|---|---|
| P0 — inmediatamente durante el evento | Auditar precios, separar capturas intradía y activar piloto permitido | Dos o más capturas distintas del mismo anuncio conservadas; precios comparados contra fuente; crudos y logs |
| P1 — después de probar P0 | API ligera, volumen, respaldo y despliegue dentro del presupuesto | URL operativa, prueba de reinicio/restauración, estado de fuentes y consumo documentado |
| P2 | App conectada, vigencia por fuente y recuperación ante fallos | Pruebas en celular de actualización, desconexión, dato vencido, variante distinta y API caída |
| P3 — puede avanzar en paralelo con P0/P1 | Auditoría 2024/2025, sensibilidad y modelo supervisado | Reglas justificadas, particiones congeladas, métricas reales y reporte de viabilidad |
| P4 — tras cerrar ventanas y recibir datos | Evaluación 2026 y análisis de mercado | Predicciones y resultados separados; hipótesis aceptadas/rechazadas o no resolubles |
| P5 | Entrega y operación posterior | Notebook completo, dataset, informe, APK, documentación y rutina de mantenimiento |

Si se mantiene el evento 13–17, el periodo posterior de 14 días termina el 1 de diciembre. Un pronóstico a siete días emitido el 17 madura el 24. No anunciar resultados completos antes de su fecha ni antes de disponer de observaciones.

Pruebas imprescindibles:

- Capturas intradía no se sobrescriben; reintentos no duplican.
- Un cambio de vendedor, capacidad o condición no altera la serie equivocada.
- Fuentes antiguas y fallidas no aparentan estar recién verificadas.
- Precio tachado de otro producto/carrusel no entra en la oferta.
- Cálculos de notebook, exportación y API coinciden sobre la misma entrada.
- No hay variables futuras en entrenamiento ni ajustes sobre la prueba.
- Respaldo recuperable, claves fuera del APK/repo y API con límites.
- Preservar la reproducción original QQP2025: 39,363 limpias, 298 series de ahorro y 93 de alza, usando el universo original fijado.
- No publicar métricas ni muestras sintéticas como resultados de mercado.

Medir disponibilidad, retraso de captura, errores, memoria, almacenamiento y consumo. Los objetivos de frecuencia se contrastan con el intervalo realmente logrado; el panel debe mostrar los huecos.

## 12. Instrucciones para el nuevo chat

Trabaja sobre el repo existente; la ruta “Mineria  de datos” contiene dos espacios. Inspecciona cambios locales y tareas activas antes de editar. No sobrescribas las entregas congeladas ni borres datos. Mantén Amazon directo desactivado.

Empieza por P0. No esperes a terminar IA, modelos o interfaz para preservar nuevas capturas. Reutiliza módulos y pruebas existentes. Haz cambios reversibles y conserva el contrato anterior mientras migras.

La autorización del usuario abarca preparar la mejora y desplegar en Fly dentro de las condiciones planteadas. Antes de consumir recursos comprueba cuenta, organización y presupuesto total; una factura condonable no es un límite de gasto. Pedir sólo la acción concreta que falte si se requieren tarjeta, nueva app/credencial o mayor presupuesto. No pedir claves en texto del chat.

Al terminar cada bloque informa: archivos cambiados, observaciones reales, prueba ejecutada, resultado, límite y siguiente paso. Diferencia “implementado”, “probado localmente”, “desplegado” y “validado con datos reales”.

Resultado esperado: una recomendación trazable y honesta, un modelo evaluado en el problema que realmente predice y un estudio del evento cuyos hallazgos puedan verificarse.

