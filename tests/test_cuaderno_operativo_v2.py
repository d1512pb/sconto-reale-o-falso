"""Pruebas sintéticas de paridad. Ninguna fila representa un comercio observado."""
from datetime import datetime
import sqlite3

import pytest

pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from sconto.api_v2 import crear_api
from sconto.cuaderno_operativo_v2 import reproducir
from sconto.importar_tienda_manual_v2 import importar
from sconto.intraday import IntradayStore


MOMENTO = '2026-11-15T17:00:00-06:00'
AHORA = datetime.fromisoformat(MOMENTO)


def test_cuaderno_api_comparten_decision_referencia_y_comparacion_actual(tmp_path):
    almacen = IntradayStore(tmp_path / 'datos')
    catalogo = tmp_path / 'catalogo.sqlite'
    with sqlite3.connect(catalogo) as db:
        db.executescript('''
            CREATE TABLE eventos (evento_id, base_inicio, base_fin);
            INSERT INTO eventos VALUES ('BF2026', '2026-09-14', '2026-10-29');
            CREATE TABLE catalogo_consulta (producto_canonico_id, nombre, categoria_app);
            INSERT INTO catalogo_consulta VALUES ('SIMULADO', 'Artículo sintético', 'computadoras');
        ''')
    soporte = tmp_path / 'soporte.txt'
    soporte.write_text('Documento sintético de prueba', encoding='utf-8')
    cotizacion = dict(tienda='liverpool', producto_id='SIMULADO', variante='Modelo 512 GB',
                      vendedor='Vendedor simulado', condicion='nuevo', disponibilidad='disponible',
                      identidad_verificada=True, envio_mxn='0', otros_cargos_mxn='0',
                      contexto_costo='envio_cdmx', alcance_permiso='publicacion',
                      referencia_permiso='Permiso sintético de prueba', tipo_evidencia='cotizacion_del_vendedor',
                      gtin='012345678905', promocion_condicionada=False)

    def registrar(sku, observado, total, **ajustes):
        importar(dict(cotizacion, sku=sku, url=f'https://www.liverpool.com.mx/tienda/pdp/equipo/{sku}?skuid={sku}',
                      observado_utc=observado, precio_publicado_mxn=total or '901',
                      costo_total_mxn=total, **ajustes), soporte, almacen, AHORA)

    for dia in ('2026-09-14', '2026-09-22', '2026-10-03', '2026-10-15'):
        registrar('1900000000', dia + 'T16:50:00-06:00', '1000')
        registrar('1900000003', dia + 'T16:50:00-06:00', '1000', variante='Modelo anterior',
                  gtin='012345678912')
    registrar('1900000000', '2026-11-15T16:50:00-06:00', '900')
    registrar('1900000001', '2026-11-15T14:50:00-06:00', '850')
    registrar('1900000002', '2026-11-15T16:50:00-06:00', None, envio_mxn=None)
    registrar('1900000003', '2026-11-15T16:50:00-06:00', '875', variante='Modelo nuevo',
              gtin='012345678929')
    registrar('1900000004', '2026-11-15T16:50:00-06:00', '950', vendedor='Otro vendedor simulado')
    registrar('1900000005', '2026-11-15T16:50:00-06:00', '890', promocion_condicionada='Tarjeta específica')
    registrar('1900000006', '2026-11-15T16:50:00-06:00', '895', promocion_condicionada=None)

    informe = reproducir(almacen.database, catalogo, MOMENTO, productos=['SIMULADO'])
    ficha = informe['productos'][0]
    with TestClient(crear_api(root=almacen.root, catalogo=catalogo, reloj=lambda: AHORA)) as cliente:
        ruta = '/v1/products/SIMULADO/'
        assert cliente.get(ruta + 'offers').json()['ofertas'] == ficha['ofertas']
        assert cliente.get(ruta + 'decision').json()['decisiones'] == [
            dict(offer_id=oferta['offer_id'], **oferta['decision']) for oferta in ficha['ofertas']]
        comparacion = cliente.get(ruta + 'comparacion-actual').json()
        assert comparacion['grupos'] == ficha['comparacion_actual']['grupos']
    # La variante anterior sí tiene base, pero su última cotización venció.
    assert informe['numero_ofertas_con_historia_previa'] == 2
    assert informe['numero_ofertas_evaluables'] == 1
    por_precio = {oferta['precio']: oferta for oferta in ficha['ofertas']}
    assert por_precio[900]['decision']['estado'] == 'precio_favorable'
    assert 'dato_vencido' in por_precio[850]['decision']['motivos']
    assert any('total_no_comparable' in oferta['decision']['motivos'] for oferta in ficha['ofertas'])
    assert por_precio[875]['cobertura_previa']['n_dias'] == 0
    assert por_precio[950]['decision']['motivos'] == ['historia_insuficiente']
    assert por_precio[950]['decision']['ahorro_pct'] is None
    assert [fila['total'] for fila in comparacion['grupos'][0]['ofertas']] == [900, 950]


def test_comparacion_no_revela_una_oferta_privada_por_el_product_id(tmp_path):
    almacen = IntradayStore(tmp_path / 'datos')
    soporte = tmp_path / 'soporte.txt'
    soporte.write_text('Prueba sintética de privacidad', encoding='utf-8')
    importar(dict(tienda='liverpool', producto_id='PRIVADO', sku='1900000000', variante='Ejemplo',
                  vendedor='Simulado', condicion='nuevo', disponibilidad='disponible',
                  observado_utc='2026-11-15T16:50:00-06:00', precio_publicado_mxn='500',
                  url='https://www.liverpool.com.mx/tienda/pdp/equipo/1900000000?skuid=1900000000',
                  alcance_permiso='interno', referencia_permiso='Permiso simulado',
                  tipo_evidencia='cotizacion_del_vendedor'), soporte, almacen, AHORA)
    assert reproducir(almacen.database, None, MOMENTO)['productos'] == []
    privada = reproducir(almacen.database, None, MOMENTO, privadas=True)
    assert privada['productos'][0]['comparacion_actual']['estado'] == 'evidencia_insuficiente'
