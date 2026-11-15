from datetime import date, datetime, timezone

import pytest

from sconto.decisiones_v2 import evaluar_decision, referencia_diaria


AHORA = datetime(2026, 11, 14, 20, tzinfo=timezone.utc)
OFERTA = dict(offer_id='oferta1', canal='en_linea', moneda='MXN', contexto_costo='retiro-estandar',
              verificacion='directa', observed_at='2026-11-14T13:30:00-06:00', precision_temporal='instante',
              identidad_confirmada=True, variante='SKU-13', vendedor='Tienda', condicion='nuevo',
              disponibilidad='en_stock', costo_total_confirmado=900)
REFERENCIA = dict(offer_id='oferta1', moneda='MXN', contexto_costo='retiro-estandar', cerrada=True,
                  n_dias=4, amplitud_dias=21, mediana=1000, p25=950, p75=1050)


@pytest.mark.parametrize(('total', 'estado'), [(950, 'precio_favorable'), (1050, 'precio_alto'), (1000, 'sin_senal_clara')])
def test_estados_bajo_intacto_el_protocolo_de_magnitud_y_cuartil(total, estado):
    decision = evaluar_decision({**OFERTA, 'costo_total_confirmado':total}, REFERENCIA, ahora=AHORA)
    assert decision['estado'] == estado
    assert decision['ahorro_pct'] == pytest.approx(100 * (1 - total / 1000))
    assert decision['edad_minutos'] == 30
    assert decision['motivos'] == []


def test_un_porcentaje_aislado_o_una_posicion_aislada_no_determina_el_indicador():
    assert evaluar_decision(OFERTA, {**REFERENCIA, 'p25':850}, ahora=AHORA)['estado'] == 'sin_senal_clara'
    assert evaluar_decision({**OFERTA, 'costo_total_confirmado':980}, {**REFERENCIA, 'p25':990},
                           ahora=AHORA)['estado'] == 'sin_senal_clara'


@pytest.mark.parametrize(('cambio', 'motivo'), [
    ({'canal':'tienda_fisica'}, 'canal_fisico'),
    ({'verificacion':'indirecta', 'fetched_at_utc':'2026-11-14T19:59:00Z'}, 'fuente_sin_verificacion_directa'),
    ({'observed_at':'2026-11-14T18:00:00Z'}, 'dato_vencido'),
    ({'observed_at':'2026-11-14T20:00:01Z'}, 'fecha_insuficiente'),
    ({'observed_at':'2026-11-14T19:00:00'}, 'fecha_insuficiente'),
    ({'precision_temporal':'dia'}, 'fecha_insuficiente'),
    ({'identidad_confirmada':False}, 'identidad_incompleta'),
    ({'variante':' '}, 'identidad_incompleta'),
    ({'vendedor':None}, 'identidad_incompleta'),
    ({'disponibilidad':None}, 'disponibilidad_sin_confirmar'),
    ({'disponibilidad':'agotado'}, 'sin_stock_confirmado'),
    ({'costo_total_confirmado':None}, 'total_no_comparable'),
    ({'moneda':'USD'}, 'total_no_comparable'),
    ({'contexto_costo':'entrega-diferente'}, 'historia_insuficiente'),
])
def test_abstencion_indica_la_evidencia_que_falta(cambio, motivo):
    decision = evaluar_decision({**OFERTA, **cambio}, REFERENCIA, ahora=AHORA)
    assert decision['estado'] == 'evidencia_insuficiente'
    assert decision['ahorro_pct'] is None
    assert motivo in decision['motivos']


def test_historia_excluye_la_consulta_y_conserva_cada_dia_con_el_mismo_peso():
    fechas = ['2026-10-01', '2026-10-08', '2026-10-15', '2026-10-22']
    filas = [{**OFERTA, 'fecha_precio':f, 'costo_total_confirmado':total}
             for f, total in zip(fechas, [800, 900, 1100, 1200], strict=True)]
    filas += [filas[0]] * 80
    filas += [{**f, 'costo_total_confirmado':1, 'verificacion':'indirecta'} for f in filas[:4]]
    filas += [{**f, 'costo_total_confirmado':1, 'contexto_costo':'otro-contexto'} for f in filas[:4]]
    filas.append({**OFERTA, 'fecha_precio':'2026-11-14', 'costo_total_confirmado':1})
    ref = referencia_diaria(filas, OFERTA, base_inicio=date(2026, 10, 1), base_fin='2026-10-30', hoy='2026-11-14')
    assert (ref['p25'], ref['mediana'], ref['p75']) == (875, 1000, 1125)
    assert ref['n_dias'] == 4 and ref['amplitud_dias'] == 21 and ref['cerrada']
    insuficiente = referencia_diaria(filas, OFERTA, base_inicio='2026-10-01', base_fin='2026-11-14', hoy='2026-11-14')
    assert not insuficiente['cerrada'] and insuficiente['n_dias'] == 4
    assert evaluar_decision(OFERTA, insuficiente, ahora=AHORA)['estado'] == 'evidencia_insuficiente'
