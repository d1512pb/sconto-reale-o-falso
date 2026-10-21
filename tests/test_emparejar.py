"""Regresiones sintéticas: sin red, bronze real ni escrituras de catálogo/reportes."""
import socket

import pandas as pd
import pytest

from sconto import emparejar
from sconto.normalizar import aparece_en_tokens, capacidades, compacto, es_codigo, modelo_qqp, tokens_slug, variantes


@pytest.fixture(autouse=True)
def sin_efectos_externos(monkeypatch):
    def prohibido(*args, **kwargs):
        raise AssertionError('Los tests de emparejamiento deben ser offline y sin escrituras')

    monkeypatch.setattr(socket, 'create_connection', prohibido)
    monkeypatch.setattr(socket.socket, 'connect', prohibido)
    monkeypatch.setattr(pd.DataFrame, 'to_csv', prohibido)
    monkeypatch.setattr(pd, 'read_parquet', prohibido)
    monkeypatch.setattr(pd, 'read_csv', prohibido)
    monkeypatch.setattr(emparejar, 'leer_bronze', prohibido)
    monkeypatch.setattr(emparejar, 'referencias_qqp', prohibido)


def referencia(presentacion='Galaxy Tab A9. SM-X110. 64 GB. RAM 4 GB.', producto_id='original-qqp', **cambios):
    modelo = modelo_qqp(presentacion)
    fila = dict(producto_id=producto_id, producto='Tablet', marca='Samsung', marca_norm='SAMSUNG',
                presentacion=presentacion, familia='tablet', prioridad=1,
                modelo_texto=modelo['modelo_texto'], modelo_normalizado=modelo['modelo_normalizado'],
                codigos_alternos=';'.join(modelo['codigos']), observaciones_qqp_2025=12, series_qqp_2025=3,
                **capacidades(presentacion))
    return dict(fila, **cambios)


def ficha(nombre='Samsung Galaxy Tab A9 SM-X110 64GB RAM 4GB', preciometro_id='4051', **cambios):
    fila = dict(preciometro_id=preciometro_id, nombre=nombre, marca='Samsung', modelo=None,
                url=f'https://ejemplo.invalid/productos/{preciometro_id}', palabras_claves=None,
                categoria='Tablet', categoria_path='tecnologia/tablets/samsung', capacidad=None, color=None,
                variante=None, asins='B0CPL6NDWH', mlm_ids='MLM31043809',
                es_tecnologia=True, fecha_captura='2026-10-20')
    return dict(fila, **cambios)


def comparar(ref=None, pm=None):
    return emparejar.candidatos(pd.DataFrame([ref or referencia()]), pd.DataFrame([pm or ficha()]))


def catalogo(monkeypatch, refs, fichas):
    referencias = pd.DataFrame(refs)
    productos = pd.DataFrame(fichas)
    copia_refs, copia_pm = referencias.copy(deep=True), productos.copy(deep=True)
    monkeypatch.setattr(emparejar, 'referencias_qqp', lambda: referencias)
    monkeypatch.setattr(emparejar, 'leer_bronze', lambda fuente: productos)
    resultado = emparejar.construir(guardar=False)
    pd.testing.assert_frame_equal(referencias, copia_refs)
    pd.testing.assert_frame_equal(productos, copia_pm)
    return resultado


@pytest.mark.parametrize('nombre', ['Galaxy Tab A9', 'Moto G15', 'Echo Pop', 'A9+', 'Tab A9'])
def test_nombre_comercial_no_es_codigo(nombre):
    assert not es_codigo(nombre)


@pytest.mark.parametrize('codigo', ['SM-X110', 'HT-S100F', '65UR7800PSB', '15IAN8'])
def test_codigos_de_fabricante(codigo):
    assert es_codigo(codigo)


@pytest.mark.parametrize('texto', ['galaxy-tab-a9-plus', 'Galaxy Tab A9+', 'Galaxy Tab A9 Pro'])
def test_modificador_no_es_modelo_base(texto):
    assert not aparece_en_tokens('GALAXYTABA9', tokens_slug(texto))
    assert compacto('Tab A9+') != compacto('Tab A9')


