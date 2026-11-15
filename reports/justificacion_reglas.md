# Justificación provisional de las reglas de precio

Corte del análisis 2026-11-14.

## Regla activa

Se conserva la regla precio-v1. Clasifica como favorable si el precio ahorra al menos 5% frente a la mediana y está en el cuartil inferior. Clasifica como alto si cuesta al menos 5% más y está en el cuartil superior. El 5% procede del diseño inicial y sigue siendo provisional.

Cada día aporta una mediana. Se exigen 4 fechas base en un tramo de 21 días calendario o más, al menos una fecha de evento y dos del periodo previo para estudiar un alza. Las cuatro fechas y la amplitud son el protocolo del Avance 1. La sensibilidad reevalúa entre dos y cinco fechas base y entre una y tres de evento.

## Muestra física CDMX, mediana y umbral de 5%

| Evento | Series con historia | Base y evento | Base, previo y evento | Precio favorable | Precio alto |
| --- | ---: | ---: | ---: | ---: | ---: |
| BF2024 | 2,766 | 544 | 205 | 302 | 46 |
| BF2025 | 2,102 | 298 | 93 | 201 | 16 |

La simulación compra a la última cotización observada antes del evento cuando la regla marca precio favorable. En otro caso compra al primer precio del evento. El beneficio se compara contra comprar siempre a esa última cotización previa. La pérdida se compara contra el menor precio de esas dos fechas, sin imputar días ni asumir compras realizadas. Se conservan los resultados para 2, 3, 5, 7, 10 y 15% con mediana, promedio y media recortada al 10% por cola. QQP nacional conserva su propio universo y contiene CDMX. Los resultados se leen por separado. La simulación no incorpora envío, condiciones de pago, inventario, ni preferencias del comprador.

## Modelo de espera

Dentro de BF2024 se seleccionó el árbol de profundidad 2. En BF2025 (93 series, 53 productos), la exactitud balanceada fue 76.0% (IC95% por producto 64.7% a 86.2%), frente a 50.0% de la clase mayoritaria. La matriz registró 15 verdaderos negativos, 6 falsos positivos, 14 falsos negativos y 58 verdaderos positivos. Un falso positivo pronostica una bajada que no se observó. Un falso negativo omite una bajada observada. El resultado es experimental.

La variable del primer corte del árbol varió entre particiones. cambio_previo_pct en 2 de 4 particiones, cortes -0.03% a -0.03%, iqr_previo_pct en 2 de 4 particiones, cortes 2.50% a 2.50%.

Los conjuntos contienen 31 productos compartidos y 22 productos exclusivos de la prueba, según los identificadores QQP. BF2025 y parte de BF2026 ya se exploraron en el proyecto. La prueba queda fija y el modelo queda fuera de la app. QQP se recuperó retrospectivamente en 2026. No se conoce la fecha de publicación por fila.

El corte disponible para 2026 es qqp_cdmx al 2026-08-31, qqp_nacional al 2026-08-31. El evento 2026 queda abierto. El diagnóstico de siete días mide continuidad con observaciones diarias de la misma serie. Falta confirmar vigencia en tienda y validar años comparables para un modelo online. No se presenta evaluación de 2026.

[Validación por grupos en scikit-learn](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data)
