"""Auditoría de cobertura, sensibilidad y prueba anual retrospectiva de precios."""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import file_digest
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

from sconto.colab import cargar_paquete
from sconto.dataset import MIN_AMPLITUD, MIN_BASE, MIN_EVENTO, MIN_PREVIO
from sconto.eventos import cargar_eventos
from sconto.normalizar import normalizar
from sconto.rutas import BRONZE, GOLD, REPORTS

SEMILLA = 42
UMBRAL_REGLA = 5
UMBRALES = (2, 3, 5, 7, 10, 15)
ANIOS = (2024, 2025, 2026)
DOMINIO = ['qqp_cdmx', 'tienda_fisica', 'MXN']
VARIABLES = ['alza_previa_pct', 'cambio_previo_pct', 'iqr_base_pct', 'iqr_previo_pct',
             'n_base', 'n_previo', 'amplitud_base_dias', 'dias_desde_precio']
METRICAS = ['accuracy', 'balanced_accuracy', 'precision', 'recall', 'f1', 'brier']
METADATOS = ['id_externo', 'canal', 'moneda', 'vendedor_serie', 'vendedor_o_cadena', 'descripcion_original']


def cargar_nacional(raiz=BRONZE):
    """Lee la revisión nacional como universo propio, con sus identificadores de sucursal."""
    partes = []
    for anio in ANIOS:
        ruta = raiz / 'qqp_nacional' / f'{anio}.parquet'
        if ruta.is_file():
            parte = pd.read_parquet(ruta, columns=[
                'fuente', 'serie_id', 'fecha_precio', 'fecha_captura', 'precio', 'sucursal_id',
                *[col for col in METADATOS if col != 'vendedor_serie']])
            partes.append(parte.assign(vendedor_serie=parte.sucursal_id, plataforma_serie='qqp_nacional'))
    return pd.concat(partes, ignore_index=True) if partes else None


def _media_recortada_diaria(precios):
    # Elimina el 10 % de cada cola sólo si hay suficientes días para recortar.
    orden = np.sort(precios)
    corte = len(orden) // 10
    return orden[corte:len(orden) - corte].mean()


def _resumir_ventana(diarios, inicio, fin, ventana):
    por_serie = diarios.loc[diarios.fecha_precio.between(inicio, fin)].groupby(['fuente', 'serie_id'])
    conteos = por_serie.agg(n=('precio', 'size'), mediana=('precio', 'median'),
                           primero=('precio', 'first'), ultimo=('precio', 'last'),
                           inicio=('fecha_precio', 'min'), fin=('fecha_precio', 'max'))
    if ventana in ('base', 'previo'):
        cuartiles = por_serie.precio.quantile([.25, .75]).unstack().reindex(columns=[.25, .75])
        conteos = conteos.join(cuartiles.rename(columns={.25: 'p25', .75: 'p75'}))
    if ventana == 'base':
        conteos = conteos.join(por_serie.precio.agg(promedio='mean', media_recortada=_media_recortada_diaria))
    return conteos.add_suffix(f'_{ventana}')


def preparar_series(observaciones, eventos, fecha_corte):
    obs = observaciones.assign(fecha_precio=pd.to_datetime(observaciones.fecha_precio))
    obs = obs.loc[obs.fecha_precio.le(fecha_corte)].sort_values('fecha_precio')
    clave = ['fuente', 'serie_id']
    piezas = []
    for evento in eventos.itertuples(index=False):
        recorte = obs.loc[obs.fecha_precio.between(evento.base_inicio, evento.evento_fin)]
        if recorte.empty:
            continue
        diarios = recorte.groupby([*clave, 'fecha_precio'], as_index=False).precio.median()
        # Metadatos de observaciones previas para no definir el universo de predicción con el resultado.
        previo = recorte.loc[recorte.fecha_precio.le(evento.previo_fin)].groupby(clave)[METADATOS].first()
        meta = recorte.groupby(clave)[METADATOS].first()
        meta.loc[previo.index, METADATOS] = previo
        for ventana in ('base', 'previo', 'evento'):
            meta = meta.join(_resumir_ventana(diarios, getattr(evento, f'{ventana}_inicio'),
                                            getattr(evento, f'{ventana}_fin'), ventana))
            meta[f'n_{ventana}'] = meta[f'n_{ventana}'].fillna(0).astype(int)
        meta['evento_id'] = evento.evento_id
        meta['cierre_previo'] = evento.previo_fin
        meta['evento_cerrado'] = fecha_corte > evento.evento_fin
        meta['amplitud_base_dias'] = (meta.fin_base - meta.inicio_base).dt.days
        meta['dias_desde_precio'] = (evento.previo_fin - meta.fin_previo).dt.days
        meta['alza_previa_pct'] = 100 * (meta.mediana_previo / meta.mediana_base - 1)
        meta['cambio_previo_pct'] = 100 * (meta.ultimo_previo / meta.primero_previo - 1)
        for ventana in ('base', 'previo'):
            meta[f'iqr_{ventana}_pct'] = 100 * (meta[f'p75_{ventana}'] - meta[f'p25_{ventana}']) / meta[f'mediana_{ventana}']
        meta['bajada_evento_mxn'] = meta.mediana_previo - meta.mediana_evento
        meta['bajada_evento_pct'] = 100 * (1 - meta.mediana_evento / meta.mediana_previo)
        meta['tienda'] = meta.vendedor_o_cadena.str.split('|', n=1).str[0].str.strip()
        meta['categoria'] = meta.descripcion_original.str.split('|', n=1).str[0].where(
            meta.descripcion_original.str.contains('|', regex=False), 'sin categoría QQP').map(normalizar)
        meta['identidad_sucursal'] = (meta.vendedor_serie.notna() & meta.vendedor_serie.str.strip().ne('') &
                                     ~meta.vendedor_serie.str.startswith('SIN_VENDEDOR_', na=False) &
                                     meta.vendedor_serie.ne('MINIMO_MULTITIENDA'))
        meta['base_amplia'] = meta.amplitud_base_dias.ge(MIN_AMPLITUD) & meta.identidad_sucursal
        meta['minimos_previos'] = meta.base_amplia & meta.n_base.ge(MIN_BASE) & meta.n_previo.ge(MIN_PREVIO)
        meta['historia_antes_del_evento'] = meta.n_base.gt(0) | meta.n_previo.gt(0)
        meta['resultado_observado'] = meta.evento_cerrado & meta.n_evento.ge(MIN_EVENTO) & meta.minimos_previos
        meta['etiqueta_bajo'] = meta.bajada_evento_mxn.gt(0).astype('Int64').where(meta.resultado_observado)
        piezas.append(meta.reset_index())
    return pd.concat(piezas, ignore_index=True) if piezas else pd.DataFrame()