@pytest.mark.parametrize(('texto', 'esperado'), [
    ('1 TB, RAM 16 GB, micro SD hasta 2 TB', dict(almacenamiento_gb=1024, ram_gb=16)),
    ('64 GB o 128 GB, RAM 4 GB', dict(almacenamiento_gb=None, ram_gb=4)),
    ('64/128 GB, 4 GB RAM o 8 GB RAM', dict(almacenamiento_gb=None, ram_gb=None)),
    ('RAM 16 GB, almacenamiento 128 GB', dict(almacenamiento_gb=128, ram_gb=16)),
    ('64 GB, micro SD hasta 64 GB', dict(almacenamiento_gb=64, ram_gb=None)),
    ('64 GB RAM 4GB', dict(almacenamiento_gb=64, ram_gb=4)),
    ('64 GB RAM 4/8GB', dict(almacenamiento_gb=64, ram_gb=None)),
    ('64 GB 4/8GB RAM', dict(almacenamiento_gb=64, ram_gb=None)),
    ('64 GB RAM 4 GB o 8 GB', dict(almacenamiento_gb=64, ram_gb=None)),
])
def test_capacidades_no_eligen_maximo_ni_confunden_ram(texto, esperado):
    assert capacidades(texto) == esperado


def test_codigo_confirmado_es_exacto():
    assert comparar().confianza_match.tolist() == ['exacto']


def test_codigo_en_campo_modelo_tiene_prioridad():
    candidato = comparar(pm=ficha('Samsung Galaxy Tab A9 64GB RAM 4GB', modelo='SM-X110'))
    assert candidato.confianza_match.tolist() == ['exacto']


def test_nombre_comercial_sin_codigo_solo_probable():
    candidato = comparar(pm=ficha('Samsung Galaxy Tab A9 64GB RAM 4GB'))
    assert candidato.confianza_match.tolist() == ['probable']


@pytest.mark.parametrize('campo', ['url', 'palabras_claves'])
def test_codigo_solo_en_slug_o_keywords_no_promueve(campo):
    candidato = comparar(pm=ficha('Samsung Galaxy Tab A9 64GB RAM 4GB', **{campo: 'SM-X110'}))
    assert candidato.confianza_match.tolist() == ['probable']


def test_no_concatena_codigo_entre_campos():
    candidato = comparar(pm=ficha('X110 Samsung 64GB RAM 4GB', url='https://ejemplo.invalid/SM'))
    assert candidato.empty


@pytest.mark.parametrize('nombre', [
    'Samsung Galaxy Tab A9+ 11-inch 64GB Android Tablet Graphite',
    'Samsung Galaxy Tab A9 Plus 64GB RAM 4GB',
    'Samsung Galaxy Tab A9 SM-X210 64GB RAM 4GB',
])
def test_a9_plus_no_se_asigna_a_smx110_aunque_slug_diga_a9(nombre):
    candidato = comparar(pm=ficha(nombre, asins='B0CLF3VPMV',
                                  url='https://ejemplo.invalid/samsung-galaxy-tab-a9-64gb'))
    assert candidato.confianza_match.tolist() == ['descartado']


def test_codigo_de_modelo_contradictorio_no_se_rescata_con_keywords():
    candidato = comparar(pm=ficha(modelo='SM-X210', palabras_claves='SM-X110'))
    assert candidato.confianza_match.tolist() == ['probable']


@pytest.mark.parametrize('nombre', [
    'Samsung Galaxy Tab A9 SM-X110 64GB',
    'Samsung Galaxy Tab A9 SM-X110 RAM 4GB',
    'Samsung Galaxy Tab A9 SM-X110 64GB o 128GB RAM 4GB',
    'Samsung Galaxy Tab A9 SM-X110 64GB RAM 4GB o RAM 8GB',
    'Samsung Galaxy Tab A9 SM-X110 64GB RAM 4GB Color Gris',
    'Samsung Galaxy Tab A9 SM-X110 64GB RAM 4GB 2a generacion',
    'Samsung Galaxy Tab A9 SM-X110 64GB RAM 4/8GB',
    'Samsung Galaxy Tab A9 SM-X110 64GB 4/8GB RAM',
])
def test_atributos_ambiguos_o_sin_confirmar_son_probables(nombre):
    assert comparar(pm=ficha(nombre)).confianza_match.tolist() == ['probable']


