# Conciliación de Sconto v2 · corte 14 de noviembre de 2026

La prueba de conciliación existente se conservó íntegra. La repetí con una copia aislada de gold del 7 de noviembre y bronze del 10. Falló con 1,015,811 capturas representadas, cero exclusiones y 1,071,337 filas bronze, tal como registró la auditoría. La copia gold del 7 tiene 683,942 observaciones consolidadas.

Las 55,526 capturas de diferencia corresponden a los días 8–10 de noviembre. La comparación por fuente identificó 53,100 entradas del histórico de Preciómetro, 2,423 de ofertas y tres de la fuente tiendas. Las otras fuentes no registraron diferencia. Esto explica la falla por corte desigual, con evidencia en `contraste_cortes.csv`, `capturas_entre_cortes.csv` y el log de la prueba fallida. En el checkout principal ya había un gold del 10 de noviembre cuando comenzó esta auditoría.

## Reconstrucción del corte 14

Se copiaron byte por byte las particiones bronze y la configuración de la revisión operativa `86fc75b` a `data/operacion/v2/corte_2026-11-14_v2`. Se verificó SHA-256 antes y después de cada copia. El ETL diario generó en esa carpeta 690,891 observaciones gold que representan las 1,145,401 filas bronze, con cero exclusiones y diferencia cero en las seis fuentes.

Las nueve tablas resultantes coincidieron con el paquete publicado del mismo corte, incluyendo observaciones, exclusiones, catálogo, ventanas, series, sensibilidad y entradas de los modelos. Se compararon todas sus celdas y sus índices. La prueba existente pasó en la carpeta separada. Las primeras ocho pruebas pasaron con una omisión por la ubicación de la matriz Avance 1. En una segunda ejecución, al proporcionar explícitamente la ruta original de esa matriz como fixture de solo lectura, pasaron las nueve pruebas.

El paquete público de referencia lleva SHA-256 `9fc3bf271f54037ee7180e297de61fe551715b1ec22ea7d57af82dea76ea5e79`. La entrada privada de reconstrucción lleva SHA-256 `4814d5339e2c896ee71c75b06e17291c5c3054815dea580961324a7cba96b064`. El manifiesto local guarda los hashes de cada partición, la revisión de origen y la lista de tablas verificadas. Los datos y entregas congelados se conservaron.

## Reproducción en el notebook 04

- `descarga_fijada` usa el gold público verificado del 14 de noviembre. `reproduccion` usa una copia local de ese gold.
- `preparacion_fijada` comprueba la entrada bronze privada, ejecuta validación, exclusiones, consolidación, mapeo y series con las funciones del ETL, y compara las tablas con gold antes de analizar.
- La consulta especial de PROFECO tiene un ZIP privado versionado para el 14 de noviembre. Conserva 2,211 precios diarios y 15 exclusiones. Elimina direcciones, nombres de sucursal, códigos postales y rutas crudas de la copia. Preserva la identidad de sucursal mediante referencias opacas dentro del corte y reproduce los agregados de ambas zonas. SHA-256 `84be1ca16529f6aa3cc8b36b5b1a647874d45d52499d4b4bed388178f1cbcba2`.
- El notebook indica si falta esa entrada. Cuando se suministra, exporta los precios y las exclusiones separados de la capa online. En Colab, se pueden cargar los ZIP privados en el panel Archivos de un runtime con acceso autorizado. El [gold de referencia](https://github.com/d1512pb/sconto-reale-o-falso/releases/download/datos/sconto_colab_2026-11-14.zip) tiene descarga fijada.

Se ejecutaron las ocho celdas de código en un kernel Jupyter local nuevo, incluyendo la comparación de las nueve tablas operativas. Se verificaron los hashes de los 69 archivos de entrega, la integridad y las claves foráneas de SQLite, y las 2,211 observaciones y 15 exclusiones oficiales. Se generaron cinco gráficas de cobertura, sensibilidad, calibración, matriz de confusión y evolución de precio. El árbol fijado para 2025 tuvo 15 verdaderos negativos, 6 falsos positivos, 14 falsos negativos y 58 verdaderos positivos. El cuaderno ejecutado quedó en `data/operacion/v2/notebook_04_conciliado`.

La ejecución en Colab alojado sigue pendiente. El acceso al navegador agotó el tiempo de espera y los ZIP privados permanecieron locales.
