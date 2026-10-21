"""PROFECO QQP: limpieza del Avance 1 (offline, con fixture) y reproducción exacta leyendo el bronze generado."""
import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sconto.esquema import CLAVE, COLUMNAS
from sconto.normalizar import modelo_qqp
from sconto.rutas import BRONZE, REPORTS
from sconto.fuentes import qqp

FIX = Path(__file__).parent / 'fixtures' / 'qqp'
CSV = FIX / 'muestra_2025.csv'


def _leer(contenido: bytes, bloque=4):
    partes, total = qqp.leer_csv(io.BufferedReader(io.BytesIO(contenido)), 'QQP_2025/01-2025_01.csv', 'h' * 64, bloque)
    return pd.concat(partes, ignore_index=True), total


@pytest.fixture(scope='module')
def tecnologia():
    return _leer(CSV.read_bytes())


# ------------------------------------------------------------------ lectura

def test_lectura_con_cabecera(tecnologia):
    tec, total = tecnologia
    assert total['cabecera'] is True
    assert total['filas_nacionales'] == 14 and total['filas_tecnologia_nacional'] == 13
    assert total['filas_cdmx'] == 13 and total['filas_tecnologia_cdmx'] == 12
    assert tec.fila_origen.tolist() == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15]  # línea 13 = aceite
    assert set(qqp.ORIGINALES) <= set(tec.columns)


def test_lectura_sin_cabecera_igual_que_2018_2023(tecnologia):
    """2018–2023 no traen cabecera: mismas columnas y fila_origen = número de línea."""
    lineas = CSV.read_bytes().split(b'\n')
    sin_cabecera = b'\xef\xbb\xbf' + b'\n'.join(lineas[1:])
    tec, total = _leer(sin_cabecera, bloque=5)
    assert total['cabecera'] is False
    assert tec.fila_origen.tolist() == [x - 1 for x in tecnologia[0].fila_origen]
    pd.testing.assert_frame_equal(tec.drop(columns='fila_origen'), tecnologia[0].drop(columns='fila_origen'))


def test_es_cabecera():
    assert qqp.es_cabecera(b'\xef\xbb\xbfproducto,presentacion,marca,categoria,catalogo,precio,fecha_registro,x\r\n')
    assert not qqp.es_cabecera('ACEITE,BOTELLA 1 LT.,1-2-3,ACEITES,BASICOS,56.00,2023-01-02,MEGA'.encode())


# ------------------------------------------------------------------ depuración (Avance 1)

def test_depuracion_cdmx(tecnologia):
    r = qqp.depurar(qqp.recorte_cdmx(tecnologia[0]), 2025)
    assert r['calidad'] == {'originales': 12, 'invalidos': 5, 'repeticiones': 1, 'filas_en_conflicto': 2,
                            'serie_fechas_en_conflicto': 1, 'limpios': 4, 'identidad_incompleta': 1,
                            'precio_invalido': 2, 'fecha_invalida': 2}
    exc = r['exclusiones']
    # toda fila cruda termina en limpias o en exclusiones, sin repetirse
    assert sorted(exc.fila_origen.tolist() + r['limpios'].fila_origen.tolist()) == sorted(
        qqp.recorte_cdmx(tecnologia[0]).fila_origen.tolist())
    assert exc.set_index('fila_origen').motivo_exclusion.to_dict() == {
        4: 'repeticion', 5: 'conflicto', 6: 'conflicto', 7: 'invalido', 8: 'invalido', 9: 'invalido',
        10: 'invalido', 11: 'invalido'}
    limpios = r['limpios']
    assert limpios.producto_id.nunique() == 2 and limpios.sucursal_id.nunique() == 3 and limpios.serie_id.nunique() == 3
    assert not limpios.duplicated(['serie_id', 'fecha']).any()