@pytest.mark.parametrize('sufijo', ['128GB RAM 4GB', '64GB RAM 8GB'])
def test_capacidad_ram_distinta_se_descarta(sufijo):
    assert comparar(pm=ficha(f'Samsung Galaxy Tab A9 SM-X110 {sufijo}')).confianza_match.tolist() == ['descartado']


@pytest.mark.parametrize(('qqp', 'externa', 'confianza'), [
    ('Color Negra', 'Color Black', 'exacto'),
    ('Color Negra', 'Color Blanca', 'descartado'),
    ('Color Blanca o Negra', 'Color Blanca', 'probable'),
    ('2a generacion', '3a generacion', 'descartado'),
    ('2a generacion', 'generacion 2', 'exacto'),
    ('2.ª generacion', 'generacion 3', 'descartado'),
])
def test_color_y_generacion(qqp, externa, confianza):
    ref = referencia(f'Galaxy Tab A9. SM-X110. 64 GB. RAM 4 GB. {qqp}.')
    candidato = comparar(ref, ficha(f'Samsung Galaxy Tab A9 SM-X110 64GB RAM 4GB {externa}'))
    assert candidato.confianza_match.tolist() == [confianza]


def test_generacion_y_colores_preservan_alternativas():
    assert variantes('Color Blanca o Negra, generacion 2 o 3a generacion')['color'] == {'BLANCO', 'NEGRO'}
    assert variantes('generacion 2 o 3a generacion')['generacion'] == {2, 3}


def test_probable_no_publica_ids_automaticos(monkeypatch):
    prod, cand = catalogo(monkeypatch, [referencia()], [ficha('Samsung Galaxy Tab A9 64GB RAM 4GB')])
    qqp = prod.loc[prod.origen.eq('qqp')].iloc[0]
    assert qqp.confianza_match == 'probable'
    assert (qqp.preciometro_ids, qqp.asins, qqp.mlm_ids) == ('', '', '')
    assert qqp.asins_candidatos == cand.asins.iloc[0] == 'B0CPL6NDWH'
    independientes = prod.loc[prod.origen.eq('preciometro')]
    assert independientes.preciometro_ids.tolist() == ['4051']
    assert independientes.producto_canonico_id.tolist() == ['P4-4051']
    assert independientes.asins.eq('').all() and independientes.mlm_ids.eq('').all()


@pytest.mark.parametrize('columna', ['asins', 'mlm_ids'])
def test_ids_compartidos_no_se_autoasignan_entre_modelos(monkeypatch, columna):
    refs = [referencia(), referencia('Galaxy Tab A9+. SM-X210. 64 GB. RAM 4 GB.', 'otra-original')]
    fichas = [ficha(**{columna: 'B0CLF3VPMV' if columna == 'asins' else 'MLM-123456'}),
              ficha('Samsung Galaxy Tab A9+ SM-X210 64GB RAM 4GB', '4077',
                    asins='B0CLF3VPMV' if columna == 'asins' else 'OTROASIN00', mlm_ids='MLM123456')]
    prod, cand = catalogo(monkeypatch, refs, fichas)
    qqp = prod.loc[prod.origen.eq('qqp')]
    assert qqp.qqp_producto_id.tolist() == ['original-qqp', 'otra-original']
    assert qqp.confianza_match.eq('probable').all()
    assert qqp[['preciometro_ids', 'asins', 'mlm_ids']].eq('').all().all()
    assert cand.loc[cand.confianza_match.ne('descartado'), 'confianza_match'].eq('probable').all()
    assert qqp.observaciones_qqp_2025.tolist() == [12, 12]


def test_id_compartido_con_ficha_sin_equivalente_qqp_tambien_bloquea(monkeypatch):
    prod, cand = catalogo(monkeypatch, [referencia()], [ficha(asins='B0CLF3VPMV'),
        ficha('Samsung Galaxy Tab A9 Plus 64GB RAM 4GB', '4077', asins='B0CLF3VPMV')])
    assert prod.confianza_match.eq('probable').all()
    assert prod.asins.eq('').all()
    assert set(prod.loc[prod.origen.eq('preciometro'), 'preciometro_ids']) == {'4051', '4077'}
    assert cand.loc[cand.preciometro_id.eq('4051'), 'confianza_match'].tolist() == ['probable']


