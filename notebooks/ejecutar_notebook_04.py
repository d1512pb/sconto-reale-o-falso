"""Reproduce el notebook v2 en un kernel local nuevo con el corte completo."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from jupyter_client import KernelManager
from nbclient import NotebookClient
import nbformat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for nombre in ('cuaderno', 'gold', 'bronze', 'profeco', 'salida'):
        parser.add_argument('--' + nombre, type=Path, required=True)
    args = parser.parse_args()
    salida = args.salida.resolve()
    salida.mkdir(parents=True, exist_ok=False)
    archivos = {clave: str(getattr(args, clave).resolve(strict=True)) for clave in ('gold', 'bronze', 'profeco')}
    os.environ.update(SCONTO_V2_MODO='preparacion_fijada', SCONTO_V2_SNAPSHOT=archivos['gold'],
                      SCONTO_V2_BRONZE=archivos['bronze'], SCONTO_V2_PROFECO=archivos['profeco'],
                      SCONTO_V2_SALIDA=str(salida / 'entrega'))
    cuaderno = nbformat.read(args.cuaderno, as_version=4)
    kernel = KernelManager(kernel_name='python3')
    kernel.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
    cliente = NotebookClient(cuaderno, km=kernel, timeout=900, startup_timeout=60,
                             resources={'metadata': {'path': str(salida)}})
    cliente.on_cell_start = lambda cell, cell_index: print(f'Celda {cell_index + 1}', flush=True)
    try:
        cliente.execute()
    finally:
        nbformat.write(cuaderno, salida / '04_Sconto_CRISP_DM_v2_ejecutado.ipynb')


if __name__ == '__main__':
    main()
