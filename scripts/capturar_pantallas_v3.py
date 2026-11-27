"""Capturas de la app v3 con Chrome sin ventana, para el reporte y la presentación.

Uso: python scripts/capturar_pantallas_v3.py --base http://localhost:8787 --salida "../../periodo 3/capturas"
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
CAPTURAS = [
    # nombre, ruta, ancho, alto, recorte (izq, arriba, der, abajo) o None
    ('01_inicio_escritorio', '/', 1366, 1000, None),
    ('02_filtro_prediccion_escritorio', '/#/?categoria=modelo', 1366, 1350, (0, 420, 1366, 1350)),
    ('03_precio_y_prediccion_escritorio', '/#/producto/P4-4054?precio=5499', 1366, 2300, None),
    ('04_tarjeta_modelo_escritorio', '/#/modelo', 1366, 2400, None),
    ('05_api_docs_escritorio', '/docs', 1366, 1150, None),
    ('06_inicio_celular', '/', 412, 915, None),
    ('07_precio_celular', '/#/producto/P4-2467?precio=799', 412, 2700, None),
]


def capturar(base: str, salida: Path) -> list[Path]:
    salida = Path(salida).resolve()
    salida.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre, ruta, ancho, alto, recorte in CAPTURAS:
        perfil = Path(tempfile.mkdtemp(prefix='sconto_chrome_'))
        destino = salida / f'{nombre}.png'
        try:
            subprocess.run([str(CHROME), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                            f'--user-data-dir={perfil}', f'--window-size={ancho},{alto}', '--virtual-time-budget=25000',
                            '--force-device-scale-factor=2' if ancho < 600 else '--force-device-scale-factor=1',
                            f'--screenshot={destino}', base.rstrip('/') + ruta],
                           check=True, capture_output=True, timeout=120)
        finally:
            shutil.rmtree(perfil, ignore_errors=True)
        if recorte:
            escala = 2 if ancho < 600 else 1
            with Image.open(destino) as img:
                img.crop(tuple(v * escala for v in recorte)).save(destino)
        rutas.append(destino)
        print(destino.name, Image.open(destino).size)
    return rutas


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', default='http://localhost:8787')
    ap.add_argument('--salida', type=Path, required=True)
    a = ap.parse_args()
    capturar(a.base, a.salida)
