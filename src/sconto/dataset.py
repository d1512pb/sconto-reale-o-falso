"""Fase 5: dataset final (data/gold/) a partir de bronze. Determinista: mismas entradas → mismas salidas.

    python -m sconto.dataset

Tablas (parquet; csv o csv.gz):
  observaciones      una fila por precio observado (formato largo), todas las fuentes salvo QQP nacional
  exclusiones        filas que no pasaron validación, con motivo (ninguna fila cruda se pierde en silencio)
  productos          catálogo canónico + mapeos + confianza (config/productos_objetivo.csv)
  eventos            BF2024, BF2025, BF2026 con D0 y ventanas
  series_evento      una fila por serie × evento; serie = producto × vendedor/sucursal × canal
  sensibilidad       series con cobertura de ahorro exigiendo 2, 3, 4 o 5 fechas base
  matriz_modelo      entrada para Isolation Forest (sin ids como variables) + metadatos_modelo
  matriz_modelo_brecha  misma idea con brecha_pp como 4a variable, sólo donde existe anuncio
  inpc               control de tendencia (si hay datos)
Reglas: no se imputa, no se rellena con 0, no se eliminan extremos (el IQR sólo marca `revisar_captura`).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from sconto.almacen import combinar_estados, hoy, leer_bronze
from sconto.esquema import CANALES, CLAVE, COLUMNAS, METODOS, TIPOS_ID
from sconto.eventos import cargar_eventos
from sconto.normalizar import id_estable
from sconto.rutas import CONFIG, GOLD

FUENTES_OBS = ['qqp_cdmx', 'preciometro', 'preciometro_ofertas', 'mercadolibre', 'amazon', 'wayback', 'commoncrawl',
               'promodescuentos', 'tiendas', 'liverpool', 'sears']
EXTRAS = ['serie_id', 'preciometro_producto_id', 'asin', 'mlm_producto', 'mlm_item']
MIN_BASE, MIN_AMPLITUD, MIN_EVENTO, MIN_PREVIO = 4, 21, 1, 2  # mínimos del Avance 1
UMBRALES_BRECHA = (5, 10, 15)


def cargar_observaciones() -> pd.DataFrame:
    partes = []
    for f in FUENTES_OBS:
        df = leer_bronze(f)
        if len(df):
            df = df[[c for c in COLUMNAS + EXTRAS if c in df.columns]].copy()
            df['fuente'] = df['fuente'].fillna(f)
            partes.append(df)
    if not partes:
        return pd.DataFrame(columns=COLUMNAS + EXTRAS)
    df = pd.concat(partes, ignore_index=True)
    for c in COLUMNAS + EXTRAS:
        if c not in df.columns:
            df[c] = pd.NA
    return df


def validar(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df['precio'] = pd.to_numeric(df.precio, errors='coerce')
    df['precio_anterior_anunciado'] = pd.to_numeric(df.precio_anterior_anunciado, errors='coerce')
    df['pct_descuento_anunciado'] = pd.to_numeric(df.pct_descuento_anunciado, errors='coerce')
    df['fecha_precio'] = pd.to_datetime(df.fecha_precio, errors='coerce').dt.normalize()
    df['fecha_captura'] = pd.to_datetime(df.fecha_captura, errors='coerce').dt.normalize()
    motivos = pd.Series('', index=df.index)
    for cond, m in [(df.precio.isna() | ~np.isfinite(df.precio) | df.precio.le(0), 'precio_no_positivo'),
                    (df.fecha_precio.isna(), 'fecha_invalida'),
                    (df.fecha_captura.isna(), 'captura_invalida'),
                    (df.fecha_precio.gt(pd.Timestamp(hoy())), 'fecha_futura'),
                    (df.fecha_precio.gt(df.fecha_captura), 'precio_posterior_a_captura'),
                    (df.pct_descuento_anunciado.notna() & ~df.pct_descuento_anunciado.between(-100, 100), 'pct_fuera_de_rango'),
                    (df.precio_anterior_anunciado.notna() & df.precio_anterior_anunciado.le(0), 'precio_anterior_no_positivo'),
                    (df.id_externo.isna() | df.id_externo.fillna('').astype(str).str.strip().eq(''), 'sin_id_externo'),
                    (~df.metodo.isin(METODOS), 'metodo_invalido'),
                    (~df.canal.isin(CANALES), 'canal_invalido'),
                    (~df.tipo_id_externo.isin(TIPOS_ID), 'tipo_id_invalido')]:
        motivos = motivos.where(~cond | motivos.ne(''), m)
    excl = df.loc[motivos.ne('')].assign(motivo_exclusion=motivos[motivos.ne('')])
    return df.loc[motivos.eq('')].copy(), excl


def consolidar(df: pd.DataFrame) -> pd.DataFrame:
    """La misma clave vista en varias capturas (p. ej. el historial de 90 días de Preciómetro) se queda con la
    captura más reciente; se cuentan las capturas y si el precio cambió entre ellas (revisión de la fuente)."""
    df = df.sort_values(['fecha_captura', 'ruta_raw'], na_position='first')
    df['vendedor_o_cadena'] = df.vendedor_o_cadena.fillna('')
    df['vendedor_clave'] = df.vendedor_o_cadena.mask(df.tipo_precio.eq('minimo_diario_multitienda'), '')
    clave_revision = ['fuente', 'id_externo', 'fecha_precio', 'vendedor_clave']
    g = df.groupby(clave_revision, dropna=False)
    df['n_capturas'] = g.precio.transform('size')
    df['precio_revisado_por_fuente'] = g.precio.transform('nunique').gt(1)
    return df.drop_duplicates(clave_revision, keep='last').drop(columns='vendedor_clave').reset_index(drop=True)


def _explotar(productos: pd.DataFrame, col: str) -> dict:
    candidatos = {}
    for fila in productos.to_dict('records'):
        identidad_propia = col == 'preciometro_ids' and fila.get('origen') == 'preciometro'
        if fila.get('confianza_match') != 'exacto' and not identidad_propia:
            continue
        for identificador in str(fila.get(col) or '').split(';'):
            identificador = identificador.strip().upper()
            if identificador:
                candidatos.setdefault(identificador, set()).add(fila['producto_canonico_id'])
    return {clave: next(iter(valores)) for clave, valores in candidatos.items() if len(valores) == 1}


def mapear_productos(df: pd.DataFrame, productos: pd.DataFrame) -> pd.DataFrame:
    por_qqp = dict(zip(productos.qqp_producto_id.astype(str).str.upper(), productos.producto_canonico_id))
    por_pm, por_asin, por_mlm = (_explotar(productos, c) for c in ('preciometro_ids', 'asins', 'mlm_ids'))
    ide = df.id_externo.astype(str).str.upper()
    canon = pd.Series(pd.NA, index=df.index, dtype='object')
    t = df.tipo_id_externo
    canon = canon.mask(t.eq('qqp'), ide.map(por_qqp))
    canon = canon.mask(t.eq('preciometro'), ide.map(por_pm))
    canon = canon.mask(t.eq('preciometro_oferta'), df.preciometro_producto_id.astype(str).str.upper().map(por_pm))
    canon = canon.mask(t.eq('asin'), ide.map(por_asin))
    canon = canon.mask(t.isin(['mlm', 'mlm_item']), ide.map(por_mlm))
    if 'asin' in df:
        canon = canon.fillna(df.asin.astype(str).str.upper().map(por_asin))
    identificable = t.isin(['qqp', 'preciometro', 'preciometro_oferta', 'asin', 'mlm', 'mlm_item'])
    df['producto_canonico_id'] = df.producto_canonico_id.where(~identificable, canon)
    return df


def plataforma_serie(df: pd.DataFrame) -> pd.Series:
    """Las páginas archivadas (Wayback/Common Crawl) de una tienda se agrupan con la tienda: mismo canal y vendedor,
    distinto método de captura (el método queda en cada fila)."""
    url = df.url.fillna('').str.lower()
    p = df.fuente.copy()
    p = p.mask(df.fuente.eq('tiendas'), df.plataforma.fillna('tiendas'))
    archivada = df.fuente.isin(['wayback', 'commoncrawl'])
    for dominio, nombre in [('amazon.com.mx', 'amazon'), ('mercadolibre.com.mx', 'mercadolibre')]:
        p = p.mask(archivada & url.str.contains(dominio, regex=False), nombre)
    otros = archivada & ~p.isin(['amazon', 'mercadolibre'])
    p = p.mask(otros, 'archivo_' + url.str.extract(r'https?://(?:www\.)?([^/]+)', expand=False).fillna('web'))
    return p


def asignar_series(df: pd.DataFrame) -> pd.DataFrame:
    df['plataforma_serie'] = plataforma_serie(df)
    vend = df.vendedor_o_cadena.fillna('').astype(str)
    vend = vend.mask(vend.str.strip().eq(''), 'SIN_VENDEDOR_' + df.fuente)
    vend = vend.mask(df.tipo_precio.eq('minimo_diario_multitienda'), 'MINIMO_MULTITIENDA')
    vend = vend.mask(df.fuente.eq('qqp_cdmx') & df.sucursal_id.notna(), df.sucursal_id.astype(str))
    df['vendedor_serie'] = vend
    ident = df.id_externo.astype(str) + '|' + df.moneda.fillna('SIN_MONEDA').astype(str)
    df['serie_id'] = [s if isinstance(s, str) and s and f == 'qqp_cdmx' else id_estable([p, i, v, c])
                      for s, f, p, i, v, c in zip(df.serie_id, df.fuente, df.plataforma_serie, ident,
                                                  df.vendedor_serie, df.canal.fillna(''))]
    # Posibles errores de captura (no se borran): fuera de 1.5×IQR de la propia serie
    if df.empty:
        df['revisar_captura'] = pd.Series(dtype=bool)
        return df
    q = df.groupby('serie_id').precio.quantile([.25, .75]).unstack()
    iqr = (q[.75] - q[.25]).reindex(df.serie_id).to_numpy()
    lo, hi = q[.25].reindex(df.serie_id).to_numpy() - 1.5 * iqr, q[.75].reindex(df.serie_id).to_numpy() + 1.5 * iqr
    df['revisar_captura'] = (df.precio.to_numpy() < lo) | (df.precio.to_numpy() > hi)
    return df


def pct_anunciado(df: pd.DataFrame) -> pd.Series:
    """Descuento que la fuente ANUNCIA: el % mostrado o, si sólo muestra precio tachado, el implícito en él."""
    implicito = 100 * (1 - df.precio / df.precio_anterior_anunciado)
    return df.pct_descuento_anunciado.where(df.pct_descuento_anunciado.notna(), implicito)


def series_evento(obs: pd.DataFrame, eventos: pd.DataFrame, min_base=MIN_BASE) -> pd.DataFrame:
    obs = obs.assign(pct_anunciado=pct_anunciado(obs))
    meta_cols = ['fuente', 'plataforma_serie', 'metodo', 'canal', 'tipo_precio', 'producto_canonico_id', 'id_externo',
                 'tipo_id_externo', 'vendedor_serie', 'marca', 'modelo_normalizado', 'descripcion_original', 'estado',
                 'alcaldia']
    obs = obs.groupby(['serie_id', 'fecha_precio'], as_index=False, dropna=False).agg(
        precio=('precio', 'median'), pct_anunciado=('pct_anunciado', 'median'),
        **{columna: (columna, 'first') for columna in meta_cols})
    salidas = []
    for ev in eventos.itertuples():
        sub = obs.loc[obs.fecha_precio.between(ev.base_inicio, ev.posterior_fin)].copy()
        if not len(sub):
            continue
        sub['ventana'] = np.select(
            [sub.fecha_precio.between(ev.base_inicio, ev.base_fin), sub.fecha_precio.between(ev.previo_inicio, ev.previo_fin),
             sub.fecha_precio.between(ev.evento_inicio, ev.evento_fin)], ['base', 'previo', 'evento'], 'posterior')
        meta = sub.sort_values('fecha_precio').groupby('serie_id')[meta_cols].first()
        meta['metodos'] = sub.groupby('serie_id').metodo.agg(lambda s: ';'.join(sorted(set(s.dropna()))))
        for v in ('base', 'previo', 'evento', 'posterior'):
            w = sub.loc[sub.ventana.eq(v)].groupby('serie_id')
            meta = meta.join(w.agg(**{f'n_{v}': ('fecha_precio', 'nunique'), f'mediana_{v}': ('precio', 'median'),
                                      f'minimo_{v}': ('precio', 'min'), f'inicio_{v}': ('fecha_precio', 'min'),
                                      f'fin_{v}': ('fecha_precio', 'max')}))
            meta[f'n_{v}'] = meta[f'n_{v}'].fillna(0).astype(int)
        base = sub.loc[sub.ventana.eq('base')]
        cuart = base.groupby('serie_id').precio.quantile([.25, .75]).unstack()
        anuncio = sub.loc[sub.ventana.eq('evento') & sub.pct_anunciado.notna()].groupby('serie_id').pct_anunciado
        meta['amplitud_base_dias'] = (meta.fin_base - meta.inicio_base).dt.days
        meta['cobertura_ahorro'] = meta.n_base.ge(min_base) & meta.amplitud_base_dias.ge(MIN_AMPLITUD) & meta.n_evento.ge(MIN_EVENTO)
        meta['vendedor_confirmado'] = ~meta.vendedor_serie.str.startswith('SIN_VENDEDOR_')
        meta['cobertura_ahorro'] &= meta.vendedor_confirmado
        meta['cobertura_alza'] = meta.cobertura_ahorro & meta.n_previo.ge(MIN_PREVIO)
        meta['ahorro_historico_pct'] = (100 * (1 - meta.mediana_evento / meta.mediana_base)).where(meta.cobertura_ahorro)
        meta['alza_previa_pct'] = (100 * (meta.mediana_previo / meta.mediana_base - 1)).where(meta.cobertura_alza)
        meta['bajada_desde_previo_pct'] = (100 * (1 - meta.mediana_evento / meta.mediana_previo)).where(meta.cobertura_alza)
        if len(cuart):
            meta['variabilidad_base_pct'] = (100 * (cuart.get(.75) - cuart.get(.25)) / meta.mediana_base).where(meta.cobertura_ahorro)
        else:
            meta['variabilidad_base_pct'] = np.nan
        meta['n_anuncio_evento'] = anuncio.size().reindex(meta.index).fillna(0).astype(int)
        meta['descuento_anunciado_pct'] = anuncio.median().reindex(meta.index)
        meta['brecha_pp'] = (meta.descuento_anunciado_pct - meta.ahorro_historico_pct).where(
            meta.cobertura_ahorro & meta.descuento_anunciado_pct.notna())
        for u in UMBRALES_BRECHA:  # etiqueta DERIVADA por regla, no verdad
            meta[f'regla_descuento_inflado_{u}pp'] = (meta.brecha_pp > u).where(meta.brecha_pp.notna())
        meta.insert(0, 'evento_id', ev.evento_id)
        salidas.append(meta.reset_index())
    if not salidas:
        return pd.DataFrame()
    se = pd.concat(salidas, ignore_index=True)
    se.insert(0, 'serie_evento_id', [id_estable([s, e]) for s, e in zip(se.serie_id, se.evento_id)])
    return se


def sensibilidad(obs: pd.DataFrame, eventos: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for k in (2, 3, 4, 5):
        se = series_evento(obs, eventos, min_base=k)
        if not len(se):
            continue
        g = se.groupby(['evento_id', 'plataforma_serie'])
        filas.append(pd.DataFrame({'min_fechas_base': k, 'series_cobertura_ahorro': g.cobertura_ahorro.sum(),
                                   'series_cobertura_alza': g.cobertura_alza.sum(),
                                   'series_con_brecha': g.brecha_pp.count()}).reset_index())
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()


def matrices(se: pd.DataFrame):
    cols = ['ahorro_historico_pct', 'alza_previa_pct', 'variabilidad_base_pct']
    sel = se.loc[se.cobertura_alza].set_index('serie_evento_id')
    X = sel[cols].astype(float).dropna()
    Xb = sel.loc[sel.brecha_pp.notna(), cols + ['brecha_pp']].astype(float).dropna()
    meta = sel.drop(columns=cols + ['brecha_pp'], errors='ignore').loc[X.index]
    return X, Xb, meta


def _guardar(nombre: str, df: pd.DataFrame, manifiesto: dict, csv_gz=False):
    GOLD.mkdir(parents=True, exist_ok=True)
    p = GOLD / f'{nombre}.parquet'
    df.to_parquet(p, index=df.index.name is not None)
    c = GOLD / (f'{nombre}.csv.gz' if csv_gz else f'{nombre}.csv')
    df.to_csv(c, index=df.index.name is not None, encoding='utf-8')
    manifiesto['tablas'][nombre] = dict(filas=len(df), columnas=len(df.columns), parquet=p.name, csv=c.name,
                                        sha256_parquet=hashlib.sha256(p.read_bytes()).hexdigest())


def construir() -> dict:
    combinar_estados()
    productos = pd.read_csv(CONFIG / 'productos_objetivo.csv', dtype=str, keep_default_na=False)
    productos['prioridad'] = pd.to_numeric(productos.prioridad)
    eventos = cargar_eventos()
    originales = cargar_observaciones()
    obs, excl = validar(originales)
    obs = consolidar(obs)
    obs = mapear_productos(obs, productos)
    obs = asignar_series(obs)
    se = series_evento(obs, eventos)
    sens = sensibilidad(obs, eventos)
    X, Xb, meta = matrices(se) if len(se) else (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    obs['fecha_precio'] = obs.fecha_precio.dt.date.astype(str)
    obs['fecha_captura'] = obs.fecha_captura.dt.date.astype(str)
    man = dict(construido_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'), tablas={},
               fuentes={f: int(n) for f, n in obs.fuente.value_counts().items()})
    man['contabilizacion'] = dict(filas_bronze=len(originales), filas_excluidas=len(excl),
                                 capturas_representadas=int(obs.n_capturas.sum()))
    if man['contabilizacion']['capturas_representadas'] + len(excl) != len(originales):
        raise ValueError('Faltan filas en la contabilización bronze → gold/exclusiones')
    _guardar('observaciones', obs, man, csv_gz=True)
    _guardar('exclusiones', excl, man, csv_gz=True)
    _guardar('productos', productos, man)
    _guardar('eventos', eventos, man)
    _guardar('series_evento', se, man)
    _guardar('sensibilidad', sens, man)
    _guardar('matriz_modelo', X, man)
    _guardar('matriz_modelo_brecha', Xb, man)
    _guardar('metadatos_modelo', meta, man)
    inpc = leer_bronze('inpc')
    if len(inpc):
        _guardar('inpc', inpc, man)
    if len(se):
        man['series_evento'] = se.groupby(['evento_id', 'plataforma_serie']).agg(
            series=('serie_id', 'size'), cobertura_ahorro=('cobertura_ahorro', 'sum'),
            cobertura_alza=('cobertura_alza', 'sum'), con_brecha=('brecha_pp', 'count')).reset_index().to_dict('records')
    (GOLD / 'manifiesto.json').write_text(json.dumps(man, ensure_ascii=False, indent=2, default=int), encoding='utf-8')
    return man


if __name__ == '__main__':
    print(json.dumps(construir(), ensure_ascii=False, indent=2, default=int)[:4000])