def cobertura_fuentes(observaciones):
    obs = observaciones.assign(fecha_precio=pd.to_datetime(observaciones.fecha_precio).dt.strftime('%Y-%m-%d'),
                               anio=pd.to_datetime(observaciones.fecha_precio).dt.year)
    return obs.groupby(['fuente', 'canal', 'anio']).agg(
        filas=('serie_id', 'size'), series=('serie_id', 'nunique'), productos=('id_externo', 'nunique'),
        dias=('fecha_precio', 'nunique'), primer_precio=('fecha_precio', 'min'),
        ultimo_precio=('fecha_precio', 'max'), ultima_captura_dataset=('fecha_captura', 'max')).reset_index()


def cobertura_resultados(series):
    filas = []
    for (evento, fuente), grupo in series.groupby(['evento_id', 'fuente']):
        for k in (2, 3, 4, 5):
            base = grupo.base_amplia & grupo.n_base.ge(k)
            previo = base & grupo.n_previo.ge(MIN_PREVIO)
            for dias in (1, 2, 3):
                evento_ok = grupo.n_evento.ge(dias)
                etiquetas = previo & evento_ok & grupo.evento_cerrado
                filas.append(dict(evento_id=evento, fuente=fuente, min_fechas_base=k, min_fechas_evento=dias,
                                  universo_serie_ventana=len(grupo), con_historia_previa=int(grupo.historia_antes_del_evento.sum()),
                                  base_suficiente=int(base.sum()), base_y_previo=int(previo.sum()),
                                  con_dias_evento=int(evento_ok.sum()), base_y_evento=int((base & evento_ok).sum()),
                                  resultado_maduro=int(etiquetas.sum()), producto_maduro=grupo.loc[etiquetas, 'id_externo'].nunique(),
                                  bajadas_observadas=int((etiquetas & grupo.bajada_evento_mxn.gt(0)).sum())))
    return pd.DataFrame(filas)


