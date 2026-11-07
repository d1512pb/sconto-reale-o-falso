"""Ejecuta el notebook entero en un kernel nuevo y conserva su auditoría local."""
import os
from pathlib import Path
import sys

from jupyter_client import KernelManager
import nbformat
from nbclient import NotebookClient

raiz = Path(__file__).resolve().parents[1]
os.environ['SCONTO_LOCAL_REPO'] = str(raiz)
os.environ['SCONTO_TRABAJO'] = str(raiz / 'data/analitica/notebook_2026-11-07')
os.environ['SCONTO_PAQUETE_LOCAL'] = str(raiz / 'data/cache/entrada_notebook_2026-11-07/sconto_colab_2026-11-07.zip')
os.environ['SCONTO_ENTRADA_LOCAL'] = str(raiz / 'data/exportaciones/sconto_entrada_notebook_2026-11-07.zip')
cuaderno = nbformat.read(raiz / 'notebooks/03_Sconto_CRISP_DM_ETL_web.ipynb', as_version=4)
kernel = KernelManager(kernel_name='python3')
kernel.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
cliente = NotebookClient(cuaderno, km=kernel, timeout=1200, resources={'metadata': {'path': str(raiz)}})
cliente.on_cell_start = lambda cell, cell_index: print(f'Celda {cell_index + 1}/{len(cuaderno.cells)}: {cell.cell_type}', flush=True)
salida = raiz / 'notebooks/ejecutados/03_Sconto_CRISP_DM_ETL_web_2026-11-07.ipynb'
salida.parent.mkdir(parents=True, exist_ok=True)
try:
    cliente.execute()
finally:
    nbformat.write(cuaderno, salida)
print('Ejecución completa:', salida)
