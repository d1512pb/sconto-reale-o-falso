# Cobertura · Common Crawl

Fecha de la corrida: 2026-10-16 · Módulo: `src/sconto/fuentes/commoncrawl.py` · Costo: **0** (no se usó ningún servicio de pago).

## Estado: bloqueada por robots.txt (sin filas en bronze)

**No se declara integrada.** `data/bronze/commoncrawl/` no existe: 0 filas, 0 productos, sin rango de fechas.

La corrida real (`python -m sconto.fuentes.commoncrawl backfill --prioridad-max 3`, 141 objetivos) se detuvo
en la primera petición. `data/estado_fuentes.csv` quedó con `commoncrawl, 2026-10-16, bloqueado, 0`. Se hizo una
sola petición de red, la del `robots.txt` de `index.commoncrawl.org`; no se consultó el índice ni se leyó ningún WARC.
El robots.txt de `data.commoncrawl.org` ya se había leído antes ese mismo día, en el sondeo del intento anterior.

### Por qué se bloqueó (verificado el 2026-10-16)

| Host | robots.txt publicado | Efecto para nuestro user-agent |
|---|---|---|
| `index.commoncrawl.org` | `User-agent: *` · `Disallow: /` · `Allow: /$`, `/index.html$`, `/collinfo.json$`, `/graphinfo.json$`, … | Prohibidas las consultas al índice (`/CC-MAIN-AAAA-SS-index?url=…`), con cualquier forma de leer el archivo. |
| `data.commoncrawl.org` | `User-Agent: *` · `Disallow: /` | Prohibida la lectura de WARC por rango de bytes. |

Todo el tráfico pasa por `sconto.cliente.Cliente`, que respeta robots.txt y lanza `NoPermitido`. El módulo
registra `bloqueado` y termina. No hay reintentos en bucle ni rodeos (ni CloudFront directo, ni otro user-agent).

Además, `urllib.robotparser`, que usa `Cliente`, aplica la primera regla que coincide y no entiende `$`. Por eso
`collinfo.json` también aparece como prohibido, aunque bajo RFC 9309 (gana la regla más larga) sí estaría
permitido. Esto no cambia el resultado: las consultas al índice y a los WARC están prohibidas con cualquiera de
las dos lecturas.

## Qué quedó implementado y probado offline

- `CommonCrawl.crawls()` lee `collinfo.json` (caché diaria) y elige los crawls que tocan sep–dic de 2024 y de 2025 (`seleccionar_crawls`).
- `CommonCrawl.indice()` consulta el CDX de cada crawl (`output=json`, `filter==status:200`, `filter=~mime:html`) y pagina con `showNumPages`. Cada consulta queda en caché en `data/cache/commoncrawl/cdx/`.
- `CommonCrawl.registro()` pide `Range: bytes=offset-(offset+length-1)` a `data.commoncrawl.org`, lee el registro con `warcio` (`carga_warc`) y guarda el HTML con `guardar_crudo('commoncrawl', …)`. La ruta no depende del día de la corrida, así que re-ejecutar no vuelve a descargar.
- Objetivos, selección de capturas y parsers son los mismos de Wayback (`wayback.objetivos_producto`, `consultas_de`, `seleccionar`, `parsers_archivo`). Las filas salen con `metodo='commoncrawl'`, `fecha_precio` = fecha de la captura y en `condiciones` el archivo WARC, `offset`, `length` y crawl.
- El bronze no repite claves entre particiones; `registrar_estado` se llama en cada corrida (`ok`, `parcial`, `bloqueado` o `fallo`).
- Pruebas: `tests/test_commoncrawl.py` (6 pruebas, sin red). Cubren los robots.txt reales de ambos hosts, la selección de crawls, un WARC construido con `warcio` que envuelve una ficha real de Amazon recortada, la adaptación de filas, el estado `bloqueado` y la escritura sin duplicados. `tests/fixtures/commoncrawl/collinfo_formato.json` sólo reproduce el **formato** de `collinfo.json`: no se pudo descargar el real y sus ids son ilustrativos.

## Pendiente o no verificable

- No se sabe qué dominios aparecen en los crawls ni cuáles bloquean a CCBot. Hacía falta consultar el índice, y está prohibido.
- No se sabe cuántas fichas objetivo tienen capturas en los crawls de sep–dic 2024 y 2025.
- Alternativas descartadas por las reglas del proyecto: `s3://commoncrawl/` pide una cuenta de AWS (con tarjeta) y Amazon Athena es de pago.

## Decisión requerida

Common Crawl documenta el índice y `data.commoncrawl.org` como la vía pública de acceso, pero su robots.txt los
prohíbe a todo user-agent. El equipo debe decidir si ese robots.txt, pensado para rastreadores, aplica al uso
puntual de su API documentada.

- Si se mantiene la regla "respetar robots.txt", Common Crawl queda fuera y Wayback es la única fuente retroactiva.
- Si se decide otra cosa, tiene que quedar por escrito. El cambio de configuración le toca al equipo, no a este
  colector. El código no trae ninguna opción para ignorar robots.txt.

## Comando (reanudable e idempotente)

```
"/c/Users/danie/Documents/ESCOM/Semestre 7/Mineria  de datos/Sconto/SCRIPTS/.venv/Scripts/python.exe" -m sconto.fuentes.commoncrawl backfill --prioridad-max 3 --max-crawls 8 --limite-minutos 30
```

Mientras siga vigente ese robots.txt, este comando sólo registra `bloqueado` tras una petición (el robots.txt del índice).
