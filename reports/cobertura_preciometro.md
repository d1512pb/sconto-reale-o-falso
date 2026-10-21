# Cobertura · Preciómetro

Generado 2026-10-21 desde `data/gold/observaciones` (no hay cifras a mano).

**Qué es:** cada ficha pública trae (a) un gráfico con **un punto por día**: el precio **mínimo entre tiendas** ese
día, con la tienda y el vendedor que lo ofrecían (ventana móvil de ~90 días); y (b) las **ofertas vigentes** por
tienda/vendedor el día de la captura, con enlaces que contienen ASIN de Amazon e ID de catálogo de Mercado Libre.
El gráfico **no** es la serie de una sola tienda: se analiza como serie `MINIMO_MULTITIENDA`, con la tienda en cada punto.

## Historial (gráfico)

- Fichas con historial: **2,795** · filas (ficha × día): **245,780**
- Rango obtenido: **2026-07-18 → 2026-10-20** · días con dato: **95**
- Puntos por ficha: mediana **90**, máximo **94**
- Tienda que tuvo el mínimo (top 8): Amazon 127,755, Mercadolibre 32,607, El Palacio de Hierro 15,070, Walmart 14,300, Cyberpuerta 13,602, Sam's Club 6,209, El Palacio De Hierro 5,753, Sanborns 5,166

## Ofertas vigentes (desde el 2026-10-16)

- Ofertas: **9,417** de **2,780** fichas;
  con ASIN: 2,462; con catálogo MLM: 1,157

## Emparejamiento con QQP

- Referencias QQP (prioridad 1–3): 231; con al menos una ficha de Preciómetro: **0**
  ().
- Fichas de tecnología sin equivalente QQP (prioridad 4): 1,493.

## Límites

- Ventana móvil: lo no descargado a tiempo se pierde por el extremo antiguo. La base del BF2026 (desde el
  2026-09-14) queda cubierta por la descarga del 16 oct; el BF2025 no está (el historial no llega a 2025).
- El precio es el que el agregador observó; no se verifica contra la tienda ni incluye precio tachado.
- Respeta robots.txt (sólo prohíbe /admin, /login, /register, /settings, /go/); 1 petición por ficha, 3–8 s.
- Costo: $0.