def sensibilidad_reglas(series):
    """Análisis descriptivo de regla y comparación condicional de compra/espera sobre QQP físico."""
    filas = []
    dominio = series.fuente.isin(['qqp_cdmx', 'qqp_nacional']) & series.canal.eq(DOMINIO[1]) & series.moneda.eq(DOMINIO[2])
    grupo_ant = series.loc[dominio & series.evento_cerrado]
    for (evento, fuente), grupo in grupo_ant.groupby(['evento_id', 'fuente']):
        n_universo = int(grupo.historia_antes_del_evento.sum())
        for minimo in (2, 3, 4, 5):
            n_regla = grupo.base_amplia & grupo.n_base.ge(minimo) & grupo.n_evento.ge(MIN_EVENTO)
            sim = grupo.loc[n_regla & grupo.n_previo.ge(MIN_PREVIO)]
            for referencia in ('mediana', 'promedio', 'media_recortada'):
                ref = grupo.loc[n_regla, f'{referencia}_base']
                observado = grupo.loc[n_regla, 'mediana_evento']
                ahorro_pct = (100 * (1 - observado / ref)).round(10)
                ultima_cotizacion = sim.ultimo_previo
                ahorro_pre_evento = (100 * (1 - ultima_cotizacion / sim[f'{referencia}_base'])).round(10)
                for umbral in UMBRALES:
                    favorable = ahorro_pct.ge(umbral) & observado.le(grupo.loc[n_regla, 'p25_base'])
                    alto = ahorro_pct.le(-umbral) & observado.ge(grupo.loc[n_regla, 'p75_base'])
                    comprar = ahorro_pre_evento.ge(umbral) & ultima_cotizacion.le(sim.p25_base)
                    # En espera se compra en el primer precio del evento; toda serie evaluada termina en compra.
                    pago = ultima_cotizacion.where(comprar, sim.primero_evento)
                    beneficio = ultima_cotizacion - pago
                    perdida = pago - np.minimum(ultima_cotizacion, sim.primero_evento)
                    filas.append(dict(
                        evento_id=evento, fuente=fuente, min_fechas_base=minimo, referencia=referencia, umbral_pct=umbral,
                        series_con_historia=n_universo, series_comparables=int(n_regla.sum()),
                        favorables=int(favorable.sum()), altos=int(alto.sum()),
                        sin_senal=int(n_regla.sum() - favorable.sum() - alto.sum()),
                        series_simulables=len(sim), cobertura_simulacion_pct=100 * len(sim) / n_universo if n_universo else np.nan,
                        compra_previa=int(comprar.sum()),
                        compras_antes_de_bajada=int((comprar & ultima_cotizacion.gt(sim.primero_evento)).sum()),
                        oportunidades_de_compra_previa_omitidas=int((~comprar & ultima_cotizacion.lt(sim.primero_evento)).sum()),
                        ahorro_mediano_vs_referencia_mxn=(ref - observado).median(),
                        ahorro_evento_mediano_pct=ahorro_pct.median(), beneficio_medio_vs_comprar_antes_mxn=beneficio.mean(),
                        perdida_media_vs_mejor_observado_mxn=perdida.mean(), decisiones_no_optimas=int(perdida.gt(0).sum())))
    return pd.DataFrame(filas)


def _metricas_recuento(y, predicho, probabilidad, pesos=None):
    pesos = np.ones(len(y), dtype=int) if pesos is None else pesos
    negativos = y == 0
    positivos = y == 1
    tn = int(pesos[negativos & (predicho == 0)].sum())
    fp = int(pesos[negativos & (predicho == 1)].sum())
    fn = int(pesos[positivos & (predicho == 0)].sum())
    tp = int(pesos[positivos & (predicho == 1)].sum())
    recall = tp / (tp + fn) if tp + fn else np.nan
    especificidad = tn / (tn + fp) if tn + fp else np.nan
    return dict(tn=tn, fp=fp, fn=fn, tp=tp, n_negativos=tn+fp, n_positivos=tp+fn,
                accuracy=(tn + tp) / (tn + fp + fn + tp), balanced_accuracy=(recall + especificidad) / 2,
                precision=tp / (tp + fp) if tp + fp else np.nan, recall=recall,
                f1=2 * tp / (2 * tp + fp + fn) if tp + fp + fn else np.nan,
                brier=np.average((probabilidad - y) ** 2, weights=pesos))


def _remuestreos_por_producto(producto, repeticiones=1000):
    estratos, inverso = np.unique(producto, return_inverse=True)
    pesos = np.random.default_rng(SEMILLA).multinomial(len(estratos), [1.0 / len(estratos)] * len(estratos),
                                                     size=repeticiones)
    return pesos[:, inverso]


def _intervalo(valores):
    finitos = np.asarray(valores)
    finitos = finitos[np.isfinite(finitos)]
    return np.quantile(finitos, [.025, .975]).tolist() if len(finitos) else [None, None]


def _probabilidad(modelo, X):
    return modelo.predict_proba(X)[:, list(modelo.classes_).index(1)]


