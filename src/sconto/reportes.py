"""Reportes calculados desde data/gold (ninguna cifra a mano):

    python -m sconto.reportes            # cobertura_preciometro.md, resumen_recoleccion.md, registro_de_fuentes_actualizado.csv
"""
from __future__ import annotations

import csv
import json
from datetime import date

import pandas as pd

from sconto.rutas import CONFIG, ESTADO_FUENTES, GOLD, REPORTS, SCONTO


def cobertura(obs: pd.DataFrame) -> pd.DataFrame:
    """Por fuente: filas, productos, rango de fechas, días con dato y puntos por producto (mediana y máximo)."""
    filas = []
    for f, g in obs.groupby('fuente'):
        por_prod = g.groupby('id_externo').fecha_precio.nunique()
        filas.append(dict(fuente=f, metodo=';'.join(sorted(g.metodo.dropna().unique())), canal=';'.join(sorted(g.canal.dropna().unique())),
                          filas=len(g), ids_externos=g.id_externo.nunique(),
                          productos_canonicos=g.producto_canonico_id.nunique(),
                          desde=g.fecha_precio.min(), hasta=g.fecha_precio.max(), dias_con_dato=g.fecha_precio.nunique(),
                          puntos_por_id_mediana=float(por_prod.median()), puntos_por_id_max=int(por_prod.max()),
                          con_precio_tachado=int(g.precio_anterior_anunciado.notna().sum()),
                          con_pct_mostrado=int(g.pct_descuento_anunciado.notna().sum())))
    return pd.DataFrame(filas)


def _tabla_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lineas = ['| ' + ' | '.join(cols) + ' |', '|' + '---|' * len(cols)]
    for r in df.itertuples(index=False):
        lineas.append('| ' + ' | '.join(f'{v:,.0f}' if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer()
                                        else f'{v:,.1f}' if isinstance(v, float) else str(v) for v in r) + ' |')
    return '\n'.join(lineas)


def cobertura_preciometro(obs: pd.DataFrame, productos: pd.DataFrame) -> str:
    h = obs.loc[obs.fuente.eq('preciometro')]
    o = obs.loc[obs.fuente.eq('preciometro_ofertas')]
    if not len(h):
        return ''
    pp = h.groupby('id_externo').fecha_precio.nunique()
    plataformas = h.plataforma.value_counts()
    emp = productos.loc[productos.prioridad.le(3)]
    con_pm = emp.loc[emp.preciometro_ids.fillna('').ne('')]
    txt = f"""# Cobertura · Preciómetro

Generado {date.today().isoformat()} desde `data/gold/observaciones` (no hay cifras a mano).

**Qué es:** cada ficha pública trae (a) un gráfico con **un punto por día**: el precio **mínimo entre tiendas** ese
día, con la tienda y el vendedor que lo ofrecían (ventana móvil de ~90 días); y (b) las **ofertas vigentes** por
tienda/vendedor el día de la captura, con enlaces que contienen ASIN de Amazon e ID de catálogo de Mercado Libre.
El gráfico **no** es la serie de una sola tienda: se analiza como serie `MINIMO_MULTITIENDA`, con la tienda en cada punto.

## Historial (gráfico)

- Fichas con historial: **{h.id_externo.nunique():,}** · filas (ficha × día): **{len(h):,}**
- Rango obtenido: **{h.fecha_precio.min()} → {h.fecha_precio.max()}** · días con dato: **{h.fecha_precio.nunique()}**
- Puntos por ficha: mediana **{pp.median():.0f}**, máximo **{pp.max()}**
- Tienda que tuvo el mínimo (top 8): {', '.join(f'{k} {v:,}' for k, v in plataformas.head(8).items())}

## Ofertas vigentes (desde el {o.fecha_precio.min() if len(o) else '—'})

- Ofertas: **{len(o):,}** de **{o.preciometro_producto_id.nunique() if len(o) else 0:,}** fichas;
  con ASIN: {int(o.asin.notna().sum()) if len(o) else 0:,}; con catálogo MLM: {int(o.mlm_producto.notna().sum()) if len(o) else 0:,}

## Emparejamiento con QQP

- Referencias QQP (prioridad 1–3): {len(emp)}; con al menos una ficha de Preciómetro: **{len(con_pm)}**
  ({', '.join(f'{k}: {v}' for k, v in con_pm.confianza_match.value_counts().items())}).
- Fichas de tecnología sin equivalente QQP (prioridad 4): {int(productos.prioridad.eq(4).sum()):,}.

## Límites

- Ventana móvil: lo no descargado a tiempo se pierde por el extremo antiguo. La base del BF2026 (desde el
  2026-09-14) queda cubierta por la descarga del 16 oct; el BF2025 no está (el historial no llega a 2025).
- El precio es el que el agregador observó; no se verifica contra la tienda ni incluye precio tachado.
- Respeta robots.txt (sólo prohíbe /admin, /login, /register, /settings, /go/); 1 petición por ficha, 3–8 s.
- Costo: $0.
"""
    (REPORTS / 'cobertura_preciometro.md').write_text(txt, encoding='utf-8')
    return txt