def test_fecha_de_otro_anio_es_invalida(tecnologia):
    """La fila 2024/12/31 es inválida en el archivo 2025; si el archivo fuera 2024 sería la única limpia."""
    cdmx = qqp.recorte_cdmx(tecnologia[0])
    r25 = qqp.depurar(cdmx, 2025)['datos'].set_index('fila_origen')
    assert r25.fecha_invalida[[9, 10]].all() and not r25.fecha_invalida[[2, 3, 14, 15]].any()
    assert qqp.depurar(cdmx, 2024)['limpios'].fila_origen.tolist() == [9]


def test_identidad_igual_al_avance1(tecnologia):
    from sconto.normalizar import id_estable, normalizar
    r = qqp.depurar(qqp.recorte_cdmx(tecnologia[0]), 2025)
    fila = r['datos'].iloc[0]
    pid = id_estable([normalizar(fila[c]) for c in ('producto', 'marca', 'presentacion')])
    sid = id_estable([normalizar(fila[c]) for c in ('cadena_comercial', 'nombre_comercial', 'direccion', 'municipio')])
    assert (fila.producto_id, fila.sucursal_id, fila.serie_id) == (pid, sid, id_estable([pid, sid]))


def test_observaciones_esquema_y_clave(tecnologia):
    for fuente, originales, n in (('qqp_cdmx', qqp.recorte_cdmx(tecnologia[0]), 4), ('qqp_nacional', tecnologia[0], 5)):
        limpios = qqp.depurar(originales, 2025)['limpios']
        obs = qqp.a_observaciones(limpios, fuente, 'https://x/file.php?t=1', 'h' * 64, 'data/raw/qqp/QQP_2025.rar',
                                  '2026-10-16', 2025)
        qqp.validar_observaciones(obs)
        assert len(obs) == n and list(obs.columns[:len(COLUMNAS)]) == COLUMNAS
        assert not obs.duplicated(CLAVE).any()
        assert set(obs.metodo) == {'archivo_oficial'} and set(obs.canal) == {'tienda_fisica'}
        assert set(obs.tipo_id_externo) == {'qqp'} and set(obs.moneda) == {'MXN'}
        assert obs.precio_anterior_anunciado.isna().all() and obs.pct_descuento_anunciado.isna().all()
        assert obs.ruta_raw.str.fullmatch(r'data/raw/qqp/QQP_2025\.rar::QQP_2025/01-2025_01\.csv#\d+').all()
        assert (obs.id_externo == obs.producto_id).all()
    # dos sucursales homónimas (misma cadena y nombre comercial, otra dirección) no colapsan en la CLAVE
    barra = obs.loc[obs.producto.eq('Barra de Sonido') & obs.fecha_precio.eq('2025-01-10')]
    assert len(barra) == 2 and barra.vendedor_o_cadena.nunique() == 2
    assert barra.vendedor_o_cadena.str.startswith('BODEGA AURRERA | BODEGA AURRERA SUCURSAL SANTA LUCIA | ').all()
    assert barra.modelo_normalizado.iloc[0] == modelo_qqp(barra.presentacion.iloc[0])['modelo_normalizado'] != ''
    assert barra.descripcion_original.iloc[0].startswith('Barra de Sonido | Sony | Ht-s100f.')


# ------------------------------------------------------------------ ventanas y cobertura

def _serie(sid, fechas_precios):
    return pd.DataFrame([dict(serie_id=sid, fecha=pd.Timestamp(f), precio_num=p, producto_id='p', sucursal_id=sid,
                              producto='x', marca='m', presentacion='y', nombre_comercial='n', cadena_comercial='c',
                              municipio='z') for f, p in fechas_precios])


