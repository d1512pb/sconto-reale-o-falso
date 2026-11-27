# Modelo predictivo: evaluación con datos del Buen Fin 2026

Corte del 26 de noviembre de 2026. Script: `scripts/viabilidad_modelo_bf2026.py`.

**Pregunta del modelo.** Dados los precios de la base (14 sep–29 oct) y del previo (30 oct–12 nov), ¿la mediana del precio durante el evento (13–17 nov) quedará por debajo de la mediana del previo? Clase positiva: «bajó».

**Modelo.** Árbol de decisión de profundidad 2 (`arbol_2`), con las mismas ocho variables, hiperparámetros y semilla del protocolo `protocolo_modelo_v2.json`. Se entrena sólo con BF2024 (205 series QQP) y no se reajusta con los datos de 2025 ni de 2026. La regresión logística y la clase mayoritaria sirven como referencias.

| Conjunto de prueba | n | Bajaron | Modelo | Accuracy | Balanced acc. | Precisión | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| BF2025 · QQP sucursales (reproduce el notebook 04) | 93 | 72 | árbol 2 | 0.785 | **0.760** | 0.906 | 0.806 | 0.853 |
| | | | clase mayoritaria | 0.774 | 0.500 | 0.774 | 1.000 | 0.873 |
| BF2026 · piloto PROFECO, mínimos estrictos | 17 | 14 | árbol 2 | 0.882 | 0.798 | 0.929 | 0.929 | 0.929 |
| | | | clase mayoritaria | 0.824 | 0.500 | 0.824 | 1.000 | 0.903 |
| BF2026 · Preciómetro, mínimo multitienda | 187 | 110 | árbol 2 | 0.701 | **0.673** | 0.711 | 0.827 | 0.765 |
| | | | regresión logística | 0.588 | 0.500 | 0.588 | 1.000 | 0.741 |
| | | | clase mayoritaria | 0.588 | 0.500 | 0.588 | 1.000 | 0.741 |

Matrices de confusión del árbol (TN/FP/FN/TP): BF2025 15/6/14/58 · PROFECO 2026 2/1/1/13 · Preciómetro 2026 40/37/19/91.

## Lectura

- Los datos nuevos permiten la primera evaluación del modelo en 2026. En las 187 series de Preciómetro, el árbol entrenado en 2024 supera la referencia: balanced accuracy de 0.673 frente a 0.500 y accuracy de 0.701 frente a 0.588. La regresión logística no generaliza: predice «bajó» en todos los casos.
- Conviene reportar la **balanced accuracy**, porque las clases están desbalanceadas. En BF2025, la clase mayoritaria tiene mayor F1 (0.873) que el árbol sin aportar información.
- El piloto PROFECO sólo deja 17 series con los mínimos del protocolo. Sus métricas se presentan como caso ilustrativo, no como estimación.

## Límites

- **Cambio de población.** El modelo aprendió de sucursales físicas QQP. Preciómetro es el mínimo en línea entre tiendas, y la tienda que ofrece ese mínimo puede cambiar. Para incluirlo se relajó sólo el requisito de identidad de sucursal; se conservan los mínimos de fechas y amplitud.
- **Ventana del evento incompleta.** Preciómetro se pausó el 14 de noviembre, así que su ventana del evento sólo tiene el 13 y el 14.
- **No es una predicción prospectiva.** El modelo se fijó con BF2024 sin ver resultados de 2026, pero la evaluación se hace después del evento y algunas partes de BF2026 ya se habían explorado en entregas anteriores.
- **Sin muestra para otras métricas.** No hay datos posteriores al 17 de noviembre ni ofertas en línea verificadas.
