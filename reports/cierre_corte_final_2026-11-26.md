# Cierre de recolección y corte final · 26 de noviembre de 2026

A partir de este corte, el análisis final, la evaluación y la presentación usan sólo los datos congelados en `data/operacion/v2/corte_final_20261126/`. La auditoría completa está en [auditoria_corte_final_2026-11-26.md](auditoria_corte_final_2026-11-26.md), con su versión en JSON. `MANIFIESTO.json` contiene la huella SHA-256 de cada archivo del corte.

## 1. Qué se detuvo

| Proceso | Estado anterior | Estado final |
|---|---|---|
| Tarea de Windows «Sconto recoleccion diaria» (10:30 y 12:30) | Activa | **Desactivada** |
| Tarea «Sconto v2 Piloto PROFECO Buen Fin 2026» (17:00) | Activa | **Desactivada** |
| Tarea «Sconto v2 Vigilancia QQP» (domingos 12:05) | Activa | **Desactivada** |
| Tareas del buzón de cotizaciones y su reactivador | Desactivadas desde el 16 | Desactivadas |
| Workflow de GitHub «Recolección diaria de precios» | Programado (07:17 CDMX) | **Desactivado** (`disabled_manually`) |
| Colector en Fly | Nunca habilitado | Sin cambios: `SCONTO_COLECTOR_NUBE` no está definido |

Las tareas se desactivaron sin borrarse. Sus definiciones originales están en `tareas_antes/`. Para reactivarlas:

```powershell
Enable-ScheduledTask -TaskName 'Sconto v2 Piloto PROFECO Buen Fin 2026'
gh workflow enable "Recolección diaria de precios" -R d1512pb/sconto-reale-o-falso
```

Antes del cierre se hizo una última captura de PROFECO a las 11:21 CDMX. Fue parcial: 23 de 24 modelos, por un error de conexión en el producto 35051. No se perdió información, porque PROFECO no ha publicado precios posteriores al 17 de noviembre y ese modelo ya estaba completo en las capturas anteriores. La vigilancia de QQP respondió `sin_publicacion`.

## 2. Qué sigue en línea para la presentación (sólo consulta)

- **API en Fly** `sconto-v2-api`: una máquina de 256 MB y un volumen de 1 GB. Sirve el almacén congelado del 16 de noviembre y no recolecta. Este mes lleva 13.8 MB de salida, lejos del corte preventivo de 5 GB. El costo estimado es de unos US$2.5 al mes.
- **Web** en GitHub Pages: queda congelada en el último despliegue del 26 de noviembre (04:04 UTC), porque el workflow ya no publica.
- **APK 2.0.0**: carga esa misma web.

Se recomienda mantener la API hasta la presentación y después eliminar la app y su volumen. El volumen se cobra aunque la máquina esté detenida. La copia del volumen ya está en el corte (`fly/`).

```powershell
fly apps destroy sconto-v2-api
```

## 3. Resultado de la auditoría

**Integridad: sin hallazgos bloqueantes.** El paquete tiene 0 duplicados por clave, 0 precios no positivos y 0 fechas inválidas, y sus huellas coinciden con `paquete.json`. Se conserva la reproducción del Avance 1. El piloto pasa la integridad SQLite y las claves foráneas, sin conflictos de precio. Las pruebas de `tests/test_dataset.py` contra el almacén operativo dan 8 aprobadas y 1 omitida.

La prueba que falla en la raíz del repo compara `data/gold` del 10 de noviembre con un bronze más reciente. Es una copia atrasada, no un defecto del corte. Se corrige reconstruyendo ese gold o apuntando la prueba al almacén operativo.