def modelo_supervisado(series):
    dominio = series.loc[series[['fuente', 'canal', 'moneda']].eq(DOMINIO).all(axis=1)].copy()
    cubierto = dominio.minimos_previos & np.isfinite(dominio[VARIABLES].astype(float)).all(axis=1)
    aptos = dominio.loc[cubierto].sort_values(['evento_id', 'serie_id'])
    train = aptos.loc[aptos.evento_id.eq('BF2024') & aptos.resultado_observado].reset_index(drop=True)
    test = aptos.loc[aptos.evento_id.eq('BF2025') & aptos.resultado_observado].reset_index(drop=True)
    prospecto = aptos.loc[aptos.evento_id.eq('BF2026')].copy()
    grupos = train.id_externo.to_numpy()
    compartidos = set(grupos) & set(test.id_externo)
    tarjeta = dict(version='esperar-buen-fin-v2.0', alcance='QQP CDMX, tienda física, MXN',
                   clase_positiva='mediana del evento estrictamente menor que mediana de 14 días previos',
                   variables=VARIABLES, semilla=SEMILLA, sklearn_version=sklearn.__version__, umbral_probabilidad=.5,
                   entrenamiento='BF2024', prueba='BF2025', caracter='reconstrucción retrospectiva',
                   producto_compartido=len(compartidos), productos_solo_prueba=len(set(test.id_externo)-set(grupos)),
                   series_compartidas=len(set(train.serie_id) & set(test.serie_id)),
                   n_entrenamiento=len(train), n_prueba=len(test), n_bf2026_features=len(prospecto),
                   n_bf2026_resultados=int(prospecto.resultado_observado.sum()),
                   estado='experimental', fecha_emision_prospectiva=None,
                   protocolo_cv='CV de hasta 4 particiones por producto dentro de BF2024 (una fecha anual de predicción).',
                   seleccion='Mejor balanced accuracy fuera de partición BF2024, Brier rompe empates; 0.5 fijo.',
                   interpretacion_datos='Fecha del precio QQP como fecha de observación. Archivo recuperado en 2026; la disponibilidad pública de cada fila al corte histórico es desconocida.',
                   previo_explorado='BF2025 y parte de BF2026 se exploraron en entregas anteriores.')
    vacio = dict(metricas=pd.DataFrame(), predicciones=pd.DataFrame(), calibracion=pd.DataFrame(),
                 particiones=pd.DataFrame(), segmentos=pd.DataFrame(), arboles=pd.DataFrame(), protocolo=tarjeta)
    if train.etiqueta_bajo.nunique() < 2 or test.empty:
        tarjeta['motivo'] = 'Faltan clases para el entrenamiento o no hay prueba con resultados comparables.'
        return vacio
    n_folds = min(4, int(train.groupby('etiqueta_bajo').id_externo.nunique().min()))
    if n_folds < 2:
        tarjeta['motivo'] = 'La clase menos frecuente no tiene al menos dos productos independientes.'
        return vacio
    y_train = train.etiqueta_bajo.to_numpy(dtype=int)
    X_train = train[VARIABLES]
    cv = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=SEMILLA)
    particiones = list(cv.split(X_train, y_train, grupos))
    if any(np.unique(y_train[t]).size < 2 for t, _ in particiones):
        tarjeta['motivo'] = 'Una partición de entrenamiento BF2024 quedó sin representación de ambas clases.'
        return vacio
    assert all(not (set(grupos[t]) & set(grupos[v])) for t, v in particiones)
    modelos = {
        'clase_mayoritaria': DummyClassifier(strategy='prior'),
        'regresion_logistica': make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=1000)),
        'arbol_2': DecisionTreeClassifier(max_depth=2, min_samples_leaf=10, random_state=SEMILLA),
        'arbol_3': DecisionTreeClassifier(max_depth=3, min_samples_leaf=10, random_state=SEMILLA),
    }
    folds = train[['evento_id', 'id_externo', 'serie_id']].copy()
    metricas = []
    ramas = []
    cortes_raiz = {}
    for nombre, plantilla in modelos.items():
        pred = np.zeros(len(train), dtype=int)
        prob = np.zeros(len(train))
        for n, (entrenar, validar) in enumerate(particiones, start=1):
            modelo = clone(plantilla).fit(X_train.iloc[entrenar], y_train[entrenar])
            folds.loc[validar, 'particion'] = n
            prob[validar] = _probabilidad(modelo, X_train.iloc[validar])
            pred[validar] = modelo.predict(X_train.iloc[validar])
            if isinstance(modelo, DecisionTreeClassifier):
                raiz = modelo.tree_.feature[0]
                cortes_raiz.setdefault(nombre, []).append(dict(
                    particion=n, variable=VARIABLES[raiz] if raiz >= 0 else None,
                    umbral=float(modelo.tree_.threshold[0]) if raiz >= 0 else None))
                ramas.append(dict(modelo=nombre, particion=n, series_entrenamiento=len(entrenar),
                                  productos_entrenamiento=len(set(grupos[entrenar])),
                                  cortes=export_text(modelo, feature_names=VARIABLES)))
        metricas.append(dict(etapa='validacion_BF2024', modelo=nombre, n_series=len(train),
                             n_productos=train.id_externo.nunique(), **_metricas_recuento(y_train, pred, prob)))
    ranking = pd.DataFrame(metricas).sort_values(['balanced_accuracy', 'brier'], ascending=[False, True])
    seleccionado = ranking.iloc[0].modelo
    tarjeta.update(modelo_elegido_en_2024=seleccionado, particiones_bf2024=n_folds,
                   cortes_raiz_arboles_en_validacion=cortes_raiz)
    y_test = test.etiqueta_bajo.to_numpy(dtype=int)
    X_test = test[VARIABLES]
    pesos = _remuestreos_por_producto(test.id_externo)
    prob_y_pred = {}
    predicciones = []
    calibracion = []
    segmentos = []
    metricas_boot = {}
    base = ['evento_id', 'serie_id', 'id_externo', 'tienda', 'categoria', 'cierre_previo', 'etiqueta_bajo',
            'bajada_evento_mxn', 'bajada_evento_pct', *VARIABLES]
    for nombre, plantilla in modelos.items():
        modelo = clone(plantilla).fit(X_train, y_train)
        if isinstance(modelo, DecisionTreeClassifier):
            ramas.append(dict(modelo=nombre, particion='entrenamiento_completo', series_entrenamiento=len(train),
                              productos_entrenamiento=train.id_externo.nunique(),
                              cortes=export_text(modelo, feature_names=VARIABLES)))
        prob = _probabilidad(modelo, X_test)
        pred = modelo.predict(X_test)
        prob_y_pred[nombre] = (prob, pred, modelo)
        m = dict(etapa='prueba_BF2025', modelo=nombre, n_series=len(test), n_productos=test.id_externo.nunique(),
                 **_metricas_recuento(y_test, pred, prob))
        re = pd.DataFrame(_metricas_recuento(y_test, pred, prob, peso) for peso in pesos)
        metricas_boot[nombre] = re
        for metrica in METRICAS:
            m[f'{metrica}_ic95_inf'], m[f'{metrica}_ic95_sup'] = _intervalo(re[metrica])
        metricas.append(m)
        predicciones.append(test[base].assign(modelo=nombre, prediccion=pred, probabilidad_bajada=prob,
                                              tipo='prueba_retrospectiva', producto_compartido=test.id_externo.isin(compartidos)))
        bins = pd.Series(np.minimum((5 * prob).astype(int), 4))
        for b in range(5):
            v = bins.eq(b).to_numpy()
            calibracion.append(dict(modelo=nombre, prob_min=b/5, prob_max=(b+1)/5, n_series=int(v.sum()),
                                    prob_media=float(prob[v].mean()) if v.any() else None,
                                    frecuencia_bajada=float(y_test[v].mean()) if v.any() else None))
        if nombre == seleccionado:
            test_segmentado = test.assign(producto_compartido=test.id_externo.isin(compartidos))
            for dimension in ('producto_compartido', 'tienda', 'categoria'):
                for valor, parte in test_segmentado.groupby(dimension, dropna=False):
                    idx = parte.index
                    segmentos.append(dict(dimension=dimension, valor=str(valor), n_series=len(parte),
                                          n_productos=parte.id_externo.nunique(),
                                          **_metricas_recuento(y_test[idx], pred[idx], prob[idx])))
    elegido = metricas_boot[seleccionado]
    referencia = metricas_boot['clase_mayoritaria']
    delta = _intervalo(elegido.balanced_accuracy - referencia.balanced_accuracy)
    tarjeta['ic95_diferencia_balanced_accuracy_con_mayoritaria'] = delta
    tarjeta['criterio_publicacion'] = 'Revisión de dominio y estabilidad, con IC95 de mejora sobre referencia completamente positivo.'
    tarjeta['motivo'] = ('Mejora retrospectiva requiere revisión independiente y validación prospectiva en QQP CDMX.'
                         if delta[0] is not None and delta[0] > 0 else
                         'La mejora comparada con la clase mayoritaria no se sostiene en el intervalo por producto.')
    if not prospecto.empty:
        modelo = prob_y_pred[seleccionado][2]
        predicciones.append(prospecto[base].assign(
            modelo=seleccionado, prediccion=modelo.predict(prospecto[VARIABLES]),
            probabilidad_bajada=_probabilidad(modelo, prospecto[VARIABLES]), tipo='reconstruccion_retrospectiva',
            producto_compartido=prospecto.id_externo.isin(grupos)))
    return dict(metricas=pd.DataFrame(metricas), predicciones=pd.concat(predicciones, ignore_index=True),
                calibracion=pd.DataFrame(calibracion), particiones=folds, segmentos=pd.DataFrame(segmentos),
                arboles=pd.DataFrame(ramas), protocolo=tarjeta)


