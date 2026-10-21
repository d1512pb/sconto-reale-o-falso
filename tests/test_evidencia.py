import gzip
import hashlib
import json

import pandas as pd

from sconto.evidencia import preservar, proyectar
from sconto.fuentes.preciometro import parsear


def test_proyeccion_excluye_reservas_y_reproduce_precios(tmp_path):
    dato = {'props': {'producto': {'id': 1, 'nombre': 'Bocina TEST', 'reservado_por': 'NO_PUBLICAR',
                                  'categoria': {'nombre': 'Audio', 'slug_path': 'tecnologia/audio', 'interno': 'NO_PUBLICAR'},
                                  'facetas': {'marca': 'Test', 'color': 'Negro', 'usuario': 'NO_PUBLICAR'}},
                      'resultados': [{'id': 4, 'precio_final': 100, 'vendedor': 'Tienda pública',
                                      'nombre': 'Bocina TEST', 'enlace': 'https://tienda.test/1',
                                      'tienda': {'nombre': 'Tienda', 'token': 'NO_PUBLICAR'}, 'cuenta': 'NO_PUBLICAR'}],
                      'datosGrafica': {'fechas': ['2026-10-20'], 'precios': [100], 'tiendas': ['Tienda'],
                                      'vendedores': ['Tienda pública']}, 'usuario': 'NO_PUBLICAR'}}
    contenido = json.dumps(dato).encode()
    limpio = proyectar(contenido)
    assert b'NO_PUBLICAR' not in limpio
    assert json.loads(limpio)['sha256_respuesta_original'] == hashlib.sha256(contenido).hexdigest()
    argumentos = ('https://preciometro.test/1', 'raw.json.gz', 'hash', '2026-10-21')
    antes = parsear(contenido, *argumentos)
    despues = parsear(limpio, *argumentos)
    for original, proyeccion in zip(antes[:2], despues[:2]):
        pd.testing.assert_frame_equal(original, proyeccion)
    assert antes[2] == despues[2]
    origen = tmp_path / 'raw'
    carpeta = origen / '2026-10-21'
    carpeta.mkdir(parents=True)
    (carpeta / '1.json.gz').write_bytes(gzip.compress(contenido))
    destino = tmp_path / 'evidencia'
    assert preservar(origen, destino) == 1
    assert preservar(origen, destino) == 0
    assert gzip.decompress((destino / '2026-10-21/1.json.gz').read_bytes()) == limpio
