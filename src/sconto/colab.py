"""Carga un paquete local sin rutas de la PC, sin red y sin descomprimir archivos ejecutables."""
from __future__ import annotations

import hashlib
import io
import json
from zipfile import ZipFile

import pandas as pd


def cargar_paquete(ruta) -> dict[str, pd.DataFrame]:
    with ZipFile(ruta) as paquete:
        manifiesto = json.loads(paquete.read('paquete.json'))
        tablas = {}
        for nombre, descripcion in manifiesto['tablas'].items():
            contenido = paquete.read(descripcion['archivo'])
            if hashlib.sha256(contenido).hexdigest() != descripcion['sha256']:
                raise ValueError(f'SHA-256 incorrecto en {nombre}')
            tabla = pd.read_parquet(io.BytesIO(contenido))
            if len(tabla) != descripcion['filas']:
                raise ValueError(f'Número de filas incorrecto en {nombre}')
            tablas[nombre] = tabla
    return tablas