def analizar(observaciones, eventos, fecha_corte=None, nacional=None):
    """Punto de entrada compartido para el notebook y la ejecución local."""
    columnas = ['fuente', 'serie_id', 'fecha_precio', 'fecha_captura', 'precio', 'plataforma_serie', 'tipo_precio', 'metodo', *METADATOS]
    datos = observaciones.reindex(columns=columnas)
    if nacional is not None:
        datos = pd.concat([datos, nacional.reindex(columns=columnas)], ignore_index=True)
    corte = pd.Timestamp(fecha_corte if fecha_corte is not None else pd.to_datetime(datos.fecha_captura).max()).normalize()
    series = preparar_series(datos, eventos, corte)
    auditoria = cobertura_fuentes(datos.loc[pd.to_datetime(datos.fecha_precio).le(corte)])
    online = auditar_horizonte_online(datos, corte)
    if series.empty:
        return dict(series=series, cobertura=auditoria, cobertura_resultado=pd.DataFrame(), sensibilidad=pd.DataFrame(),
                    horizonte_online=online,
                    **{k: pd.DataFrame() for k in ('metricas', 'predicciones', 'calibracion', 'particiones', 'segmentos', 'arboles')},
                    protocolo={'estado': 'sin_observaciones_en_ventanas', 'fecha_corte': str(corte.date())})
    salida = modelo_supervisado(series)
    salida['protocolo']['fecha_corte'] = str(corte.date())
    return dict(series=series, cobertura=auditoria, cobertura_resultado=cobertura_resultados(series),
                sensibilidad=sensibilidad_reglas(series), horizonte_online=online, **salida)


