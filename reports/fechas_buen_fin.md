# Fechas del Buen Fin usadas en el análisis

Revisión: 2026-10-21.

| Evento | Inicio (D0) | Fin | Días | Fuente | Estado |
|---|---|---|---|---|---|
| BF2024 | 2024-11-15 | 2024-11-18 | 4 | Secretaría de Economía (anuncio oficial, según el planteamiento del equipo) | Tomado del prompt; pendiente citar el comunicado |
| BF2025 | 2025-11-13 | 2025-11-17 | 5 | Avance 1 (QQP 2025) y términos de JBL México Buen Fin 2025 | Verificado en el Avance 1 |
| BF2026 | 2026-11-13 | 2026-11-17 | 5 | SAT, Sorteo El Buen Fin 2026 | **Confirmado en fuente oficial del SAT** |

## BF2026

- El sitio oficial [elbuenfin.org](https://www.elbuenfin.org/) carga su contenido con JavaScript: sin navegador sólo
  devuelve el título "El Buen Fin", así que no se pudo leer ahí la fecha (no se usó ningún truco para evitarlo).
- Varias fuentes de prensa coinciden: 16ª edición, del **viernes 13 al martes 17 de noviembre de 2026**, coordinada
  por la Secretaría de Economía y Concanaco Servytur; el lunes 16 es día feriado (Revolución Mexicana).
  - [Bloomberg Línea](https://www.bloomberglinea.com/latinoamerica/mexico/buen-fin-2026-en-mexico-cuando-empieza-cuantos-dias-dura-y-que-dia-sera-festivo/)
  - [SDP Noticias](https://www.sdpnoticias.com/negocios/el-buen-fin-2026-fechas-oficiales-en-mexico/)
  - [N+](https://www.nmas.com.mx/economia/como-registrar-negocios-buen-fin-2026-para-participar-sorteo-260-mil-pesos/)
  - [Chilango](https://www.chilango.com/noticias/cuando-es-el-buen-fin-2026-fechas-novedades-registro-y-como-saber-que-tiendas-participan/amp/)
- Actualización del 21 de octubre: las [bases oficiales del SAT para tarjetahabientes](https://www.sat.gob.mx/minisitio/SorteoElBuenFin/tarjetahabientes.html)
  establecen compras participantes del **13 al 17 de noviembre de 2026** en los comercios registrados en El Buen Fin.
  Esto confirma el intervalo en una fuente gubernamental primaria; no se atribuye a una lectura de la portada con JavaScript.
- Si cambiara, basta editar `config/eventos.yaml` y
  reconstruir `data/gold/` (`python -m sconto.dataset`); las ventanas se recalculan solas.

## Ventanas BF2026 (relativas a D0 = 2026-11-13)

| Ventana | Desde | Hasta |
|---|---|---|
| Base (D-60..D-15) | 2026-09-14 | 2026-10-29 |
| Previo (D-14..D-1) | 2026-10-30 | 2026-11-12 |
| Evento | 2026-11-13 | 2026-11-17 |
| Posterior (diagnóstico) | 2026-11-18 | 2026-12-01 |

Nota operativa: el historial de Preciómetro cubre ~90 días hacia atrás. Bajado hoy (16 oct) cubre del 19 jul al
16 oct de 2026, así que la base completa del BF2026 (desde el 14 sep) ya está asegurada para todas las fichas
descargadas; seguiría a salvo aunque se dejara de bajar hasta ~12 dic.
