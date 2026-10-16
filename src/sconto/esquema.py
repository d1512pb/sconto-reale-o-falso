"""Esquema común de `observaciones` (formato largo). Todas las fuentes emiten estas columnas en bronze."""
from __future__ import annotations

import hashlib
import json

import pandas as pd

METODOS = {'archivo_oficial', 'api', 'scraping', 'wayback', 'commoncrawl', 'agregador', 'comunidad'}
CANALES = {'tienda_fisica', 'en_linea'}
TIPOS_ID = {'mlm', 'mlm_item', 'asin', 'qqp', 'preciometro', 'preciometro_oferta', 'url'}

COLUMNAS = [
    # identificación
    'obs_id', 'fuente', 'metodo', 'canal', 'tipo_precio',
    # fechas
    'fecha_precio', 'fecha_captura',
    # producto
    'producto_canonico_id', 'id_externo', 'tipo_id_externo', 'marca', 'modelo_normalizado', 'descripcion_original',
    # vendedor y lugar
    'plataforma', 'vendedor_o_cadena', 'sucursal_id', 'estado', 'alcaldia',
    # precio
    'precio', 'precio_anterior_anunciado', 'pct_descuento_anunciado', 'moneda', 'disponibilidad', 'condiciones',
    # trazabilidad
    'url', 'ruta_raw', 'hash_raw',
]

# Clave de unicidad: una fuente no puede dar dos precios del mismo id externo, día y vendedor.
CLAVE = ['fuente', 'id_externo', 'fecha_precio', 'vendedor_o_cadena']


def obs_id(fila: dict) -> str:
    base = [str(fila.get(c) or '') for c in ('fuente', 'id_externo', 'fecha_precio', 'vendedor_o_cadena', 'tipo_precio')]
    return hashlib.sha256(json.dumps(base).encode()).hexdigest()[:20]


def condiciones_json(**kw) -> str | None:
    limpio = {k: v for k, v in kw.items() if v not in (None, '', [], {})}
    return json.dumps(limpio, ensure_ascii=False, sort_keys=True) if limpio else None


def a_dataframe(filas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(filas)
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = pd.NA
    if len(df):
        df['obs_id'] = [obs_id(r) for r in df.to_dict('records')]
    extra = [c for c in df.columns if c not in COLUMNAS]
    return df[COLUMNAS + extra]