def auditar_horizonte_online(datos, fecha_corte):
    """Comprueba densidad de siete días sin asumir que la descarga indica vigencia en tienda."""
    online = datos.loc[datos.canal.eq('en_linea')].copy()
    online['fecha_precio'] = pd.to_datetime(online.fecha_precio)
    online = online.loc[online.fecha_precio.le(fecha_corte)]
    clave = ['fuente', 'tipo_precio', 'metodo']
    filas = []
    for metadatos, grupo in online.groupby(clave, dropna=False):
        comparables = grupo.loc[grupo.vendedor_serie.notna() & ~grupo.vendedor_serie.str.startswith(
            ('SIN_VENDEDOR_', 'MINIMO_MULTITIENDA'), na=False)]
        dias = comparables[['serie_id', 'fecha_precio']].drop_duplicates().sort_values('fecha_precio')
        ventanas_completas = (dias.groupby('serie_id').fecha_precio.shift(-7) - dias.fecha_precio).dt.days.eq(7)
        filas.append(dict(zip(clave, metadatos), filas=len(grupo), series=grupo.serie_id.nunique(),
                          series_con_vendedor=comparables.serie_id.nunique(),
                          series_con_8_dias_consecutivos=dias.loc[ventanas_completas, 'serie_id'].nunique(),
                          ventanas_de_7_dias_completas=int(ventanas_completas.sum()),
                          primer_precio=str(grupo.fecha_precio.min().date()), ultimo_precio=str(grupo.fecha_precio.max().date())))
    return pd.DataFrame(filas)


def _figuras(resultado, salida):
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    tabla = resultado['sensibilidad']
    if not tabla.empty:
        tabla = tabla.loc[tabla.fuente.eq('qqp_cdmx') & tabla.min_fechas_base.eq(MIN_BASE) & tabla.referencia.eq('mediana')]
        fig, ejes = plt.subplots(3, 1, sharex=True, figsize=(8.4, 8.4), layout='constrained')
        fig.suptitle('Sensibilidad de la regla de precio en QQP CDMX')
        for evento, grupo in tabla.groupby('evento_id'):
            umbrales = grupo.umbral_pct
            series = grupo.series_simulables.iloc[0]
            etiqueta = f'{evento} ({series} series simulables)'
            ejes[0].plot(umbrales, grupo.beneficio_medio_vs_comprar_antes_mxn, 'o-', label=etiqueta)
            ejes[1].plot(umbrales, 100 * grupo.decisiones_no_optimas / grupo.series_simulables, 'o-')
            ejes[2].plot(umbrales, 100 * (grupo.favorables + grupo.altos) / grupo.series_con_historia, 'o-')
        ejes[-1].set(xticks=UMBRALES, xlabel='Umbral de diferencia frente a la mediana (%)')
        ejes[0].set_ylabel('Beneficio medio\nfrente a comprar antes (MXN)')
        ejes[1].set_ylabel('Compras a mayor precio\nque la mejor de dos fechas (%)')
        ejes[2].set_ylabel('Series con señal de precio\nsobre series con historial (%)')
        ejes[0].legend(frameon=False)
        for eje in ejes:
            eje.grid(alpha=.23)
            eje.axvline(UMBRAL_REGLA, color='.6', linestyle='--', linewidth=1)
        fig.savefig(salida / 'sensibilidad_umbrales.png', dpi=150)
        plt.close(fig)
    tabla = resultado['calibracion']
    if not tabla.empty:
        fig, eje = plt.subplots(figsize=(6.2, 5.7), layout='constrained')
        eje.plot([0, 1], [0, 1], '--', color='.6', label='Correspondencia perfecta')
        for nombre, grupo in tabla.loc[tabla.n_series.gt(0)].groupby('modelo'):
            eje.plot(grupo.prob_media, grupo.frecuencia_bajada, alpha=.75, label=nombre.replace('_', ' '))
            eje.scatter(grupo.prob_media, grupo.frecuencia_bajada, s=12 + 1.2 * grupo.n_series)
        eje.set(xlim=(0, 1), ylim=(0, 1), xlabel='Probabilidad media estimada',
                ylabel='Frecuencia de bajada observada', title='Calibración retrospectiva, QQP CDMX BF2025')
        eje.legend(frameon=False)
        eje.grid(alpha=.23)
        fig.savefig(salida / 'calibracion_bf2025.png', dpi=150)
        plt.close(fig)


