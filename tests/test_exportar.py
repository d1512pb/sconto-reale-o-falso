import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from sconto.colab import cargar_paquete
from sconto.exportar import empaquetar


def preparar_gold(tmp_path):
    carpeta = tmp_path / 'gold'
    carpeta.mkdir()
    manifiesto = {'construido_utc': '2026-10-20T12:00:00Z', 'tablas': {}}
    for nombre in ['observaciones', 'productos', 'eventos', 'series_evento', 'exclusiones']:
        tabla = pd.DataFrame({'valor': [1]})
        ruta = carpeta / f'{nombre}.parquet'
        tabla.to_parquet(ruta, index=False)
        tabla.to_csv(carpeta / f'{nombre}.csv', index=False)
        manifiesto['tablas'][nombre] = dict(parquet=ruta.name, csv=f'{nombre}.csv', filas=1,
                                           sha256_parquet=hashlib.sha256(ruta.read_bytes()).hexdigest())
    (carpeta / 'manifiesto.json').write_text(json.dumps(manifiesto), encoding='utf-8')
    return carpeta


def test_paquete_portable_sin_crudos_ni_secretos(tmp_path):
    gold = preparar_gold(tmp_path)
    archivo = empaquetar(gold, tmp_path / 'dataset.zip')
    with ZipFile(archivo) as paquete:
        assert 'paquete.json' in paquete.namelist()
        assert not any('raw' in nombre or '.env' in nombre for nombre in paquete.namelist())
    tablas = cargar_paquete(archivo)
    assert len(tablas['observaciones']) == 1


def test_exportacion_rechaza_gold_modificado(tmp_path):
    gold = preparar_gold(tmp_path)
    pd.DataFrame({'valor': [2]}).to_parquet(gold / 'observaciones.parquet', index=False)
    with pytest.raises(ValueError, match='cambió'):
        empaquetar(gold, tmp_path / 'dataset.zip')


def test_carga_rechaza_hash_incorrecto(tmp_path):
    archivo = tmp_path / 'invalido.zip'
    with ZipFile(archivo, 'w', compression=ZIP_DEFLATED) as paquete:
        paquete.writestr('observaciones.parquet', b'datos no validos')
        paquete.writestr('paquete.json', json.dumps({'tablas': {'observaciones': {
            'archivo': 'observaciones.parquet', 'sha256': 'incorrecto', 'filas': 1}}}))
    with pytest.raises(ValueError, match='SHA-256'):
        cargar_paquete(archivo)