HUECOS = [
    ('1. Precio anunciado / tachado', ['amazon', 'wayback', 'commoncrawl', 'mercadolibre', 'promodescuentos']),
    ('2. Más fuentes y eventos (BF2024–BF2026)', ['qqp_cdmx', 'preciometro', 'preciometro_ofertas', 'amazon', 'wayback', 'commoncrawl']),
    ('3. Amazon / Mercado Libre, por día y en el tiempo', ['amazon', 'mercadolibre', 'preciometro_ofertas', 'preciometro']),
    ('4. Días faltantes de QQP', ['preciometro', 'preciometro_ofertas', 'amazon']),
]


def resumen(obs, se, productos, man) -> str:
    cob = cobertura(obs)
    ev = se.groupby(['evento_id', 'plataforma_serie']).agg(series=('serie_id', 'size'),
        cobertura_ahorro=('cobertura_ahorro', 'sum'), cobertura_alza=('cobertura_alza', 'sum'),
        con_anuncio=('descuento_anunciado_pct', 'count'), con_brecha=('brecha_pp', 'count')).reset_index()
    est = pd.read_csv(ESTADO_FUENTES, dtype=str) if ESTADO_FUENTES.exists() else pd.DataFrame()
    huecos = []
    for nombre, fuentes in HUECOS:
        c = cob.loc[cob.fuente.isin(fuentes)]
        huecos.append(f'- **{nombre}**: ' + ('; '.join(f'{r.fuente} {r.filas:,} filas ({r.desde} → {r.hasta}, tachado {r.con_precio_tachado:,})'
                                                    for r in c.itertuples()) or 'sin filas todavía'))
    txt = f"""# Resumen de la recolección

Generado {date.today().isoformat()} desde `data/gold/` (construido {man.get('construido_utc')}). Cifras calculadas,
no escritas a mano. Resultados de **ejecución local** salvo que se indique otra cosa; las corridas de GitHub Actions
quedan en `data/estado/github.csv` y las de Colab no se cuentan aquí.

## Cobertura por fuente

{_tabla_md(cob)}

Una fuente sólo se considera integrada si tiene filas en `observaciones`. Detalle y límites de cada una en
`reports/cobertura_<fuente>.md`.

## Series por evento

{_tabla_md(ev)}

Mínimos del Avance 1 (≥4 fechas base en ≥21 días, ≥1 en el evento; alza: ≥2 en el previo). Sensibilidad con
2–5 fechas en `data/gold/sensibilidad`. El BF2026 aún no ocurre: sus series de evento se llenan del 13 al 17 nov.

## Qué cubre cada hueco del Avance 1

{chr(10).join(huecos)}

## Estado de las corridas

{_tabla_md(est.groupby(['fuente', 'entorno', 'estado']).size().reset_index(name='dias')) if len(est) else 'Sin corridas registradas.'}

## Productos objetivo

{_tabla_md(productos.groupby(['prioridad', 'confianza_match']).size().reset_index(name='productos'))}

Los emparejamientos `probable` están en `reports/matches_para_revisar.csv` para validación manual (Igor y Kevin).
"""
    (REPORTS / 'resumen_recoleccion.md').write_text(txt, encoding='utf-8')
    return txt


def registro_actualizado(obs: pd.DataFrame, notas: dict) -> None:
    """Copia del registro del Avance 1 + estado verificado de cada fuente. El original no se toca."""
    ruta_original = SCONTO / '02_registro_de_fuentes.csv'
    if not ruta_original.exists():
        ruta_original = CONFIG / 'registro_fuentes_avance1.csv'
    with open(ruta_original, encoding='utf-8') as archivo:
        original = list(csv.DictReader(archivo))
    cob = cobertura(obs).set_index('fuente')
    campos = list(original[0].keys()) + ['filas_obtenidas', 'rango_obtenido', 'estado_verificado']
    salida = [dict(r, filas_obtenidas='', rango_obtenido='', estado_verificado='sin cambio (registro del Avance 1)') for r in original]
    for fuente, n in notas.items():
        c = cob.loc[fuente] if fuente in cob.index else None
        salida.append(dict(fuente=n['nombre'], url=n['url'], costo_consulta=n.get('costo', 'Gratis'),
                           costo_api=n.get('costo_api', 'No aplica'), aporte=n['aporte'], estado_verificacion=n['estado'],
                           limitacion=n['limitacion'], uso_propuesto=n['uso'], fecha_revision=date.today().isoformat(),
                           filas_obtenidas=int(c.filas) if c is not None else 0,
                           rango_obtenido=f'{c.desde} / {c.hasta}' if c is not None else '',
                           estado_verificado='integrada' if c is not None and c.filas else n.get('estado_corto', 'sin filas')))
    with open(REPORTS / 'registro_de_fuentes_actualizado.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(salida)


def notas_fuentes() -> dict:
    ruta = REPORTS / 'notas_fuentes.json'
    return json.loads(ruta.read_text(encoding='utf-8')) if ruta.exists() else {}


def generar():
    obs = pd.read_parquet(GOLD / 'observaciones.parquet')
    se = pd.read_parquet(GOLD / 'series_evento.parquet')
    productos = pd.read_parquet(GOLD / 'productos.parquet')
    productos['prioridad'] = pd.to_numeric(productos.prioridad)
    man = json.loads((GOLD / 'manifiesto.json').read_text(encoding='utf-8'))
    cobertura_preciometro(obs, productos)
    resumen(obs, se, productos, man)
    registro_actualizado(obs, notas_fuentes())


if __name__ == '__main__':
    generar()
    print(REPORTS / 'resumen_recoleccion.md')
