"""Genera DICCIONARIO.md a partir de data/gold/: descripción (escrita aquí) + tipo y rango observados (calculados).

    python -m sconto.diccionario
"""
from __future__ import annotations

import pandas as pd

from sconto.rutas import GOLD, RAIZ

D = {
    'observaciones': {
        '_': 'Una fila por precio observado (formato largo). Todas las fuentes salvo QQP nacional. Clave única: '
             '(fuente, id_externo, fecha_precio, vendedor_o_cadena).',
        'obs_id': ('Identificador estable de la observación (hash).', 'todas'),
        'fuente': ('Origen: qqp_cdmx, preciometro, preciometro_ofertas, mercadolibre, amazon, wayback, commoncrawl, promodescuentos.', 'todas'),
        'metodo': ('archivo_oficial | api | scraping | wayback | commoncrawl | agregador | comunidad.', 'todas'),
        'canal': ('tienda_fisica (QQP) | en_linea. Nunca se mezclan en una serie.', 'todas'),
        'tipo_precio': ('minimo_diario_multitienda (gráfico de Preciómetro: el más bajo entre tiendas ese día), '
                        'oferta_vigente, precio_vigente, observado_sucursal, etc.', 'todas'),
        'fecha_precio': ('Día al que corresponde el precio (en Wayback/Common Crawl, fecha del snapshot).', 'todas'),
        'fecha_captura': ('Día en que se descargó.', 'todas'),
        'producto_canonico_id': ('Producto canónico de config/productos_objetivo.csv; vacío si no se emparejó.', 'derivado'),
        'id_externo': ('Id en la fuente: producto_id QQP, id de ficha u oferta Preciómetro, ASIN, MLM.', 'todas'),
        'tipo_id_externo': ('qqp | preciometro | preciometro_oferta | asin | mlm | mlm_item | url.', 'todas'),
        'marca': ('Marca según la fuente.', 'todas'),
        'modelo_normalizado': ('Código o nombre de modelo en mayúsculas sin espacios ni guiones.', 'derivado'),
        'descripcion_original': ('Texto original del producto en la fuente.', 'todas'),
        'plataforma': ('Tienda o marketplace (Amazon, Mercadolibre, Elektra, …) en fuentes en línea.', 'en línea'),
        'vendedor_o_cadena': ('Vendedor (en línea) o cadena + sucursal (QQP).', 'todas'),
        'sucursal_id': ('Sucursal QQP (hash de cadena, nombre, dirección y alcaldía, igual que el Avance 1).', 'QQP'),
        'estado': ('Entidad federativa (QQP).', 'QQP'),
        'alcaldia': ('Municipio/alcaldía (QQP).', 'QQP'),
        'precio': ('Precio observado de contado, MXN. Mayor que 0.', 'todas'),
        'precio_anterior_anunciado': ('Precio tachado / “Antes” / “Precio de lista” SÓLO si la fuente lo muestra.', 'en línea'),
        'pct_descuento_anunciado': ('% de descuento SÓLO si la fuente lo muestra; entre −100 y 100.', 'en línea'),
        'moneda': ('MXN.', 'todas'),
        'disponibilidad': ('Disponible, agotado, etc., según la fuente.', 'en línea'),
        'condiciones': ('JSON: MSI, cupón, envío, membresía (Prime), vendido/enviado por, marketplace.', 'en línea'),
        'url': ('URL del producto/oferta/archivo oficial.', 'todas'),
        'ruta_raw': ('Ruta del crudo (relativa a la raíz del repo; los voluminosos viven en la PC local).', 'todas'),
        'hash_raw': ('SHA-256 del crudo sin comprimir.', 'todas'),
        'serie_id': ('Serie = plataforma × id externo × vendedor/sucursal × canal (QQP: el serie_id del Avance 1).', 'derivado'),
        'plataforma_serie': ('Plataforma con la que se agrupa la serie (Wayback de Amazon se agrupa con amazon).', 'derivado'),
        'vendedor_serie': ('Vendedor de la serie (MINIMO_MULTITIENDA para el gráfico de Preciómetro; sucursal en QQP).', 'derivado'),
        'n_capturas': ('Cuántas capturas trajeron esa misma clave (el historial de 90 días se repite cada día).', 'derivado'),
        'precio_revisado_por_fuente': ('True si capturas distintas dieron precios distintos para la misma clave.', 'derivado'),
        'revisar_captura': ('True si el precio está fuera de 1.5×IQR de su serie: posible error, NO se borra.', 'derivado'),
    },
    'series_evento': {
        '_': 'Una fila por serie × evento (BF2024, BF2025, BF2026). Medianas sobre fechas observadas, sin imputar.',
        'serie_evento_id': ('Hash de serie_id + evento_id.', 'derivado'),
        'evento_id': ('BF2024 | BF2025 | BF2026.', 'config/eventos.yaml'),
        'n_base': ('Fechas distintas con precio en la base (D-60..D-15).', 'derivado'),
        'n_previo': ('Fechas en el previo (D-14..D-1).', 'derivado'),
        'n_evento': ('Fechas durante el evento.', 'derivado'),
        'n_posterior': ('Fechas en los 14 días posteriores (diagnóstico).', 'derivado'),
        'mediana_base': ('Mediana de precios de la base, MXN.', 'derivado'),
        'amplitud_base_dias': ('Días entre la primera y la última fecha base.', 'derivado'),
        'cobertura_ahorro': ('≥4 fechas base en ≥21 días y ≥1 en el evento (Avance 1).', 'derivado'),
        'cobertura_alza': ('cobertura_ahorro y ≥2 fechas en el previo.', 'derivado'),
        'vendedor_confirmado': ('Vendedor o sucursal presente; si falta, no se calcula ahorro de una supuesta tienda fija.', 'derivado'),
        'ahorro_historico_pct': ('100 × (1 − mediana evento / mediana base). Sólo con cobertura_ahorro.', 'derivado'),
        'alza_previa_pct': ('100 × (mediana previa / mediana base − 1). Sólo con cobertura_alza.', 'derivado'),
        'bajada_desde_previo_pct': ('100 × (1 − mediana evento / mediana previa). Sólo con cobertura_alza.', 'derivado'),
        'variabilidad_base_pct': ('100 × (P75 − P25) / mediana base.', 'derivado'),
        'n_anuncio_evento': ('Observaciones del evento con % o precio tachado mostrado.', 'derivado'),
        'descuento_anunciado_pct': ('Mediana en el evento del % mostrado o, si sólo hay tachado, 100 × (1 − precio/tachado).', 'derivado'),
        'brecha_pp': ('descuento_anunciado_pct − ahorro_historico_pct (puntos porcentuales).', 'derivado'),
        'regla_descuento_inflado_5pp': ('Etiqueta DERIVADA por regla: brecha_pp > 5. No es verdad verificada.', 'derivado'),
        'regla_descuento_inflado_10pp': ('Etiqueta derivada: brecha_pp > 10.', 'derivado'),
        'regla_descuento_inflado_15pp': ('Etiqueta derivada: brecha_pp > 15.', 'derivado'),
    },
    'productos': {'_': 'Catálogo canónico (config/productos_objetivo.csv): prioridad 1 = modelos de las 93 series, '
                       '2 = de las 298, 3 = resto QQP, 4 = fichas de Preciómetro sin equivalente QQP. confianza_match: '
                       'exacto | probable (revisión manual) | descartado | sin_candidato.'},
    'eventos': {'_': 'Eventos con D0 y ventanas base, previo, evento y posterior.'},
    'sensibilidad': {'_': 'Series con cobertura de ahorro/alza y con brecha, exigiendo 2, 3, 4 o 5 fechas base.'},
    'matriz_modelo': {'_': 'Entrada a Isolation Forest: ahorro_historico_pct, alza_previa_pct, variabilidad_base_pct '
                           'de las series con cobertura_alza. Índice serie_evento_id (no es variable).'},
    'matriz_modelo_brecha': {'_': 'Como matriz_modelo más brecha_pp, sólo donde hay anuncio.'},
    'metadatos_modelo': {'_': 'Descripciones, vendedores, fechas y conteos de las filas de matriz_modelo.'},
    'exclusiones': {'_': 'Filas bronze que no pasaron validación, con motivo_exclusion.'},
    'inpc': {'_': 'INPC de INEGI por genérico (control de tendencia nacional).'},
}


