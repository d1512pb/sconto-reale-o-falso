"""Auditoría descriptiva del Buen Fin con un corte explícito y evidencia por serie."""
from __future__ import annotations

import hashlib

import pandas as pd


HIPOTESIS = [
    ('H1', 'Alza previa y rebaja durante el evento', 'Mediana previa > mediana base y mediana del evento < mediana previa en la misma serie.', 'La cobertura y el calendario de precios pueden explicar parte del cambio.'),
    ('H2', 'Precio tachado superior a lo habitual', 'Precio tachado frente a la mediana base de la misma variante y vendedor.', 'El tachado puede representar un precio de lista.'),
    ('H3', 'Mayor descuento anunciado sin menor precio pagable', 'Comparar dos capturas con porcentaje anunciado y costo total conocido.', 'Un cambio de términos puede alterar la comparación.'),
    ('H4', 'Promoción condicionada', 'Cotejar cupón, medio de pago, tope, mínimo y fechas en los términos.', 'Los campos del agregador pueden estar incompletos.'),
    ('H5', 'Envío o cargo absorbe el ahorro', 'Cotejar costo total y precio histórico comparable para la misma entrega.', 'El envío puede variar según el domicilio.'),
    ('H6', 'Cambió la variante o el vendedor', 'Verificar SKU, atributos, condición y vendedor efectivo en ambas fuentes.', 'Los títulos pueden omitir atributos.'),
    ('H7', 'Oferta fugaz, agotada o desactualizada', 'Comparar comprobaciones intradía del mismo anuncio con inventario conocido.', 'Un hueco de captura deja la vigencia sin confirmar.'),
    ('H8', 'Descuento verificable y útil', 'Precio total verificable, disponible y por debajo de una referencia comparable.', 'La utilidad del ahorro depende del comprador.'),
]


def analizar_mercado(observaciones, series_evento, evento, corte):
    desde, hasta = str(evento['evento_inicio'])[:10], str(evento['evento_fin'])[:10]
    corte = pd.Timestamp(corte).date().isoformat()
    fechas = pd.to_datetime(observaciones.fecha_precio).dt.strftime('%Y-%m-%d')
    capturas = pd.to_datetime(observaciones.fecha_captura).dt.strftime('%Y-%m-%d')
    muestra = observaciones.loc[fechas.between(desde, min(corte, hasta)) & capturas.le(corte)].copy()
    muestra['fecha_precio'] = fechas.loc[muestra.index]
    inventario = muestra.groupby(['fuente', 'plataforma', 'fecha_precio'], dropna=False).agg(
        filas=('obs_id', 'size'), series=('serie_id', 'nunique'),
        productos=('producto_canonico_id', 'nunique'), tachados=('precio_anterior_anunciado', 'count'),
        porcentajes=('pct_descuento_anunciado', 'count'), disponibilidad=('disponibilidad', 'count'),
    ).reset_index()

    # Agregar dentro del día antes de comparar. Una serie cuenta una vez en cada resultado.
    diarios = muestra.groupby(['fuente', 'serie_id', 'fecha_precio'], as_index=False).precio.median()
    dias = diarios.sort_values('fecha_precio').groupby(['fuente', 'serie_id']).precio.agg(
        dias_observados='size', primer_precio='first', ultimo_precio='last',
        minimo_observado='min', maximo_observado='max',
    ).reset_index()
    pares = dias.loc[dias.dias_observados.ge(2)].copy()
    pares['cambio_pct'] = 100 * (pares.ultimo_precio / pares.primer_precio - 1)

    # La trayectoria de los mínimos de mercado sólo describe el catálogo.
    bases = series_evento.loc[series_evento.evento_id.eq(evento['evento_id']) &
                              series_evento.cobertura_ahorro].copy()
    if (pd.to_datetime(observaciones.fecha_precio).gt(pd.Timestamp(corte)) |
            pd.to_datetime(observaciones.fecha_captura).gt(pd.Timestamp(corte))).any():
        raise ValueError('Usa el snapshot del corte para evitar bases que incluyen datos posteriores.')
    bases = bases.loc[bases.serie_id.isin(muestra.serie_id)]
    bases = bases[['fuente', 'serie_id', 'mediana_base', 'minimo_base', 'mediana_previo',
                   'mediana_evento', 'cobertura_alza', 'ahorro_historico_pct']]
    bases['diferencia_con_minimo_base_pct'] = 100 * (1 - bases.mediana_evento / bases.minimo_base)
    bases['alza_y_rebaja_observadas'] = (bases.cobertura_alza &
                                        bases.mediana_previo.gt(bases.mediana_base) &
                                        bases.mediana_evento.lt(bases.mediana_previo))
    hallazgos = pd.DataFrame(HIPOTESIS, columns=['id', 'hipotesis', 'definicion', 'explicacion_alternativa'])
    hallazgos['estado'] = 'sin_evidencia_comparable_al_corte'
    hallazgos['n_casos_validos'] = 0
    hallazgos['n_con_patron'] = pd.Series(pd.NA, index=hallazgos.index, dtype='Int64')
    hallazgos['limite'] = 'Falta verificar la evidencia requerida para la misma variante y vendedor.'
    referidas = bases.loc[bases.cobertura_alza & bases.fuente.isin(['qqp_cdmx', 'qqp_nacional'])]
    if len(referidas):
        hallazgos.loc[hallazgos.id.eq('H1'), ['estado', 'n_casos_validos', 'n_con_patron', 'limite']] = [
            'patron_descriptivo_preliminar', len(referidas), int(referidas.alza_y_rebaja_observadas.sum()),
            'Series físicas por producto y sucursal con cobertura. El patrón no identifica intención.',
        ]
    return dict(muestra=muestra, inventario=inventario, cambios=pares, referencias=bases,
                hipotesis=hallazgos[['id', 'hipotesis', 'definicion', 'explicacion_alternativa']],
                hallazgos=hallazgos)


