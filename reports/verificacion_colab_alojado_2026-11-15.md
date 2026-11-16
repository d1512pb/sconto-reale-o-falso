# Verificación de Sconto v2 en Colab alojado

El 15 de noviembre de 2026 se abrió el notebook de la revisión pública `1fffbb2b39427f6fbffbd137c7d9cc78f72e8e32` y se ejecutaron sus ocho celdas de código en un entorno nuevo de Google Compute Engine con Python 3. [Notebook fijado por commit](https://colab.research.google.com/github/d1512pb/sconto-reale-o-falso/blob/1fffbb2b39427f6fbffbd137c7d9cc78f72e8e32/notebooks/04_Sconto_CRISP_DM_v2.ipynb)

- Modo `descarga_fijada`. El paquete público superó la comprobación de SHA-256 `9fc3bf271f54037ee7180e297de61fe551715b1ec22ea7d57af82dea76ea5e79`. [Paquete usado](https://github.com/d1512pb/sconto-reale-o-falso/releases/download/datos/sconto_colab_2026-11-14.zip)
- El código embebido superó la comprobación de SHA-256 `706e6ad228d249a56ea9419cc25b0471d38dfa77025c98ea070d6a2ab8db7455`.
- La última celda imprimió `Entrega entrega_sconto_v2 · corte 2026-11-14 · registros limpios 690891`.
- El panel de archivos del entorno mostró 58 elementos en `/content/entrega_sconto_v2`: el manifiesto, SQLite, cinco gráficas y archivos tabulares. Las gráficas cubren matriz de confusión, calibración, cobertura, sensibilidad de la regla y una ficha histórica.

El modo rápido usa el gold público. La preparación desde bronze y la consulta especial de PROFECO requieren entradas privadas. La ejecución las omitió sin cargar archivos privados ni montar Drive. Sus resultados verifican el análisis histórico alojado, mientras que la paridad del motor operativo y la consulta a una API pública requieren sus propias pruebas.
