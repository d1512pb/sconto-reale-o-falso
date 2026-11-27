"""Exporta el modelo final para la app y la API: tarjeta (modelo.json) y árbol sin dependencias (arbol.json)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sconto.modelo_final import NOMBRES_VARIABLES, VERSION

VERSION_APP = 'sconto-modelo-app-v1'
CONJUNTOS = ['Prueba 2025 · QQP sucursales', 'Validación final 2026 · Preciómetro', 'Validación final 2026 · PROFECO']


def casos_por_nodo(modelo, datos: pd.DataFrame, variables) -> dict:
    """Series de entrenamiento (QQP 2018–2025) que llegan a cada nodo y cuántas bajaron."""
    entrenamiento = datos.loc[datos.fuente.eq('qqp_cdmx') & datos.anio.le(2025)]
    ruta = modelo.decision_path(entrenamiento[variables].to_numpy(dtype=float))
    y = entrenamiento.y.to_numpy()
    return {i: (int(ruta[:, i].sum()), int(y[ruta[:, i].toarray().ravel() == 1].sum())) for i in range(ruta.shape[1])}


def exportar_arbol(modelo, variables, casos=None) -> dict:
    """Árbol de scikit-learn a JSON. Recorrido: izquierda si x[variable] <= umbral."""
    from sklearn.tree import DecisionTreeClassifier
    est = modelo[-1] if hasattr(modelo, 'steps') else modelo
    if not isinstance(est, DecisionTreeClassifier) or hasattr(modelo, 'steps'):
        raise TypeError('La exportación ligera sólo admite un árbol de decisión sin transformaciones.')
    t = est.tree_
    clase = list(est.classes_).index(1)
    nodos = []
    for i in range(t.node_count):
        valor = t.value[i][0]
        nodos.append(dict(izq=int(t.children_left[i]), der=int(t.children_right[i]),
                          variable=variables[t.feature[i]] if t.children_left[i] != -1 else None,
                          umbral=float(t.threshold[i]) if t.children_left[i] != -1 else None,
                          prob_bajada=float(valor[clase] / valor.sum()), muestras=int(t.n_node_samples[i]),
                          casos=(casos or {}).get(i, (None, None))[0], bajaron=(casos or {}).get(i, (None, None))[1]))
    tasa = None if not casos else casos[0][1] / casos[0][0]
    return dict(version=VERSION, tipo='arbol_decision', variables=list(variables), tasa_general=tasa,
                nombres={v: NOMBRES_VARIABLES.get(v, v) for v in variables}, nodos=nodos)


def hallazgos(conclusiones: Path) -> tuple[list[str], dict]:
    """Frases con datos para la app, a partir de `sconto.conclusiones`."""
    if not (conclusiones / 'conclusiones.json').is_file():
        return [], {}
    c = json.loads((conclusiones / 'conclusiones.json').read_text(encoding='utf-8'))
    r = {f['poblacion']: f for f in c['resumen']}
    d = {f['fuente']: f for f in c['dispersion']}
    bf, normal = r['QQP sucursales · Buen Fin 2018–2025'], r['QQP sucursales · semanas normales']
    linea, senuelo = r['Preciómetro en línea · Buen Fin 2026'], d['Preciómetro · tiendas en línea 2026']
    fina = pd.read_csv(conclusiones / 'busqueda_fina_umbral.csv')
    mejor = fina.loc[fina.youden_j.idxmax()]
    empates = fina.loc[fina.equivalente_al_mejor, 'umbral_pct'].tolist()
    frases = [
        f"En sucursales físicas (QQP, Buen Fin 2018–2025) el {bf['pct_rebaja_real']:.0f} % de los precios bajó al menos 5 % frente a su historia; en semanas normales sólo el {normal['pct_rebaja_real']:.0f} %.",
        f"En línea (Buen Fin 2026) más de la mitad ({100 - linea['pct_favorable']:.0f} %) no mostró una oferta clara: {linea['pct_sin_senal']:.0f} % sin señal y {linea['pct_alto']:.0f} % más caro que su historia; sólo {linea['pct_favorable']:.0f} % fue favorable.",
        f"Subir y bajar: {bf['pct_subir_y_bajar']:.0f} % de las series subió antes del Buen Fin y bajó en el evento; en {bf['pct_subir_y_bajar_paga_igual_o_mas']:.0f} % de esos casos terminabas pagando lo mismo o más que antes.",
        f"Si comparas contra el precio de las dos semanas previas, {bf['pct_ofertas_aparentes_sin_ahorro_real']:.0f} % de las 'ofertas' del Buen Fin y {normal['pct_ofertas_aparentes_sin_ahorro_real']:.0f} % en semanas normales no son ahorro real. La regla de Sconto no marcó ninguna como favorable.",
        f"Precio señuelo: en línea, la tienda más cara del mismo producto y día está {senuelo['mas_cara_sobre_mediana_mediana_pct']:.1f} % arriba de la mediana (en {senuelo['pct_mas_cara_30_o_mas']:.0f} % de los casos, 30 % o más). Compararte con ella te hace ver un {senuelo['descuento_aparente_vs_mas_cara_mediana_pct']:.0f} % de 'descuento' que no existe.",
    ]
    umbral = dict(probados=len(fina), desde=float(fina.umbral_pct.min()), hasta=float(fina.umbral_pct.max()),
                  mejor=float(mejor.umbral_pct), mejor_j=float(mejor.youden_j), equivalentes=[float(x) for x in empates])
    return frases, umbral


def tarjeta(resultados: Path, paquete: dict, conclusiones: Path | None = None) -> dict:
    r = json.loads((resultados / 'resumen.json').read_text(encoding='utf-8'))
    metricas = pd.read_csv(resultados / 'metricas_finales.csv')
    pred = pd.read_csv(resultados / 'predicciones.csv')
    imp = pd.read_csv(resultados / 'importancia_variables.csv')
    datos = pd.read_csv(resultados / 'dataset_modelado.csv')
    con_p25 = pd.read_csv(resultados / 'umbral_regla_app_con_p25.csv')
    sin_p25 = pd.read_csv(resultados / 'umbral_regla_app_sin_p25.csv')
    precision = pd.read_csv(resultados / 'precision_referencia_fechas.csv')
    estudio = pd.read_csv(resultados / 'estudio_evento_semanal.csv')
    elegido = r['modelo_elegido']
    familia = elegido['familia']

    en5 = con_p25.loc[con_p25.umbral_pct.eq(5)].iloc[0]
    mejor = con_p25.loc[con_p25.youden_j.idxmax()]
    k4, k3 = precision.set_index('k').loc[4], precision.set_index('k').loc[3]
    sem = estudio.set_index('semana').promedio

    def n(evento=None, fuente='qqp_cdmx', hasta=None):
        d = datos.loc[datos.fuente.eq(fuente)]
        if hasta:
            d = d.loc[d.anio.le(hasta)]
        return len(d)

    finales = pred.loc[pred.familia.eq(familia) & pred.conjunto.eq('Validación final 2026 · Preciómetro')
                       & pred.producto_canonico_id.notna()]
    variables = paquete['variables']
    casos = casos_por_nodo(paquete['modelo'], datos, variables)
    tasa_general = casos[0][1] / casos[0][0]
    filas_2026 = datos.loc[datos.fuente.eq('preciometro') & datos.anio.eq(2026)].set_index('serie_id')
    hojas = dict(zip(filas_2026.index, paquete['modelo'].apply(filas_2026[variables].to_numpy(dtype=float))))
    predicciones = {}
    for f in finales.itertuples():
        n_hoja, bajaron_hoja = casos[int(hojas[f.serie_id])]
        predicciones[f.producto_canonico_id] = dict(
            prob_bajada=round(float(f.prob_bajada), 4), prediccion=int(f.prediccion), bajo=int(f.y),
            bajada_pct=round(float(f.bajada_evento_pct), 2), acierto=bool(int(f.prediccion) == int(f.y)), evento='BF2026',
            casos_parecidos=n_hoja, pct_bajaron_parecidos=round(100 * bajaron_hoja / n_hoja, 1))
    fila_2026 = metricas.loc[metricas.familia.eq(familia) & metricas.conjunto.eq('Validación final 2026 · Preciómetro')].iloc[0]
    columnas = ['conjunto', 'familia', 'n', 'positivos', 'accuracy', 'balanced_accuracy', 'precision', 'recall', 'f1', 'auc']
    return dict(
        version=VERSION_APP, modelo_version=VERSION, corte=r['corte'],
        pregunta='¿Bajará el precio de este producto de tecnología durante el Buen Fin?',
        etiqueta=('"Bajó" significa que la mediana del precio durante el evento quedó por debajo de la mediana de las '
                  'dos semanas previas, en la misma serie (producto y tienda). Las variables sólo usan precios anteriores al evento.'),
        esquema=[
            dict(etapa='Entrenamiento', descripcion=f'Buen Fin 2018–2023 · {n(hasta=2023):,} series de QQP (sucursales físicas de CDMX).'),
            dict(etapa='Validación', descripcion='2022, 2023 y 2024, cada año entrenado sólo con los anteriores. Se eligió la variante con mejor balanced accuracy promedio.'),
            dict(etapa='Prueba', descripcion=f'Buen Fin 2025 · {len(datos.loc[datos.anio.eq(2025)])} series que no participaron en ninguna decisión.'),
            dict(etapa='Validación final', descripcion=f'Buen Fin 2026 · {n(fuente="preciometro")} productos de Preciómetro (mínimo en línea) y {n(fuente="profeco_bf2026")} series del piloto PROFECO.')],
        conjuntos=CONJUNTOS,
        metricas=[{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in row.items()}
                  for row in metricas[columnas].to_dict(orient='records')],
        tasa_general_bajada=round(100 * tasa_general, 1),
        modelo=dict(familia=familia, variante=elegido['variante'], bal_acc_validacion=elegido['bal_acc_validacion'],
                    bal_acc_2026=float(fila_2026.balanced_accuracy), accuracy_2026=float(fila_2026.accuracy),
                    entrenamiento=f'los Buen Fin 2018–2025 ({n(hasta=2025):,} series de QQP)'),
        importancias=imp.head(6).to_dict(orient='records'),
        reglas=dict(umbral_pct=5, min_fechas_base=4, min_amplitud_dias=21),
        umbrales=dict(
            regla_app=dict(umbral_pct=5, pct_buen_fin=float(en5.pct_buen_fin), pct_semanas_normales=float(en5.pct_semanas_normales),
                           youden_j=float(en5.youden_j), mejor_umbral=float(mejor.umbral_pct), mejor_j=float(mejor.youden_j),
                           normal_sin_p25=float(sin_p25.loc[sin_p25.umbral_pct.eq(5), 'pct_semanas_normales'].iloc[0])),
            fechas=dict(k=4, pct_error_mayor_5=float(k4.pct_error_mayor_5), error_p90_k3=float(k3.error_p90)),
            estudio=dict(evento=float(sem.loc[0]), antes=float(sem.loc[-1]), despues=float(sem.loc[1]))),
        arquitectura=('Fuentes públicas (QQP, Preciómetro y consulta del Buen Fin de PROFECO) → ETL bronze/silver/gold con huellas SHA-256 → '
                      'modelo de scikit-learn evaluado por años → API FastAPI en Fly.io con almacén SQLite en volumen cifrado → '
                      'app web instalable (PWA) y APK Android que funcionan sin conexión con el último corte.'),
        limites=('El modelo aprendió de sucursales físicas; en 2026 se valida con precios en línea y con 17 series de PROFECO. '
                 'No hay datos después del 17 de noviembre ni ofertas en línea verificadas con vendedor, inventario y total. '
                 'Una predicción no sustituye confirmar variante, vendedor, envío y precio final.'),
        predicciones=predicciones,
        **dict(zip(('hallazgos', 'busqueda_umbral'), hallazgos(conclusiones) if conclusiones else ([], {}))))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resultados', type=Path, default=Path('reports/modelo_final'))
    p.add_argument('--modelo', type=Path, required=True, help='modelo_final.joblib')
    p.add_argument('--salida', type=Path, required=True)
    p.add_argument('--conclusiones', type=Path, default=Path('reports/conclusiones'))
    a = p.parse_args(argv)
    import joblib
    paquete = joblib.load(a.modelo)
    a.salida.mkdir(parents=True, exist_ok=True)
    card = tarjeta(a.resultados, paquete, a.conclusiones)
    (a.salida / 'modelo.json').write_text(json.dumps(card, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    datos = pd.read_csv(a.resultados / 'dataset_modelado.csv')
    arbol = exportar_arbol(paquete['modelo'], paquete['variables'], casos_por_nodo(paquete['modelo'], datos, paquete['variables']))
    (a.salida / 'arbol.json').write_text(json.dumps(arbol, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(dict(predicciones=len(card['predicciones']), nodos=len(arbol['nodos']), modelo=card['modelo']), ensure_ascii=False))


if __name__ == '__main__':
    main()
