"""Selecciona una lista fija y equilibrada; no realiza búsquedas ni consultas web."""
from __future__ import annotations

import argparse
from collections import deque

import pandas as pd

from sconto.rutas import CONFIG


def seleccionar(productos, lista, cantidad=200):
    referencias = productos.loc[productos.origen.eq('preciometro')].copy()
    referencias['preciometro_id'] = referencias.preciometro_ids.astype(str)
    datos = referencias.merge(lista, on='preciometro_id', suffixes=('_canonico', '_lista'))
    datos = datos.drop_duplicates('preciometro_id')
    datos['prioridad_lista'] = pd.to_numeric(datos.prioridad_lista)
    datos = datos.sort_values(['prioridad_lista', 'preciometro_id'])
    grupos = {familia: deque(grupo.to_dict('records')) for familia, grupo in datos.groupby('familia', sort=True)}
    salida = []
    while len(salida) < cantidad and any(grupos.values()):
        for grupo in grupos.values():
            if grupo and len(salida) < cantidad:
                fila = grupo.popleft()
                salida.append(dict(producto_canonico_id=fila['producto_canonico_id'],
                                   preciometro_id=fila['preciometro_id'], familia=fila['familia'],
                                   prioridad=fila['prioridad_lista'], url=fila['url']))
    return pd.DataFrame(salida)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cantidad', type=int, default=200)
    argumentos = parser.parse_args(argv)
    if not 150 <= argumentos.cantidad <= 300:
        parser.error('Usar entre 150 y 300 productos para la lista diaria')
    productos = pd.read_csv(CONFIG / 'productos_objetivo.csv', dtype=str, keep_default_na=False)
    lista = pd.read_csv(CONFIG / 'preciometro_lista.csv', dtype=str, keep_default_na=False)
    seleccion = seleccionar(productos, lista, argumentos.cantidad)
    seleccion.to_csv(CONFIG / 'preciometro_diarios.csv', index=False)
    print(seleccion.groupby('familia').size().to_string())
    print(f'Total: {len(seleccion)}; no se hicieron peticiones')


if __name__ == '__main__':
    main()