def test_cobertura_ahorro_y_alza():
    ev = qqp.evento_de(2025)
    assert (ev.base_inicio.date().isoformat(), ev.base_fin.date().isoformat()) == ('2025-09-14', '2025-10-29')
    assert (ev.previo_inicio.date().isoformat(), ev.previo_fin.date().isoformat()) == ('2025-10-30', '2025-11-12')
    assert (ev.evento_inicio.date().isoformat(), ev.evento_fin.date().isoformat()) == ('2025-11-13', '2025-11-17')
    base = [('2025-09-14', 100), ('2025-09-25', 100), ('2025-10-01', 110), ('2025-10-05', 120)]  # 21 días
    limpios = pd.concat([
        _serie('ok', base + [('2025-11-01', 130), ('2025-11-10', 130), ('2025-11-14', 90)]),
        _serie('amplitud20', [('2025-09-15', 1), ('2025-09-20', 1), ('2025-09-30', 1), ('2025-10-05', 1),
                              ('2025-11-14', 1)]),
        _serie('sin_evento', base + [('2025-11-01', 1), ('2025-11-02', 1)]),
        _serie('un_previo', base + [('2025-11-01', 1), ('2025-11-17', 1)]),
        _serie('tres_base', base[:3] + [('2025-11-14', 1)]),
    ], ignore_index=True)
    s = qqp.variables_por_serie(limpios, ev)
    assert s.cobertura_ahorro.to_dict() == {'amplitud20': False, 'ok': True, 'sin_evento': False, 'tres_base': False,
                                            'un_previo': True}
    assert s.cobertura_alza.to_dict() == {'amplitud20': False, 'ok': True, 'sin_evento': False, 'tres_base': False,
                                          'un_previo': False}
    assert s.loc['ok', 'ahorro_historico_pct'] == pytest.approx(100 * (1 - 90 / 105))
    assert s.loc['ok', 'alza_previa_pct'] == pytest.approx(100 * (130 / 105 - 1))
    assert np.isnan(s.loc['un_previo', 'alza_previa_pct'])
    X = qqp.matriz_modelo(limpios, s, ev)
    assert list(X.index) == ['ok'] and X.loc['ok', 'variabilidad_base_pct'] == pytest.approx(100 * (112.5 - 100) / 105)


def test_eventos_historicos():
    ev = qqp.eventos().set_index('evento_id')
    assert {f'BF{a}' for a in range(2018, 2027)} <= set(ev.index)
    assert ev.loc['BF2020', 'd0'] == pd.Timestamp('2020-11-09') and ev.loc['BF2020', 'fin'] == pd.Timestamp('2020-11-20')
    assert ev.loc['BF2024', 'd0'] == pd.Timestamp('2024-11-15')  # viene de config/eventos.yaml
    assert ev.loc['BF2018':'BF2023', 'fuente_fechas'].str.startswith('https://').all()


# ------------------------------------------------------------------ enlaces

def test_descubrir_enlaces_pagina_actual():
    e = qqp.descubrir_enlaces((FIX / 'qqp_php_2026-10-16.html').read_bytes())
    assert e['anios'] == {
        2024: 'https://datos.profeco.gob.mx/datos_abiertos/file.php?t=2de3505b2d37e7db72557a09262d95c5',
        2025: 'https://datos.profeco.gob.mx/datos_abiertos/file.php?t=b9540b181657c2bc7735892091e81f96',
        2026: 'https://datos.profeco.gob.mx/datos_abiertos/file.php?t=9d62040eae6dcc63e36b8ac821427647'}
    assert set(e['otros']) == {'Metadatos dataset', 'Diccionario de datos dataset'}


def test_descubrir_enlaces_captura_wayback():
    e = qqp.descubrir_enlaces((FIX / 'wayback_qqp_php_20250125111952.html').read_bytes())
    assert sorted(e['anios']) == list(range(2015, 2025))
    assert e['anios'][2023].endswith('file.php?t=f3270d227f2966e6138a3ed41a9bbfb7')
    assert e['anios'][2018].startswith('https://datos.profeco.gob.mx/datos_abiertos/file.php?t=')


# ------------------------------------------------------------------ bronze real (se salta si no se ha generado)

requiere_2025 = pytest.mark.skipif(not (BRONZE / 'qqp_cdmx' / '2025.parquet').exists()
                                   or not (BRONZE / 'qqp_cdmx_series' / 'BF2025.parquet').exists(),
                                   reason='falta correr: python -m sconto.fuentes.qqp backfill --anios 2025')


