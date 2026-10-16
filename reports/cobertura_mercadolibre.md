# Cobertura · Mercado Libre México

Verificación en vivo: 2026-10-16, desde la PC local, sin token, con el user-agent académico del proyecto y pausa de 3–8 s.
Crudos: `data/raw/mercadolibre/2026-10-16/verificacion_*.gz`. Tabla: `data/cache/mercadolibre/verificacion_2026-10-16.json`.

## Resultado

**Filas obtenidas directamente de Mercado Libre: 0.** La fuente queda como `sin_credenciales` (API) y `bloqueado` (web).
No se declara integrada.

| # | Endpoint | HTTP | Respuesta |
|---|---|---|---|
| 1 | `/sites/MLM` | 403 | PolicyAgent: At least one policy returned UNAUTHORIZED |
| 2 | `/products/{id}` | 401 | authorization value not present |
| 3 | `/products/{id}/items` | 403 | PolicyAgent UNAUTHORIZED |
| 4 | `/items/{id}` | 403 | PolicyAgent UNAUTHORIZED |
| 5 | `/items?ids=...` | 401 | 401 Authorization Required (nginx) |
| 6 | `/items/{id}/prices` | 403 | PolicyAgent UNAUTHORIZED |
| 7 | `/items/{id}/sale_price` | 403 | PolicyAgent UNAUTHORIZED |
| 8 | `/sites/MLM/search?q=...` | 403 | forbidden |
| 9 | `/products/search?q=...` | 403 | PolicyAgent UNAUTHORIZED |
| 10 | `/highlights/MLM/category/{cat}` | 401 | unspecified_token |
| 11 | `/user-products/{id}` | 401 | Missing access token |
| 12 | `www.mercadolibre.com.mx/p/{id}` | 200 tras redirección | `/gz/account-verification` (muro de verificación de cuenta) |
| 13 | `articulo.mercadolibre.com.mx/MLM-{id}` | 200 tras redirección | `/gz/account-verification` |
| 14 | `listado.mercadolibre.com.mx/{texto}` | 200 tras redirección | `/gz/account-verification` |

IDs usados: catálogo `MLM41998828` e ítem `MLM2081699241` (Samsung Galaxy A06, tomados de las ofertas de Preciómetro).

Conclusión: **todos** los endpoints de precio y búsqueda exigen token, y las páginas públicas piden verificar cuenta.
Según las reglas del proyecto no se inicia sesión ni se evade la verificación.

## Qué hace hoy el colector (`src/sconto/fuentes/mercadolibre.py`)

- Sin credenciales: **una** petición diaria de sondeo a una página de catálogo para saber si el muro sigue; registra
  `bloqueado` o `sin_credenciales` en `data/estado/<entorno>.csv`. No hay reintentos en bucle.
- Con `ML_CLIENT_ID`, `ML_CLIENT_SECRET` y `ML_REFRESH_TOKEN` en `.env`: usa `/products/{id}/items`, `/items/{id}` y
  `/items/{id}/sale_price`, guarda el crudo y registra `precio` y `original_price`/`regular_amount` como precio tachado.
  El token se refresca solo y se guarda en `data/cache/mercadolibre/token.json` (fuera de git). **Este camino no está
  verificado en vivo**, porque el equipo decidió no registrar la app por ahora.

## Cómo llegan, aun así, precios de Mercado Libre al dataset

- **Preciómetro** (`preciometro_ofertas`, plataforma `Mercadolibre`): ofertas vigentes de vendedores de ML que el
  agregador sigue, con su ID de catálogo `MLM…`. Es evidencia de agregador (`metodo = agregador`), no de la API.
- **Wayback Machine** (2024–2025): páginas archivadas de producto de ML, con precio y precio anterior cuando aparecen.

## Decisión pendiente del equipo

Registrar una app gratuita en developers.mercadolibre.com.mx (sin tarjeta) daría precio vigente y precio original por
ítem y vendedor, todos los días, desde GitHub Actions. A considerar: el refresh token cambia en cada uso (el colector
guarda el nuevo), y en GitHub Actions habría que guardar las credenciales como *secrets* del repositorio. Conviene
revisar los términos de uso de la API antes de registrarla.

Costo: $0.
