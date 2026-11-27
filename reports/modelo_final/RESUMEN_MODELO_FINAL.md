# Modelo final de Sconto · corte del 26 de noviembre de 2026

Generado con `python -m sconto.modelo_final` sobre el paquete congelado del corte (`sconto_colab_2026-11-26.zip`, SHA-256 `e6e8b353…`) y el piloto PROFECO. Las tablas completas están en esta carpeta y el notebook `notebooks/06_Sconto_Final_CRISP_DM.ipynb` reproduce todo.

## Pregunta y etiqueta

**¿Bajará el precio de este producto de tecnología durante el Buen Fin?** "Bajó" significa que la mediana del precio durante el evento quedó por debajo de la mediana de las dos semanas previas, en la misma serie (producto × sucursal). Las ocho variables más el nivel de precio sólo usan precios anteriores al evento.

## Datos de modelado (1,909 series)

| Edición | Fuente | Series | % bajó | Uso |
|---|---|---|---|---|
| BF2018–BF2021 | QQP sucursales CDMX | 850 | 60.4 % | Entrenamiento |
| BF2022–BF2023 | QQP | 557 | 59.4 % | Entrenamiento y validación |
| BF2024 | QQP | 205 | 50.2 % | Validación (elegir el modelo) |
| BF2025 | QQP | 93 | 77.4 % | Prueba |
| BF2026 | Preciómetro (mínimo en línea) | 187 | 58.8 % | Validación final |
| BF2026 | Piloto PROFECO | 17 | 82.4 % | Validación final |

Fechas oficiales de cada edición y sus fuentes en `EDICIONES` de `src/sconto/modelo_final.py`. 2020 duró 12 días.

## Decisiones justificadas con datos

La regla de la app se puso a prueba contra **semanas normales** (prueba placebo): se compararon 1,705 ventanas reales del Buen Fin con 6,538 ventanas de la misma forma en fechas sin eventos (15 de febrero, marzo, abril, julio, agosto y 1 de octubre, 2018–2025).

| Umbral (con P25) | % Buen Fin que cumple | % semanas normales | J de Youden | Lift |
|---|---|---|---|---|
| 2 % | 61.4 | 24.6 | 36.8 | 2.5 |
| 4 % | 60.1 | 22.7 | **37.4** | 2.6 |
| **5 %** | 58.2 | 21.3 | 36.9 | 2.7 |
| 10 % | 47.0 | 15.3 | 31.7 | 3.1 |

- **Por qué 5 %:** la separación es casi plana entre 1 % y 6 % y máxima en 4 %. Dentro de esa meseta, 5 % da menos falsas alarmas que 2 % (21.3 % contra 24.6 % de semanas normales). Con 10 % se pierde una de cada cinco rebajas reales.
- **Búsqueda fina:** se probaron 30 umbrales, de 0.5 % a 15 % en pasos de 0.5, con IC95 por remuestreo de series (500 repeticiones). El máximo es 4 % (J = 37.4, IC95 34.9–39.9). 2 %, 3.5 %, 4.5 % y 5 % no se distinguen estadísticamente de él, y entre ellos 5 % tiene la menor tasa de falsas alarmas (`reports/conclusiones/busqueda_fina_umbral.csv`).
- **Por qué P25:** exigir el cuartil inferior mejora J en todos los umbrales. Con 5 %, las falsas alarmas bajan de 23.5 % a 21.3 %.
- **Por qué 4 fechas:** con 4 días en la base, la mediana de referencia se equivoca 5 % o más en 10.1 % de las series (percentil 90 del error: 5.0 %). Con 3 días el percentil 90 sube a 5.6 %, y con 5 días se pierde cerca del 40 % de las series elegibles.
- **Etiqueta sin umbral:** cualquier bajada es 2.5 veces más frecuente en el Buen Fin que en semanas normales (J máxima entre 0 % y 1 %).
- **Estudio de evento:** el precio cae 2.8 % la semana previa y 9.4 % durante el evento, y vuelve a −0.8 % la semana siguiente.

## Esquema temporal y selección

- **Entrenamiento:** 2018–2023.
- **Validación móvil:** 2022, 2023 y 2024, cada año entrenado sólo con los años anteriores.
- **Criterio de selección:** la balanced accuracy promedio de validación, con el AUC para desempatar.
- **Prueba 2025:** se reentrena con 2018–2024.
- **Validación final 2026:** se reentrena con 2018–2025.
- **Intervalos de confianza:** IC95 por remuestreo de productos (1,000 repeticiones).