def test_candidatos_compartidos_incompatibles_ya_son_probables():
    refs = [referencia(), referencia('Galaxy Tab A9+. SM-X210. 64 GB. RAM 4 GB.', 'otro-qqp')]
    fichas = [ficha(), ficha('Samsung Galaxy Tab A9+ SM-X210 64GB RAM 4GB', '4077')]
    cand = emparejar.candidatos(pd.DataFrame(refs), pd.DataFrame(fichas))
    assert cand.confianza_match.tolist() == ['probable', 'probable']


def test_tablet_sin_capacidad_ni_ram_no_es_exacta():
    candidato = comparar(referencia('Galaxy Tab A9. SM-X110.'), ficha('Samsung Galaxy Tab A9 SM-X110'))
    assert candidato.confianza_match.tolist() == ['probable']


def test_exacto_no_incorpora_ids_de_otro_candidato_probable(monkeypatch):
    prod, cand = catalogo(monkeypatch, [referencia()], [ficha(),
        ficha('Samsung Galaxy Tab A9 64GB RAM 4GB', '9999', asins='PROBABLE00', mlm_ids='')])
    qqp = prod.loc[prod.origen.eq('qqp')].iloc[0]
    assert qqp.confianza_match == 'exacto'
    assert qqp.asins == 'B0CPL6NDWH'
    assert 'PROBABLE00' not in qqp.asins
    assert set(cand.confianza_match) == {'exacto', 'probable'}


def test_no_fusiona_qqp_sin_ficha_externa(monkeypatch):
    refs = [referencia(), referencia(producto_id='segundo-original', prioridad=3)]
    prod, cand = catalogo(monkeypatch, refs, [])
    assert cand.empty and len(prod) == 2
    assert prod.qqp_producto_id.tolist() == ['original-qqp', 'segundo-original']
    assert prod.producto_canonico_id.nunique() == 2
    assert prod.confianza_match.eq('sin_candidato').all()


def test_qqp_compatibles_conservan_ambos_originales(monkeypatch):
    refs = [referencia(), referencia(producto_id='segundo-original', prioridad=3)]
    prod, cand = catalogo(monkeypatch, refs, [ficha()])
    assert len(prod) == 2 and prod.producto_canonico_id.nunique() == 2
    assert prod.qqp_producto_id.tolist() == ['original-qqp', 'segundo-original']
    assert prod.confianza_match.eq('exacto').all()
    assert cand.confianza_match.eq('exacto').all()


def test_texto_qqp_agrupado_se_conserva_sin_dividir(monkeypatch):
    ref = referencia('Galaxy Tab A9. SM-X110. 64 GB. RAM 4 GB. Color Blanca o Negra.')
    prod, cand = catalogo(monkeypatch, [ref], [ficha('Samsung Galaxy Tab A9 SM-X110 64GB RAM 4GB Blanca')])
    qqp = prod.loc[prod.origen.eq('qqp')]
    assert len(qqp) == 1 and qqp.qqp_producto_id.iloc[0] == ref['producto_id']
    assert qqp.descripcion_qqp.iloc[0] == f"Tablet | Samsung | {ref['presentacion']}"
    assert cand.descripcion_qqp.iloc[0] == qqp.descripcion_qqp.iloc[0]
    assert qqp.confianza_match.iloc[0] == 'probable' and qqp.asins.iloc[0] == ''


@pytest.mark.parametrize(('cambios', 'motivo'), [
    ({'marca': 'Sony', 'nombre': 'Sony Galaxy Tab A9 SM-X110 64GB RAM 4GB'}, 'marca'),
    ({'categoria_path': 'tecnologia/laptops'}, 'familia'),
])
def test_marca_y_familia_siguen_siendo_barreras(cambios, motivo):
    candidato = comparar(pm=ficha(**cambios))
    assert candidato.confianza_match.tolist() == ['descartado']
    assert motivo in candidato.motivo.iloc[0]
