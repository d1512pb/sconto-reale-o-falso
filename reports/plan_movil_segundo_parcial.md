# Sconto en el celular · Plan del 6 al 17 de noviembre de 2026

**Objetivo.** Buscar audífonos o una laptop por nombre y decidir dónde conviene comprar la variante exacta, con prioridad en Sears y comparación con Liverpool. La respuesta mostrará precios en MXN, quién vende, cuándo se observó el precio y cómo se compara con el historial disponible. Para esta semana se propone convertir la web existente en una app web móvil instalable (PWA), de consulta y sin cuenta.

**Entrega escolar.** El 13 de noviembre a las 12:00, hora de CDMX, entregar enlace al notebook y dataset adjunto. La demo se hará dentro del cuaderno. Se aprovechará el primer día del evento sólo si ya existe una captura verificada. El equipo podrá evaluar el evento completo después de su cierre.

## Piloto basado en los datos del 6 de noviembre

El catálogo publicado tiene 200 productos, 26 en la familia laptop. Cuatro títulos mencionan audífonos y uno es un paquete de Sony con una tetera. El paquete requiere identidad propia. Hay 197 referencias de mínimos multitienda con base suficiente. Todas las referencias que cumplen la cobertura BF2026 en este corte son de ese tipo.

- **Laptop en Sears.** Preciómetro registró en Sears una Lenovo IdeaPad Slim 3 Core i3, 8 GB y SSD de 512 GB por $13,499, con SEARS como vendedor. Antes de comparar con otra tienda, confirmar el código del fabricante y la configuración exacta.
- **Audífonos en dos plataformas.** Preciómetro registró AirPods Pro 3 a $4,339 en Liverpool, vendidos por Liverpool, y a $7,039 en Sears, vendidos por SERVCOMP DE MEXICO SA DE CV. La diferencia observada es de $2,700. Verificar número de parte, condición, disponibilidad y envío para admitir la comparación final. Son observaciones del 6 de noviembre y la captura es indirecta.
- **Fuente de Sears.** La ficha del colector directo sigue pendiente de validación. Primero verificar las fichas públicas de esos modelos. Como evidencia adicional, guardar URL, fecha, precio, vendedor y condiciones si están disponibles y se permite la captura. Documentar como observación manual cualquier cotejo hecho a mano.

Corte consultado en [Sconto](https://d1512pb.github.io/sconto-reale-o-falso/). SHA-256 del JSON publicado: `87c1b761cb235699882ac1da1269c2e1fb32188b1bd1a9dbe5d37ced90fde3db`.

## CRISP-DM en seis fases

1. **Negocio.** Acordar las dos decisiones del comprador: cuál es la oferta comparable más barata hoy y qué tan favorable es frente a la historia. Mantener computadoras y laptops como categoría principal y audífonos como segunda prueba personal.
2. **Datos.** Inventariar por modelo las ofertas de Sears y Liverpool, distinguir tienda de marketplace y vendedor, y contar fechas, anuncios y faltantes. Preciómetro aporta historia de mercado y ofertas fechadas. QQP aporta los casos históricos de tiendas físicas. Registrar la ficha oficial como evidencia complementaria cuando sea viable.
3. **Preparación y ETL.** En el notebook, leer un snapshot fijado, mostrar la trazabilidad desde la captura, normalizar precio y fecha, separar variantes, registrar exclusiones y reproducir las tablas limpias. Para la app exportar catálogo y alias de búsqueda, ofertas por vendedor, historial diario, referencia y cobertura, y resultado con explicación. Reutilizar las tablas existentes de SQLite y publicar el JSON de consulta generado de la misma ejecución.
4. **Modelado.** Buscar por marca, nombre o modelo y permitir elegir variante si hay ambigüedad. Calcular posición del precio frente a la mediana y al rango central histórico. Mantener Isolation Forest en el notebook para revisar anomalías históricas de QQP. El indicador de compra se calcula con reglas explícitas.
5. **Evaluación.** Reproducir el Avance 1, evaluar el modelo con BF2024/BF2025 y probar el buscador con las dos consultas del piloto. Cotejar modelo, vendedor, fecha, precio y aritmética contra la evidencia. Incluir una variante ambigua, una oferta antigua y una consulta sin cobertura. Variar el umbral de precio a 5% y 10% y documentar si cambia el resultado.
6. **Despliegue.** Un buscador móvil devuelve una ficha con las ofertas ordenadas, la gráfica, la fecha del dato y una frase explicativa. Si se conocen los cargos, ordenar por total comparable; si falta envío, mostrar los precios listados y la condición pendiente. Usar la actualización diaria existente y probar instalación y consulta en el teléfono que se utilizará durante la compra.

## Regla inicial para probar

Comparar ofertas actuales del mismo día en CDMX, para la misma variante, condición, moneda y canal. Informar siempre tienda y vendedor. Las ofertas más antiguas quedan identificadas con su fecha. Para el indicador histórico exigir la base del 14 de septiembre al 29 de octubre: al menos cuatro fechas distintas con amplitud de 21 días. Un nuevo precio de noviembre ayuda a comparar ofertas actuales. Para completar la base de un vendedor habría que recuperar observaciones de esa ventana.

`ventaja_pct = 100 × (mediana_base − precio_observado) / mediana_base`

- **Precio favorable** si la ventaja es ≥5% y el precio es igual o inferior al percentil 25 de la base.
- **Precio alto** si el precio supera la mediana por ≥5% y alcanza o supera el percentil 75.
- **Sin señal clara** en los demás casos con datos comparables.
- **Evidencia insuficiente** cuando falte identidad, vigencia o cobertura. Se podrán mostrar los precios disponibles y la razón.

Etiquetar el referente como “mercado” o “mismo vendedor”. Calcular brecha respecto del descuento anunciado únicamente para la misma serie con historia suficiente. El 5% es una decisión inicial que el equipo debe contrastar. El porcentaje significa distancia frente a un precio observado.

## Fechas y criterio de entrega

- **6–8 nov.** Cerrar la lista piloto, verificar variantes y fichas de Sears/Liverpool y asegurar dos casos trazables.
- **9–10 nov.** Dejar el ETL y las reglas ejecutables en Colab. Congelar una copia del dataset para la clase y comprobar que abre junto al notebook.
- **11–12 nov.** Conectar buscador, ficha y resumen a esa misma salida. Probar en celular y ensayar la demo en Colab desde una sesión nueva.
- **13 nov., antes de las 12:00.** Entregar el enlace accesible del notebook y el dataset adjunto. En clase ejecutar una búsqueda, explicar una comparación y mostrar un caso con evidencia insuficiente.
- **13–17 nov.** Usar la app en la compra real, contrastar el resultado con la ficha o la tienda y registrar fecha, variante, vendedor, precio final y explicación de discrepancias. Separar los precios físicos y en línea. Al cierre, evaluar cuántas consultas ayudaron a decidir y en cuáles faltaron datos.
