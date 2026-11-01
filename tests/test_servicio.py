import pandas as pd
import pytest

from sconto import almacen, servicio


def archivo(raiz, relativa, contenido):
    ruta = raiz / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


def test_particiones_evitan_colision_cloud_local(tmp_path, monkeypatch):
    monkeypatch.setattr(almacen, 'BRONZE', tmp_path)
    monkeypatch.delenv('SCONTO_PARTICION', raising=False)
    cloud = almacen.escribir_bronze('preciometro', [{'id': 'A', 'precio': 100}], '2026-10-31', clave=['id'])
    monkeypatch.setenv('SCONTO_PARTICION', 'local')
    local = almacen.escribir_bronze('preciometro', [{'id': 'A', 'precio': 90}], '2026-10-31', clave=['id'])
    assert cloud.name == '2026-10-31.parquet'
    assert local.name == '2026-10-31.local.parquet'
    assert pd.read_parquet(cloud).precio.iloc[0] == 100
    assert pd.read_parquet(local).precio.iloc[0] == 90
    assert len(almacen.leer_bronze('preciometro')) == 2


def test_rechaza_particion_con_rutas(tmp_path, monkeypatch):
    monkeypatch.setattr(almacen, 'BRONZE', tmp_path)
    monkeypatch.setenv('SCONTO_PARTICION', '../ajeno')
    with pytest.raises(ValueError, match='Partición'):
        almacen.escribir_bronze('fuente', [{'precio': 10}], '2026-10-31')


def test_particion_local_no_cambia_nombre_de_tabla_anual(tmp_path, monkeypatch):
    monkeypatch.setattr(almacen, 'BRONZE', tmp_path)
    monkeypatch.setenv('SCONTO_PARTICION', 'local')
    ruta = almacen.escribir_bronze('qqp_cdmx', [{'precio': 10}], '2026')
    assert ruta.name == '2026.parquet'


def test_recupera_historia_local_sin_sobrescribir_cloud(tmp_path):
    datos, copia = tmp_path / 'datos', tmp_path / 'repo'
    archivo(datos, 'data/raw/preciometro/2026-10-22/1.json.gz', b'privado')
    archivo(datos, 'data/bronze/preciometro/2026-10-22.parquet', b'captura local')
    remoto = archivo(copia, 'data/bronze/preciometro/2026-10-22.parquet', b'captura cloud')
    archivo(datos, 'data/bronze/preciometro/2026-10-31.local.parquet', b'nueva captura')
    archivo(datos, 'data/bronze/preciometro/2026-10-30.parquet', b'semilla remota')
    archivo(datos, 'data/evidencia/preciometro/2026-10-22/1.json.gz', b'proyeccion segura')
    rutas = servicio.copiar_publicables(datos, copia)
    assert remoto.read_bytes() == b'captura cloud'
    assert (copia / 'data/bronze/preciometro/2026-10-22.local.parquet').read_bytes() == b'captura local'
    assert (copia / 'data/bronze/preciometro/2026-10-31.local.parquet').read_bytes() == b'nueva captura'
    assert not (copia / 'data/bronze/preciometro/2026-10-30.local.parquet').exists()
    assert 'data/evidencia/preciometro/local/2026-10-22/1.json.gz' in rutas
    assert not any('data/raw' in ruta for ruta in rutas)
    assert servicio.copiar_publicables(datos, copia) == []


def test_legado_no_atribuye_descargas_remotas_futuras_a_la_pc(tmp_path):
    assert servicio.legado_local(tmp_path) == []
    archivo(tmp_path, 'data/raw/preciometro/2026-10-31/1.json.gz', b'local')
    archivo(tmp_path, 'data/bronze/preciometro/2026-10-31.parquet', b'remoto')
    assert servicio.legado_local(tmp_path) == []


def test_no_publica_de_nuevo_semilla_identica(tmp_path):
    datos, copia = tmp_path / 'datos', tmp_path / 'repo'
    archivo(datos, 'data/raw/tiendas/2026-10-21/1.gz', b'privado')
    relativa = 'data/bronze/tiendas/2026-10-21.parquet'
    archivo(datos, relativa, b'ya publicada')
    archivo(copia, relativa, b'ya publicada')
    assert servicio.copiar_publicables(datos, copia) == []


def test_sin_confirmacion_local_genera_alerta_aunque_no_se_ejecute(tmp_path, monkeypatch):
    ruta = tmp_path / 'estado.csv'
    pd.DataFrame([dict(fuente='tiendas', entorno='local', fecha='2026-10-22', estado='ok', detalle='real')]).to_csv(ruta, index=False)
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'fuentes.yaml').write_text('fuentes:\n  tiendas:\n    entornos: [local]\n', encoding='utf-8')
    monkeypatch.setattr(almacen, 'ESTADO_FUENTES', ruta)
    monkeypatch.setattr(almacen, 'CONFIG', config)
    monkeypatch.setattr(almacen, 'ALERTA', tmp_path / 'ALERTA.md')
    monkeypatch.setattr(almacen, 'hoy', lambda: '2026-10-31')
    assert 'sin confirmación desde 2026-10-22' in almacen.revisar_alertas()[0]
    (config / 'fuentes.yaml').write_text('fuentes:\n  tiendas:\n    habilitada: false\n    entornos: [local]\n', encoding='utf-8')
    assert almacen.revisar_alertas() == []