@requiere_2025
def test_reproduccion_exacta_avance1():
    r = qqp.reproduccion_avance1()
    obtenido = {k: v['obtenido'] for k, v in r['cifras'].items()}
    assert obtenido == {'originales': 39989, 'invalidos': 0, 'repeticiones': 440, 'filas_en_conflicto': 186,
                        'serie_fechas_en_conflicto': 93, 'limpios': 39363, 'referencias': 231, 'sucursales': 80,
                        'series': 4551, 'series_cobertura_ahorro': 298, 'series_cobertura_alza': 93}
    for k in ('06_mismos_serie_id', '06_columnas_numericas_iguales', '06_coberturas_iguales', '06_fechas_iguales',
              '06_texto_igual', '07_mismos_serie_id', '07_valores_iguales', '05_mismas_filas'):
        if k in r:
            assert r[k], k
    assert r['todo_igual']


@requiere_2025
def test_hash_2025_es_el_del_avance1():
    obs = pd.read_parquet(BRONZE / 'qqp_cdmx' / '2025.parquet', columns=['hash_raw', 'ruta_raw', 'url'])
    assert set(obs.hash_raw) == {qqp.SHA256_2025}
    assert obs.ruta_raw.str.startswith('../datos_originales/QQP_2025.rar::QQP_2025/').all()
    assert set(obs.url) == {qqp.URL_2025}


ANIOS = qqp.anios_extraidos()


@pytest.mark.skipif(not ANIOS, reason='sin bronze de QQP')
@pytest.mark.parametrize('anio', ANIOS)
@pytest.mark.parametrize('fuente', ['qqp_cdmx', 'qqp_nacional'])
def test_bronze_integridad(fuente, anio):
    ruta = BRONZE / fuente / f'{anio}.parquet'
    if not ruta.exists():
        pytest.skip(f'falta {ruta}')
    obs = pd.read_parquet(ruta, columns=CLAVE + ['precio', 'pct_descuento_anunciado', 'metodo', 'canal', 'hash_raw',
                                                 'serie_id', 'estado'])
    assert not obs.duplicated(CLAVE).any()
    assert not obs.duplicated(['serie_id', 'fecha_precio']).any()
    assert obs.precio.gt(0).all()
    fechas = pd.to_datetime(obs.fecha_precio, format='%Y-%m-%d', errors='coerce')
    assert fechas.notna().all() and fechas.dt.year.eq(anio).all()
    assert obs.pct_descuento_anunciado.isna().all()
    assert set(obs.metodo) == {'archivo_oficial'} and set(obs.canal) == {'tienda_fisica'}
    assert obs.hash_raw.nunique() == 1
    man = qqp.leer_manifiesto(anio)
    if man:
        assert obs.hash_raw.iloc[0] == man['sha256']
    if fuente == 'qqp_cdmx':
        assert set(qqp._normalizar_serie(obs.estado)) <= qqp.ESTADOS_CDMX
    m = qqp.metricas(fuente, anio)
    assert m['crudas'] == m['limpias'] + m['invalidos'] + m['repeticiones'] + m['conflictos']
    if m['auditoria'] is not None:
        assert m['crudas'] == m['auditoria']  # toda fila cruda del recorte quedó en limpias o en exclusiones


@pytest.mark.skipif(not (REPORTS / 'cobertura_qqp.md').exists() or not ANIOS, reason='sin reporte')
def test_reporte_coincide_con_bronze():
    texto = (REPORTS / 'cobertura_qqp.md').read_text(encoding='utf-8')
    for anio in ANIOS:
        for fuente in ('qqp_cdmx', 'qqp_nacional'):
            m = qqp.metricas(fuente, anio)
            if m:
                assert qqp.fila_recorte(m) in texto, (fuente, anio)
                assert qqp.fila_cobertura(m) in texto, (fuente, anio)
