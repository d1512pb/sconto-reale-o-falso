"""Modelado retrospectivo sin etiquetas de fraude ni entrenamiento con eventos futuros."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest

VARIABLES = ['ahorro_historico_pct', 'alza_previa_pct', 'variabilidad_base_pct']
SEMILLA = 42


def modelar(series, eventos, fecha_corte, arboles=300):
    fin = eventos.set_index('evento_id').evento_fin.map(pd.Timestamp)
    datos = series.copy()
    completos = datos.evento_id.map(fin).lt(pd.Timestamp(fecha_corte))
    dominio = datos.plataforma_serie.eq('qqp_cdmx') & datos.canal.eq('tienda_fisica')
    elegibles = completos & dominio & datos.cobertura_alza.fillna(False)
    finitos = np.isfinite(datos[VARIABLES].apply(pd.to_numeric, errors='coerce')).all(axis=1)
    datos = datos.loc[elegibles & finitos].sort_values('serie_evento_id').copy()
    entrenamiento = datos.loc[datos.evento_id.eq('BF2024')]
    validacion = datos.loc[datos.evento_id.eq('BF2025')]
    tarjeta = dict(version='if-qqp-temporal-v1', variables=VARIABLES, semilla=SEMILLA,
                   n_arboles=arboles, dominio='QQP CDMX, tienda física',
                   evento_entrenamiento='BF2024', evento_validacion='BF2025',
                   n_entrenamiento=len(entrenamiento), n_validacion=len(validacion),
                   sklearn_version=sklearn.__version__, fecha_corte=str(fecha_corte),
                   interpretacion='Puntaje de rareza; NO es probabilidad de fraude ni prueba de engaño.',
                   alcance='Evaluación temporal retrospectiva sobre precios reconstruidos; no ensayo prospectivo.',
                   brecha_como_cuarta_variable='No entrenada: requiere una muestra comparable suficiente.',
                   incluye_posterior=False, incluye_identificadores=False)
    if len(entrenamiento) < 20:
        tarjeta['estado'] = 'sin_muestra_entrenamiento_suficiente'
        return dict(resultados=pd.DataFrame(), evaluacion=pd.DataFrame(), revision=pd.DataFrame(), tarjeta=tarjeta)
    modelo = IsolationForest(n_estimators=arboles, contamination='auto', random_state=SEMILLA, n_jobs=1)
    modelo.fit(entrenamiento[VARIABLES])
    datos['puntaje_anomalia'] = -modelo.score_samples(datos[VARIABLES])
    puntajes_train = -modelo.score_samples(entrenamiento[VARIABLES])
    umbral = float(np.quantile(puntajes_train, .90))
    datos['umbral_revision'] = umbral
    datos['senal_revision_modelo'] = datos.puntaje_anomalia.ge(umbral)
    datos['etapa'] = np.where(datos.evento_id.eq('BF2024'), 'entrenamiento',
                             np.where(datos.evento_id.eq('BF2025'), 'validacion_temporal', 'aplicacion_historica'))
    datos['regla_sin_ahorro'] = datos.ahorro_historico_pct.le(0)
    datos['regla_alza_previa_5'] = datos.alza_previa_pct.gt(5)
    datos['modelo_id'] = tarjeta['version']
    datos['revision_humana'] = 'pendiente'
    datos['motivos_reglas'] = [json.dumps([nombre for nombre, cumple in
                                          [('sin_ahorro', ahorro), ('alza_previa_mayor_5_pct', alza)] if cumple])
                               for ahorro, alza in zip(datos.regla_sin_ahorro, datos.regla_alza_previa_5)]
    metricas = []

    def agregar(experimento, metrica, valor, cantidad, interpretacion):
        metricas.append(dict(experimento=experimento, metrica=metrica, valor=valor,
                             n_casos=cantidad, interpretacion=interpretacion))

    productos_train = set(entrenamiento.producto_canonico_id.dropna())
    productos_test = set(validacion.producto_canonico_id.dropna())
    tarjeta.update(estado='entrenado', umbral_revision=umbral,
                   productos_compartidos_train_test=len(productos_train & productos_test),
                   advertencia_solapamiento='Se evalúa el futuro de productos conocidos; no se afirma independencia por producto.',
                   n_brechas_disponibles=int(datos.brecha_pp.notna().sum()))
    for etapa, grupo in datos.groupby('etapa'):
        agregar(etapa, 'n_series', len(grupo), len(grupo), 'Tamaño de muestra, no exactitud.')
        agregar(etapa, 'senal_revision_modelo', int(grupo.senal_revision_modelo.sum()), len(grupo),
                'Señal derivada del percentil 90 de entrenamiento; no etiqueta verificada.')
        agregar(etapa, 'regla_alza_previa_5', int(grupo.regla_alza_previa_5.sum()), len(grupo), 'Regla descriptiva.')
        top = grupo.nlargest(min(10, len(grupo)), 'puntaje_anomalia')
        agregar(etapa, 'top10_coincide_alza_5', int(top.regla_alza_previa_5.sum()), len(top),
                'Coincidencia entre reglas, no precisión contra verdad independiente.')
    nuevos = datos.loc[datos.etapa.eq('validacion_temporal') & ~datos.producto_canonico_id.isin(productos_train)]
    agregar('validacion_temporal', 'series_productos_no_vistos', len(nuevos), len(validacion),
            'Subconjunto sin producto compartido; su tamaño limita generalizar a nuevos modelos.')
    if len(validacion):
        prueba = datos.loc[datos.etapa.eq('validacion_temporal')].set_index('serie_evento_id')
        cantidad = min(10, len(prueba))
        principales = set(prueba.nlargest(cantidad, 'puntaje_anomalia').index)
        for semilla in (7, 101):
            alterno = IsolationForest(n_estimators=arboles, contamination='auto', random_state=semilla, n_jobs=1)
            alterno.fit(entrenamiento[VARIABLES])
            puntajes = pd.Series(-alterno.score_samples(prueba[VARIABLES]), index=prueba.index)
            seleccion = set(puntajes.nlargest(cantidad).index)
            jaccard = len(principales & seleccion) / len(principales | seleccion)
            agregar('estabilidad_semilla', f'jaccard_top10_42_vs_{semilla}', jaccard, len(prueba),
                    'Estabilidad del ranking, no exactitud de detección de fraude.')
    for fraccion in (.05, .10, .15):
        limite = float(np.quantile(puntajes_train, 1 - fraccion))
        agregar('sensibilidad_umbral', f'fraccion_revision_{fraccion:.2f}',
                int(datos.puntaje_anomalia.ge(limite).sum()), len(datos),
                'Umbral calculado sólo con entrenamiento; empates pueden cambiar la fracción efectiva.')
    columnas = ['serie_evento_id', 'serie_id', 'evento_id', 'producto_canonico_id', 'descripcion_original',
                'vendedor_serie', *VARIABLES, 'puntaje_anomalia', 'umbral_revision', 'senal_revision_modelo',
                'etapa', 'modelo_id', 'regla_sin_ahorro', 'regla_alza_previa_5', 'motivos_reglas', 'revision_humana']
    resultados = datos[columnas].sort_values(['puntaje_anomalia', 'serie_evento_id'], ascending=[False, True])
    revision = resultados.head(20).copy()
    revision['variante_verificada'] = pd.NA
    revision['precio_fuente_revisado'] = pd.NA
    revision['comentario_revision'] = ''
    return dict(resultados=resultados.reset_index(drop=True), evaluacion=pd.DataFrame(metricas),
                revision=revision.reset_index(drop=True), tarjeta=tarjeta)