def resumen_cambios(pares):
    return pares.assign(
        subieron=pares.cambio_pct.gt(0), bajaron=pares.cambio_pct.lt(0),
        quedaron_igual=pares.cambio_pct.eq(0), magnitud_pct=pares.cambio_pct.abs(),
    ).groupby('fuente').agg(
        series_comparables_por_id=('serie_id', 'size'), subieron=('subieron', 'sum'),
        bajaron=('bajaron', 'sum'), quedaron_igual=('quedaron_igual', 'sum'),
        mediana_cambio_absoluto_pct=('magnitud_pct', 'median'),
    ).reset_index()


def analizar_profeco_bf(datos, evento):
    """Compara la misma sucursal y producto de la consulta especial, con precisión diaria."""
    campos_sucursal = ['sucursal_ref'] if 'sucursal_ref' in datos else ['sucursal', 'direccion']
    clave = ['producto_profeco_id', *campos_sucursal, 'zona_sucursal']
    datos = datos.copy()
    datos['fecha_precio'] = pd.to_datetime(datos.fecha_precio, errors='raise').dt.normalize()
    datos['precio_mxn'] = pd.to_numeric(datos.precio_mxn, errors='raise')
    if not datos.precio_mxn.between(0, float('inf'), inclusive='neither').all():
        raise ValueError('La consulta especial contiene precios inválidos')
    datos = datos.dropna(subset=['producto_profeco_id', *campos_sucursal])
    diarios = datos.groupby(clave + ['fecha_precio'], as_index=False, dropna=False).precio_mxn.agg(
        minimo='min', maximo='max')
    conflicto = diarios.minimo.ne(diarios.maximo)
    conflictos = int(conflicto.sum())
    diarios = diarios.loc[~conflicto].rename(columns={'minimo': 'precio_mxn'})
    panel = diarios[clave].drop_duplicates().set_index(clave)
    for ventana in ('base', 'previo', 'evento'):
        a, b = (pd.Timestamp(evento[f'{ventana}_{extremo}']) for extremo in ('inicio', 'fin'))
        grupo = diarios.loc[diarios.fecha_precio.between(a, b)].groupby(clave, dropna=False)
        resumen = grupo.agg(n=('fecha_precio', 'size'), mediana=('precio_mxn', 'median'),
                            minimo=('precio_mxn', 'min'), inicio=('fecha_precio', 'min'), fin=('fecha_precio', 'max'))
        panel = panel.join(resumen.add_prefix(ventana + '_'))
        panel[f'{ventana}_n'] = panel[f'{ventana}_n'].fillna(0).astype(int)
    panel['base_dias'] = (panel.base_fin - panel.base_inicio).dt.days
    panel['cobertura_alza'] = (panel.base_n.ge(4) & panel.base_dias.ge(21) &
                               panel.previo_n.ge(2) & panel.evento_n.ge(1))
    panel['patron_alza_y_rebaja'] = (panel.cobertura_alza & panel.previo_mediana.gt(panel.base_mediana) &
                                    panel.evento_mediana.lt(panel.previo_mediana))
    panel['ahorro_vs_base_pct'] = (100 * (1 - panel.evento_mediana / panel.base_mediana)).where(
        panel.base_n.ge(4) & panel.base_dias.ge(21) & panel.evento_n.ge(1))
    panel['variacion_evento_vs_previo_pct'] = (100 * (panel.evento_mediana / panel.previo_mediana - 1)).where(
        panel.previo_n.ge(2) & panel.evento_n.ge(1))
    panel = panel.reset_index()
    campos_serie = ['producto_profeco_id', *campos_sucursal]
    panel['serie_id'] = [hashlib.sha256(repr(valores).encode()).hexdigest()[:20]
                        for valores in panel[campos_serie].itertuples(index=False, name=None)]
    panel = panel.drop(columns=campos_sucursal)

    inventario = diarios.groupby(['zona_sucursal', 'fecha_precio'], as_index=False, dropna=False).agg(
        observaciones=('precio_mxn', 'size'), productos=('producto_profeco_id', 'nunique'))
    resumen = panel.assign(evento_visto=panel.evento_n.gt(0),
                           ahorro_evaluable=panel.ahorro_vs_base_pct.notna()).groupby(
        'zona_sucursal', dropna=False, as_index=False).agg(
        series=('serie_id', 'size'), productos=('producto_profeco_id', 'nunique'),
        con_evento=('evento_visto', 'sum'), con_base_y_evento=('ahorro_evaluable', 'sum'),
        con_base_previo_evento=('cobertura_alza', 'sum'), alza_y_rebaja=('patron_alza_y_rebaja', 'sum'))
    return dict(inventario=inventario, panel=panel, resumen=resumen, conflictos=conflictos)