def _rango(s: pd.Series) -> str:
    s = s.dropna()
    if not len(s):
        return 'vacío'
    if pd.api.types.is_bool_dtype(s):
        return f'True {int(s.sum()):,} / False {int((~s).sum()):,}'
    if pd.api.types.is_numeric_dtype(s):
        return f'{s.min():,.2f} – {s.max():,.2f}'
    if pd.api.types.is_datetime64_any_dtype(s):
        return f'{s.min():%Y-%m-%d} – {s.max():%Y-%m-%d}'
    u = s.astype(str).unique()
    return ', '.join(sorted(u)[:8]) + (f' … ({len(u):,} distintos)' if len(u) > 8 else '') if len(u) <= 40 else f'{len(u):,} valores distintos'


def generar() -> str:
    partes = ['# Diccionario de datos (`data/gold/`)\n',
              'Tipos y rangos calculados sobre los datos actuales al generar este archivo '
              '(`python -m sconto.diccionario`). Los rangos describen lo observado, no límites teóricos.\n']
    for tabla, desc in D.items():
        p = GOLD / f'{tabla}.parquet'
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        partes.append(f'\n## {tabla}\n\n{desc.get("_", "")}\n\nFilas: {len(df):,}\n')
        partes.append('| Campo | Descripción | Tipo | Rango observado | Fuente |\n|---|---|---|---|---|')
        for c in ([df.index.name] if df.index.name else []) + list(df.columns):
            serie = df.index.to_series() if c == df.index.name else df[c]
            d, f = desc.get(c, ('', ''))
            e = lambda t: str(t).replace('|', r'\|')
            partes.append(f'| `{c}` | {e(d)} | {serie.dtype} | {e(_rango(serie))} | {f} |')
    texto = '\n'.join(partes) + '\n'
    (RAIZ / 'DICCIONARIO.md').write_text(texto, encoding='utf-8')
    return texto


if __name__ == '__main__':
    print(generar()[:2000])