def _redactar_reglas(resultado, reglas):
    a = resultado['sensibilidad']
    modelo = resultado['protocolo']
    cobertura = resultado['cobertura']
    base = (a.loc[a.fuente.eq('qqp_cdmx') & a.min_fechas_base.eq(MIN_BASE) & a.referencia.eq('mediana') &
                  a.umbral_pct.eq(UMBRAL_REGLA)] if not a.empty else a)
    filas = ['| Evento | Series con historia | Base y evento | Base, previo y evento | Precio favorable | Precio alto |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    filas.extend(f'| {r.evento_id} | {r.series_con_historia:,} | {r.series_comparables:,} | {r.series_simulables:,} | '
                 f'{r.favorables:,} | {r.altos:,} |' for r in base.itertuples(index=False))
    recientes = cobertura.loc[cobertura.anio.eq(2026) & cobertura.fuente.isin(['qqp_cdmx', 'qqp_nacional'])]
    corte_qqp = ', '.join(f'{r.fuente} al {r.ultimo_precio}' for r in recientes.itertuples(index=False)) or 'sin datos QQP 2026'
    comparacion = resultado['metricas']
    if not comparacion.empty:
        comparacion = comparacion.loc[comparacion.etapa.eq('prueba_BF2025')].set_index('modelo')
        elegido = modelo['modelo_elegido_en_2024']
        nombre_elegido = elegido.replace('arbol_', 'el árbol de profundidad ') if elegido.startswith('arbol_') else elegido.replace('_', ' ')
        ganador, referencia = comparacion.loc[elegido], comparacion.loc['clase_mayoritaria']
        parrafo = (
            f'Dentro de BF2024 se seleccionó {nombre_elegido}. En BF2025 ('
            f'{ganador.n_series} series, {ganador.n_productos} productos), la exactitud balanceada fue '
            f'{ganador.balanced_accuracy:.1%} (IC95% por producto {ganador.balanced_accuracy_ic95_inf:.1%} a '
            f'{ganador.balanced_accuracy_ic95_sup:.1%}), frente a {referencia.balanced_accuracy:.1%} de la '
            f'clase mayoritaria. La matriz registró {ganador.tn} verdaderos negativos, {ganador.fp} falsos positivos, '
            f'{ganador.fn} falsos negativos y {ganador.tp} verdaderos positivos. Un falso positivo pronostica una '
            'bajada que no se observó. Un falso negativo omite una bajada observada. El resultado es experimental.')
    else:
        parrafo = modelo.get('motivo', 'Sin muestra para el modelo.')
    cortes = modelo.get('cortes_raiz_arboles_en_validacion', {}).get(modelo.get('modelo_elegido_en_2024'), [])
    estabilidad = ''
    if cortes:
        resumen = pd.DataFrame(cortes).groupby('variable').umbral.agg(['size', 'min', 'max'])
        detalle = ', '.join(f'{v} en {int(x["size"])} de {len(cortes)} particiones, cortes '
                            f'{x["min"]:.2f}% a {x["max"]:.2f}%' for v, x in resumen.iterrows())
        estabilidad = f'La variable del primer corte del árbol varió entre particiones. {detalle}.'
    return '\n'.join([
        '# Justificación provisional de las reglas de precio', '',
        f'Corte del análisis {modelo["fecha_corte"]}.', '',
        '## Regla activa', '',
        'Se conserva la regla precio-v1. Clasifica como favorable si el precio ahorra al menos 5% frente a la '
        'mediana y está en el cuartil inferior. Clasifica como alto si cuesta al menos 5% más y está en el '
        'cuartil superior. El 5% procede del diseño inicial y sigue siendo provisional.', '',
        f'Cada día aporta una mediana. Se exigen {reglas["min_fechas_base"]} fechas base en un tramo de '
        f'{reglas["amplitud_base_dias"]} días calendario o más, al menos una fecha de evento y dos del periodo '
        'previo para estudiar un alza. Las cuatro fechas y la amplitud son el protocolo del Avance 1. '
        'La sensibilidad reevalúa entre dos y cinco fechas base y entre una y tres de evento.', '',
        '## Muestra física CDMX, mediana y umbral de 5%', '', *filas, '',
        'La simulación compra a la última cotización observada antes del evento cuando la regla marca precio '
        'favorable. En otro caso compra al primer precio del evento. El beneficio se compara contra comprar '
        'siempre a esa última cotización previa. La pérdida se compara contra el menor precio de esas dos '
        'fechas, sin imputar días ni asumir compras realizadas. Se conservan los resultados para 2, 3, 5, 7, 10 '
        'y 15% con mediana, promedio y media recortada al 10% por cola. QQP nacional conserva su propio '
        'universo y contiene CDMX. Los resultados se leen por separado. La simulación no incorpora envío, '
        'condiciones de pago, inventario, ni preferencias del comprador.', '',
        '## Modelo de espera', '', parrafo, '', estabilidad, '',
        f'Los conjuntos contienen {modelo.get("producto_compartido", 0)} productos compartidos y '
        f'{modelo.get("productos_solo_prueba", 0)} productos exclusivos de la prueba, según los identificadores QQP. '
        'BF2025 y parte de BF2026 ya se exploraron en el proyecto. La prueba queda fija y el modelo queda fuera '
        'de la app. QQP se recuperó retrospectivamente en 2026. No se conoce la fecha de publicación por fila.', '',
        f'El corte disponible para 2026 es {corte_qqp}. El evento 2026 queda abierto. El diagnóstico de siete días '
        'mide continuidad con observaciones diarias de la misma serie. Falta confirmar vigencia en tienda y '
        'validar años comparables para un modelo online. No se presenta evaluación de 2026.', '',
        '[Validación por grupos en scikit-learn](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data)', ''])