Se compararon 174 variantes:

| Familia | Mejor variante (validación) | Bal. acc. validación |
|---|---|---|
| **Árbol de decisión (elegido)** | profundidad 4, hoja ≥ 10, pesos balanceados, 8 variables + precio | **0.785** |
| Random Forest | profundidad 4, hoja ≥ 1, pesos balanceados | 0.775 |
| Línea base: regla simple | bajará si ya venía bajando en las 2 semanas previas | 0.755 |
| Random Forest + puntaje IF | profundidad 4, hoja ≥ 10 | 0.751 |
| Regresión logística | C = 10, pesos balanceados | 0.751 |
| Isolation Forest | contaminación 0.4, 50 % de variables por árbol | 0.694 |
| Línea base: clase mayoritaria | siempre "baja" | 0.500 |

## Resultados con datos que el modelo no vio

| Conjunto | Modelo | Accuracy | Bal. acc. (IC95) | Precisión | Recall | F1 | AUC |
|---|---|---|---|---|---|---|---|
| Prueba 2025 (n=93) | **Árbol de decisión** | 0.796 | **0.784** (0.68–0.87) | 0.921 | 0.806 | 0.859 | 0.787 |
| | Random Forest | 0.817 | 0.781 | 0.910 | 0.847 | 0.878 | 0.818 |
| | RF + puntaje IF | 0.860 | 0.792 | 0.904 | 0.917 | 0.910 | 0.821 |
| | Regla simple | 0.763 | 0.797 | 0.946 | 0.736 | 0.828 | 0.797 |
| | Regresión logística | 0.742 | 0.732 | 0.900 | 0.750 | 0.818 | 0.769 |
| | Isolation Forest | 0.785 | 0.743 | 0.894 | 0.819 | 0.855 | 0.804 |
| | Clase mayoritaria | 0.774 | 0.500 | 0.774 | 1.000 | 0.873 | 0.500 |
| 2026 · Preciómetro (n=187) | **Árbol de decisión** | 0.722 | **0.682** (0.62–0.74) | 0.704 | 0.909 | 0.794 | 0.709 |
| | Random Forest | 0.727 | 0.688 | 0.709 | 0.909 | 0.797 | 0.822 |
| | Regla simple | 0.727 | 0.718 | 0.766 | 0.773 | 0.769 | 0.718 |
| | Logística / IF / mayoritaria | 0.588 | 0.500 | 0.588 | 1.000 | 0.741 | — |
| 2026 · PROFECO (n=17) | Árbol de decisión | 0.824 | 0.762 | 0.923 | 0.857 | 0.889 | 0.869 |

## Lectura

1. El árbol supera claramente a la línea base "siempre baja" en datos futuros: balanced accuracy de 0.78 en 2025 y 0.68 en 2026, contra 0.50.
2. La variable que más pesa es `cambio_previo_pct` (73 % de la importancia): si el precio ya venía bajando en las dos semanas previas, probablemente baje en el evento.
3. La regla simple basada en esa variable compite con los modelos y los IC95 se traslapan. Es una línea base exigente, y así se explica en la presentación.
4. RF + puntaje IF tiene la mejor accuracy en 2025 (0.860), pero no fue el mejor en validación y es más débil en 2026. Elegirlo por la prueba habría sido sobreajustar.
5. La regresión logística y el Isolation Forest no generalizan a Preciómetro: predicen "baja" para todo. Las variables de conteo tienen otra escala en esa fuente (mediana de 46 días contra 5 en QQP); los árboles resisten mejor ese cambio.
6. Más ediciones ayudan. Con el mismo árbol, entrenar con 2018–2024 en lugar de sólo 2024 sube la balanced accuracy de 2025 de 0.757 a 0.784 y el AUC de 0.76 a 0.79.

## Artefactos

- `dataset_modelado.csv`: conjunto final de 1,909 series. La muestra de 10 instancias se toma de aquí con `random_state=42`.
- `seleccion_variantes.csv`, `validacion_por_fold.csv`, `variantes_elegidas.csv`, `metricas_finales.csv`, `predicciones.csv`, `importancia_variables.csv`.
- `umbral_*.csv`, `precision_referencia_fechas.csv`, `estudio_evento_semanal.csv` y figuras `fig_*.png`.
- Modelo serializado en `data/operacion/v2/modelo_final_20261126/modelo_final.joblib`. Su exportación sin dependencias para la API está en `data/operacion/v2/app_v3/modelo/arbol.json`; las pruebas verifican que coincide con scikit-learn.
