"""Empaqueta gold para subirlo a Colab; no publica nada ni incluye crudos, tokens o rutas del equipo."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from sconto.almacen import ahora_utc, hoy
from sconto.rutas import DATA, GOLD


def empaquetar(gold: Path = GOLD, destino: Path | None = None) -> Path:
    manifiesto_gold = json.loads((gold / 'manifiesto.json').read_text(encoding='utf-8'))
    requeridas = {'observaciones', 'productos', 'eventos', 'series_evento', 'exclusiones'}
    if requeridas - set(manifiesto_gold['tablas']):
        raise ValueError('Dataset incompleto: reconstruir con python -m sconto.dataset')
    destino = destino or DATA / 'exportaciones' / f'sconto_colab_{hoy()}.zip'
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix('.zip.tmp')
    manifiesto = dict(formato='sconto-colab-v1', exportado_utc=ahora_utc(),
                      dataset_construido_utc=manifiesto_gold.get('construido_utc'), tablas={})
    with ZipFile(temporal, 'w', compression=ZIP_DEFLATED) as paquete:
        for nombre, descripcion in manifiesto_gold['tablas'].items():
            archivo = gold / descripcion['parquet']
            if archivo.parent.resolve() != gold.resolve():
                raise ValueError('El manifiesto apunta fuera de gold')
            contenido = archivo.read_bytes()
            digest = hashlib.sha256(contenido).hexdigest()
            if digest != descripcion['sha256_parquet']:
                raise ValueError(f'{nombre}: gold cambió después de construir el manifiesto')
            if len(pd.read_parquet(archivo)) != descripcion['filas']:
                raise ValueError(f'{nombre}: filas no coinciden')
            paquete.writestr(archivo.name, contenido)
            csv = gold / descripcion['csv']
            if csv.exists() and csv.parent.resolve() == gold.resolve():
                paquete.write(csv, csv.name)
            manifiesto['tablas'][nombre] = {'archivo': archivo.name, 'sha256': digest,
                                            'filas': descripcion['filas']}
        paquete.writestr('paquete.json', json.dumps(manifiesto, ensure_ascii=False, indent=2))
        paquete.write(Path(__file__).with_name('colab.py'), 'cargar_dataset.py')
    temporal.replace(destino)
    return destino


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino', type=Path)
    argumentos = parser.parse_args(argv)
    print(empaquetar(destino=argumentos.destino))


if __name__ == '__main__':
    main()
