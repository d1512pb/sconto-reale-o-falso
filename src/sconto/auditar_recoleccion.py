"""Verifica gold y exporta cobertura diaria y límites antes de pasar al análisis en Colab."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from sconto.almacen import hoy
from sconto.esquema import CLAVE
from sconto.rutas import GOLD, REPORTS


def comprobar(observaciones):
    errores = []
    if observaciones.duplicated(CLAVE).any():
        errores.append('claves_duplicadas')
    precios = pd.to_numeric(observaciones.precio, errors='coerce')
    if not (np.isfinite(precios) & precios.gt(0)).all():
        errores.append('precios_invalidos')
    fechas = pd.to_datetime(observaciones.fecha_precio, errors='coerce')
    capturas = pd.to_datetime(observaciones.fecha_captura, errors='coerce')
    if fechas.isna().any() or capturas.isna().any() or fechas.gt(pd.Timestamp(hoy())).any():
        errores.append('fechas_invalidas')
    porcentajes = observaciones.pct_descuento_anunciado.dropna()
    if not porcentajes.between(-100, 100).all():
        errores.append('porcentajes_invalidos')
    return errores


def cobertura_diaria(observaciones):
    return observaciones.groupby(['fuente', 'fecha_precio'], dropna=False).agg(
        filas=('precio', 'size'), ids_externos=('id_externo', 'nunique'),
        productos_canonicos=('producto_canonico_id', 'nunique'),
        con_precio_anterior=('precio_anterior_anunciado', 'count'),
        con_descuento_anunciado=('pct_descuento_anunciado', 'count')).reset_index()


def generar():
    manifiesto = json.loads((GOLD / 'manifiesto.json').read_text(encoding='utf-8'))
    tablas = {}
    for nombre, descripcion in manifiesto['tablas'].items():
        archivo = GOLD / descripcion['parquet']
        if archivo.parent.resolve() != GOLD.resolve():
            raise ValueError('El manifiesto apunta fuera de gold')
        if hashlib.sha256(archivo.read_bytes()).hexdigest() != descripcion['sha256_parquet']:
            raise ValueError(f'SHA-256 incorrecto: {nombre}')
        tablas[nombre] = pd.read_parquet(archivo)
        if len(tablas[nombre]) != descripcion['filas']:
            raise ValueError(f'Conteo incorrecto: {nombre}')
    observaciones = tablas['observaciones']
    errores = comprobar(observaciones)
    series = tablas['series_evento']
    originales = series.loc[series.evento_id.eq('BF2025') & series.plataforma_serie.eq('qqp_cdmx')]
    avance = dict(observaciones=int((observaciones.fuente.eq('qqp_cdmx') & observaciones.fecha_precio.str.startswith('2025')).sum()),
                  series_ahorro=int(originales.cobertura_ahorro.sum()), series_alza=int(originales.cobertura_alza.sum()))
    if tuple(avance.values()) != (39363, 298, 93):
        errores.append('avance1_no_reproducido')
    coberturas = []
    faltantes = {}
    for fuente, grupo in observaciones.groupby('fuente'):
        coberturas.append(dict(fuente=fuente, filas=len(grupo), ids_externos=grupo.id_externo.nunique(),
                               desde=grupo.fecha_precio.min(), hasta=grupo.fecha_precio.max(),
                               dias_con_dato=grupo.fecha_precio.nunique(), ultima_captura=grupo.fecha_captura.max(),
                               con_precio_anterior=int(grupo.precio_anterior_anunciado.notna().sum())))
        if fuente in ('tiendas', 'preciometro_ofertas'):
            dias = pd.date_range(grupo.fecha_precio.min(), hoy()).strftime('%Y-%m-%d')
            faltantes[fuente] = sorted(set(dias) - set(grupo.fecha_precio))
    resultado = dict(fecha_auditoria=hoy(), construido_utc=manifiesto['construido_utc'],
                     filas=len(observaciones), tablas={nombre: len(tabla) for nombre, tabla in tablas.items()},
                     errores=errores, cobertura_fuentes=coberturas, avance1=avance,
                     fechas_sin_observacion_no_imputadas=faltantes,
                     limites=['Amazon y Mercado Libre indirectos no son una captura verificada de su API.',
                              'Los cruces probables de modelos requieren validación humana de variante.',
                              'Los faltantes no se rellenan. Una captura no demuestra cobertura completa por producto.',
                              'Antes de concluir sobre BF2026, esperar el evento y comprobar cobertura de cada serie.'])
    REPORTS.mkdir(parents=True, exist_ok=True)
    cobertura_diaria(observaciones).to_csv(REPORTS / 'cobertura_por_fuente_y_dia.csv', index=False)
    (REPORTS / 'preparacion_siguiente_fase.json').write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    if errores:
        raise ValueError('Auditoría fallida: ' + ', '.join(errores))
    return resultado


if __name__ == '__main__':
    resultado = generar()
    print(json.dumps({'filas': resultado['filas'], 'errores': resultado['errores'], 'avance1': resultado['avance1']}))
