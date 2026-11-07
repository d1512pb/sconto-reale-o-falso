"""Entrada portable y controles reproducibles para el notebook CRISP-DM."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pandas as pd

from sconto import dataset
from sconto.colab import cargar_paquete


def crear_entrada(paquete_gold, salida, fecha_corte):
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    gold = cargar_paquete(paquete_gold)
    originales = dataset.cargar_observaciones()
    fecha = pd.to_datetime(originales.fecha_captura, errors='coerce')
    originales = originales.loc[fecha.le(pd.Timestamp(fecha_corte)) | fecha.isna()].copy()
    manifest = {'formato': 'sconto-entrada-notebook-v1', 'fecha_corte': fecha_corte,
                'gold_sha256': hashlib.sha256(Path(paquete_gold).read_bytes()).hexdigest(), 'tablas': {}}
    tablas = {'bronze_observaciones': originales, 'productos': gold['productos'], 'eventos': gold['eventos']}
    temporal = salida.with_suffix('.tmp')
    with zipfile.ZipFile(temporal, 'w', compression=zipfile.ZIP_DEFLATED) as archivo:
        for nombre, datos in tablas.items():
            memoria = io.BytesIO()
            datos.to_parquet(memoria, index=False)
            contenido = memoria.getvalue()
            archivo.writestr(nombre + '.parquet', contenido)
            manifest['tablas'][nombre] = {'archivo': nombre + '.parquet', 'filas': len(datos),
                                         'sha256': hashlib.sha256(contenido).hexdigest()}
        archivo.writestr('entrada.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    temporal.replace(salida)
    return manifest


def cargar_entrada(ruta):
    tablas = {}
    with zipfile.ZipFile(ruta) as archivo:
        manifest = json.loads(archivo.read('entrada.json'))
        if manifest['formato'] != 'sconto-entrada-notebook-v1':
            raise ValueError('Formato de entrada desconocido')
        for nombre, info in manifest['tablas'].items():
            contenido = archivo.read(info['archivo'])
            if hashlib.sha256(contenido).hexdigest() != info['sha256']:
                raise ValueError(f'SHA-256 incorrecto: {nombre}')
            tablas[nombre] = pd.read_parquet(io.BytesIO(contenido))
            if len(tablas[nombre]) != info['filas']:
                raise ValueError(f'Conteo incorrecto: {nombre}')
    return tablas, manifest


def auditoria_limpieza(originales, validas, observaciones, exclusiones):
    capturas = int(observaciones.n_capturas.sum())
    if capturas + len(exclusiones) != len(originales):
        raise ValueError('La limpieza perdió capturas sin contabilizarlas')
    if observaciones.obs_id.duplicated().any():
        raise ValueError('Observaciones duplicadas después de consolidar')
    conteos = pd.DataFrame([
        ('entrada_bronze', len(originales)), ('validas_antes_de_consolidar', len(validas)),
        ('exclusiones', len(exclusiones)), ('observaciones_consolidadas', len(observaciones)),
        ('capturas_representadas', capturas), ('capturas_repetidas_consolidadas', len(validas) - len(observaciones))
    ], columns=['etapa', 'filas'])
    return conteos


def comparar_gold(observaciones, gold):
    columnas = ['obs_id', 'serie_id', 'producto_canonico_id', 'precio', 'fecha_precio', 'fecha_captura', 'n_capturas']
    izquierda = observaciones[columnas].copy()
    derecha = gold['observaciones'][columnas].copy()
    for datos in (izquierda, derecha):
        for campo in ('fecha_precio', 'fecha_captura'):
            datos[campo] = pd.to_datetime(datos[campo]).dt.strftime('%Y-%m-%d')
    izquierda = izquierda.sort_values('obs_id').reset_index(drop=True)
    derecha = derecha.sort_values('obs_id').reset_index(drop=True)
    pd.testing.assert_frame_equal(izquierda, derecha, check_dtype=False)
    return len(izquierda)


def reconstruir(originales, productos, eventos, fecha_corte):
    validas, exclusiones = dataset.validar(originales, fecha_referencia=fecha_corte)
    observaciones = dataset.consolidar(validas)
    observaciones = dataset.mapear_productos(observaciones, productos)
    observaciones = dataset.asignar_series(observaciones)
    auditoria = auditoria_limpieza(originales, validas, observaciones, exclusiones)
    series = dataset.series_evento(observaciones, eventos)
    matriz, matriz_brecha, metadatos = dataset.matrices(series)
    gold = dict(observaciones=observaciones, exclusiones=exclusiones, productos=productos, eventos=eventos,
                series_evento=series, sensibilidad=dataset.sensibilidad(observaciones, eventos),
                matriz_modelo=matriz, matriz_modelo_brecha=matriz_brecha, metadatos_modelo=metadatos)
    return gold, auditoria


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold', type=Path, required=True)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--fecha-corte', required=True)
    argumentos = parser.parse_args()
    print(json.dumps(crear_entrada(argumentos.gold, argumentos.salida, argumentos.fecha_corte), ensure_ascii=False))
