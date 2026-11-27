"""Herramienta y firma del RAR anual de Quién es Quién en los Precios."""
import os
from pathlib import Path
import shutil

MAGIA_RAR = b'Rar!\x1a\x07'


def _tar() -> str:
    if os.name == 'nt':
        return str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'tar.exe')
    ejecutable = shutil.which('bsdtar')
    if not ejecutable:
        raise RuntimeError('Se requiere bsdtar (libarchive-tools) para leer el RAR en este entorno.')
    return ejecutable