| Conjunto | Contenido | Último dato |
|---|---|---|
| Histórico multifuente | 690,888 observaciones limpias, 1,724 productos. QQP 409,138; Preciómetro 251,438; ofertas del agregador 30,184; Wayback 109; tiendas 18; Amazon 1 | QQP 31 ago 2026; Preciómetro 14 nov 2026 |
| Piloto PROFECO Buen Fin 2026 | 3,144 precios únicos anuncio·fecha; 24 modelos; 85 sucursales; 718 anuncios producto×sucursal | Precio del 17 nov 2026 |
| Ofertas en línea verificadas | 0. Hay 17 capturas archivadas de Liverpool, sin vendedor ni inventario | — |
| QQP anual 2026 | Sin publicación nueva; el índice antiguo responde 404 | 31 ago 2026 |

Cobertura del Buen Fin 2026 (13–17 de noviembre):

- **Piloto PROFECO:** 1,300 precios en el evento, 1,238 en la base y 358 en el previo. **0 en el periodo posterior**, porque PROFECO dejó de publicar después del 17. Hay 197 anuncios con base, previo y evento.
- **Preciómetro:** 379 registros del mínimo multitienda y 1,578 anuncios del agregador durante el evento, sólo del 13 y 14, porque la fuente se pausó el 14. Hay 187 series con cobertura de base, previo y evento.
- **QQP:** cero series evaluables de 2026.

Huecos conocidos: no hubo captura del piloto el 25 de noviembre (la tarea se interrumpió), y la del 26 fue parcial. Ninguno de los dos pierde precios, porque el último día publicado sigue siendo el 17.

## 4. Estado de CRISP-DM

| Fase | Estado | Evidencia o pendiente |
|---|---|---|
| Comprensión del negocio | **Cerrada** | Pregunta, costo del error y abstención en `PLAN_SCONTO_V2.md` y `01_alcance_y_viabilidad.md` |
| Comprensión de los datos | **Cerrada con este corte** | Auditoría por fuente, año y ventana del evento |
| Preparación | **Cerrada** | ETL reproducible, paquete con huellas, conciliación del 14 de noviembre e integridad del corte |
| Modelado | Parcial | Regla base y sensibilidad, árbol BF2024→BF2025 e Isolation Forest. **Falta decidir el modelo 2026** (sección 5) |
| Evaluación | Parcial | La prueba retrospectiva 2025 está completa. 2026: QQP no es evaluable y no hay datos en línea. Queda la validación con el piloto |
| Despliegue | Casi cerrado | Web, APK y API operan. Pendiente: notebook 05 en Colab alojado, APK en un celular físico, integrar la v2 en `main` y publicar el release final |

## 5. Qué modelo nuevo permiten los datos del corte

- **Viable sólo como caso pequeño: aplicar el árbol fijado al piloto PROFECO.** El protocolo (`protocolo_modelo_v2.json`: entrenamiento BF2024, prueba BF2025, ocho variables, clase positiva «la mediana del evento queda por debajo de la mediana de los 14 días previos») exige al menos 4 fechas en la base con 21 días de amplitud, 2 fechas en el previo y 1 en el evento. De los 197 anuncios con las tres ventanas, **sólo 17 cumplen los mínimos, de 8 modelos**. En 14 de esos 17 el precio bajó en el evento. El límite lo pone el previo: 63 anuncios tienen dos fechas en él. Con n=17 se puede aplicar el árbol sin reajustarlo y mostrar su matriz de confusión como validación externa ilustrativa. No alcanza para métricas confiables, y es otra población: tecnología en sucursales de CDMX y la ZMVM, no la canasta QQP.
- **Alternativa con más muestra:** un modelo descriptivo o no supervisado sobre los 558 anuncios con precio en el evento. Por ejemplo, agrupar anuncios por su trayectoria de precio entre base, previo y evento, o aplicar Isolation Forest para detectar rebajas atípicas. Debe presentarse como análisis exploratorio, no como modelo evaluado.
- **Viable, descriptivo:** el patrón de «alza previa y rebaja en el evento» en las 187 series de Preciómetro y en las sucursales del piloto, para las hipótesis de mercado.
- **No viable:** el pronóstico posterior a siete días y cualquier evaluación del periodo del 18 de noviembre al 1 de diciembre, porque hay 0 datos posteriores. Tampoco es viable la evaluación de recomendaciones en línea, porque hay 0 ofertas verificadas.
