"""Ejecuta el notebook final 06 en un kernel local nuevo con el paquete del corte y guarda la copia con resultados."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient

RAIZ = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cuaderno', type=Path, default=RAIZ / 'notebooks/06_Sconto_Final_CRISP_DM.ipynb')
    p.add_argument('--paquete', type=Path, default=RAIZ / 'data/operacion/v2/corte_final_20261126/sconto_colab_2026-11-26.zip')
    p.add_argument('--salida', type=Path, default=RAIZ / 'data/operacion/v2/notebook_06_ejecucion')
    a = p.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    os.environ['SCONTO_FINAL_PAQUETE'] = str(a.paquete.resolve(strict=True))
    cuaderno = nbformat.read(a.cuaderno, as_version=4)
    kernel = KernelManager(kernel_name='python3')
    kernel.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
    cliente = NotebookClient(cuaderno, km=kernel, timeout=1800, startup_timeout=90,
                             resources={'metadata': {'path': str(a.salida)}})
    cliente.on_cell_start = lambda cell, cell_index: print(f'Celda {cell_index + 1}/{len(cuaderno.cells)}', flush=True)
    try:
        cliente.execute()
    finally:
        nbformat.write(cuaderno, a.salida / '06_Sconto_Final_CRISP_DM_ejecutado.ipynb')
        print('Guardado', a.salida / '06_Sconto_Final_CRISP_DM_ejecutado.ipynb')


if __name__ == '__main__':
    main()