def escribir_resultados(resultado, salida, procedencia=None):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    reglas = dict(version='precio-v1', estado='provisional', umbral_ahorro_pct=UMBRAL_REGLA,
                  origen='Regla de diseño del proyecto aplicada antes del estudio',
                  min_fechas_base=MIN_BASE, min_fechas_evento=MIN_EVENTO, min_fechas_previo=MIN_PREVIO,
                  amplitud_base_dias=MIN_AMPLITUD, referencia='mediana de medianas diarias',
                  favorable='ahorro >= umbral y precio <= P25', alto='ahorro <= -umbral y precio >= P75',
                  cobertura='serie comparable con historia suficiente, observación vigente e identidad comprobada',
                  muestra_sensibilidad='QQP físico CDMX 2024/2025; QQP nacional descriptivo por separado',
                  objetivo='Describir precios observados y simular el costo de una política fija de compra o espera',
                  limite='El cambio observado aún no valida el criterio de utilidad para compras online.')
    tablas = dict(cobertura='cobertura_historica_v2', cobertura_resultado='cobertura_resultados_v2',
                  sensibilidad='sensibilidad_umbrales', metricas='metricas_buen_fin_v2',
                  predicciones='predicciones_retrospectivas_v2', calibracion='calibracion_bf2025',
                  particiones='particiones_entrenamiento_bf2024', segmentos='segmentos_prueba_bf2025',
                  arboles='cortes_arbol_bf2024', horizonte_online='viabilidad_7_dias_v2')
    for clave, archivo in tablas.items():
        resultado[clave].to_csv(salida / f'{archivo}.csv', index=False)
    objetos = dict(reglas_v2=reglas, protocolo_modelo_v2=resultado['protocolo'])
    if procedencia:
        objetos['procedencia_historica_v2'] = procedencia
    for archivo, obj in objetos.items():
        (salida / f'{archivo}.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (salida / 'justificacion_reglas.md').write_text(_redactar_reglas(resultado, reglas), encoding='utf-8')
    _figuras(resultado, salida)


def _sha256(path):
    with path.open('rb') as archivo:
        return file_digest(archivo, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    origen = parser.add_mutually_exclusive_group()
    origen.add_argument('--paquete', type=Path, help='ZIP de exportación con hashes verificados.')
    origen.add_argument('--observaciones', type=Path, help='Parquet gold de observaciones.')
    parser.add_argument('--fecha-corte', type=date.fromisoformat, help='Día del corte YYYY-MM-DD.')
    parser.add_argument('--sin-nacional', action='store_true', help='Reproducir sólo el universo del paquete.')
    parser.add_argument('--salida', type=Path, default=REPORTS)
    args = parser.parse_args()
    origen = args.paquete or args.observaciones or (GOLD / 'observaciones.parquet')
    nacional = None if args.sin_nacional else cargar_nacional()
    if args.paquete:
        paquete = cargar_paquete(origen)
        obs, eventos = paquete['observaciones'], paquete['eventos']
    else:
        obs, eventos = pd.read_parquet(origen), cargar_eventos()
    resultado = analizar(obs, eventos, fecha_corte=args.fecha_corte, nacional=nacional)
    fuentes = {origen.name: {'filas': len(obs), 'sha256': _sha256(origen)}}
    if nacional is not None:
        for anio in ANIOS:
            ruta = BRONZE / 'qqp_nacional' / f'{anio}.parquet'
            if ruta.is_file():
                fuentes[f'qqp_nacional/{ruta.name}'] = {
                    'filas': int(pd.to_datetime(nacional.fecha_precio).dt.year.eq(anio).sum()), 'sha256': _sha256(ruta)}
    escribir_resultados(resultado, args.salida, procedencia=dict(
        archivo_codigo_sha256=_sha256(Path(__file__)), fuentes=fuentes, pandas_version=pd.__version__,
        sklearn_version=sklearn.__version__, fecha_corte=resultado['protocolo']['fecha_corte']))
    print(json.dumps(resultado['protocolo'], ensure_ascii=True))


if __name__ == '__main__':
    main()


