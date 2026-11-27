"""Clasificación de rebajas reales y aparentes, y búsqueda fina del umbral."""
import pandas as pd

from sconto.conclusiones import busqueda_umbral, clasificar


def ventana(base, previo, evento, real=True, p25=None, p75=None, serie='s'):
    return dict(mediana_base=base, mediana_previo=previo, mediana_evento=evento, p25_base=p25 or base * .98,
                p75_base=p75 or base * 1.02, real=real, serie_id=serie)


def test_rebaja_real_aparente_y_subir_y_bajar():
    d = clasificar(pd.DataFrame([
        ventana(1000, 1000, 900),   # rebaja real: 10 % bajo la historia
        ventana(1000, 1100, 1000),  # subir y bajar: parece 9 % de descuento, pero cuesta lo mismo que antes
        ventana(1000, 1000, 1000),  # sin cambio
        ventana(1000, 1000, 1100),  # subió
    ]))
    assert d.patron.tolist() == ['rebaja_real', 'rebaja_aparente', 'sin_cambio_relevante', 'subio']
    assert d.subir_y_bajar.tolist() == [False, True, False, False]
    assert d.veredicto_app.tolist() == ['favorable', 'sin_senal_clara', 'sin_senal_clara', 'alto']


def test_la_regla_no_marca_favorable_una_rebaja_aparente():
    d = clasificar(pd.DataFrame([ventana(1000, 1300, 990)]))
    assert d.parece_oferta.iloc[0] and not d.rebaja_real.iloc[0] and d.veredicto_app.iloc[0] != 'favorable'


def test_busqueda_umbral_separa_evento_de_semanas_normales():
    filas = [ventana(1000, 1000, 920, True, serie=f'r{i}') for i in range(20)]
    filas += [ventana(1000, 1000, 1000, False, serie=f'n{i}') for i in range(20)]
    t = busqueda_umbral(pd.DataFrame(filas), umbrales=[2, 5, 10], repeticiones=50)
    fila = t.set_index('umbral_pct')
    assert fila.loc[5, 'youden_j'] == 100 and fila.loc[10, 'youden_j'] == 0
