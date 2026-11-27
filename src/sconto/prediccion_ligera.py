"""Predicción sin dependencias pesadas para la API (sólo biblioteca estándar).

Reproduce las variables de `v2_history.preparar_series` a partir de una lista de precios fechados y evalúa el
árbol exportado por `app_modelo`. Las pruebas comprueban que coincide con pandas y scikit-learn.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

MIN_BASE, MIN_AMPLITUD, MIN_PREVIO = 4, 21, 2


def _cuantil(valores: list[float], q: float) -> float:
    v = sorted(valores)
    pos = (len(v) - 1) * q
    i = math.floor(pos)
    return v[i] + ((pos - i) * (v[i + 1] - v[i]) if i + 1 < len(v) else 0.0)


def ventanas(inicio_evento: date) -> dict:
    return dict(base=(inicio_evento - timedelta(days=60), inicio_evento - timedelta(days=15)),
                previo=(inicio_evento - timedelta(days=14), inicio_evento - timedelta(days=1)))


def diarios(precios: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """Una mediana por día, como en el ETL."""
    por_dia: dict[date, list[float]] = {}
    for fecha, precio in precios:
        por_dia.setdefault(fecha, []).append(float(precio))
    return sorted((f, statistics.median(v)) for f, v in por_dia.items())


def caracteristicas(precios: list[tuple[date, float]], inicio_evento: date) -> dict:
    """Variables del modelo con los precios anteriores al evento. No usa ningún precio del evento."""
    v = ventanas(inicio_evento)
    dias = diarios(precios)
    base = [(f, p) for f, p in dias if v['base'][0] <= f <= v['base'][1]]
    previo = [(f, p) for f, p in dias if v['previo'][0] <= f <= v['previo'][1]]
    salida = dict(n_base=len(base), n_previo=len(previo),
                  base_inicio=v['base'][0].isoformat(), base_fin=v['base'][1].isoformat(),
                  previo_inicio=v['previo'][0].isoformat(), previo_fin=v['previo'][1].isoformat())
    faltan = []
    if len(base) < MIN_BASE:
        faltan.append(f'al menos {MIN_BASE} días con precio entre {salida["base_inicio"]} y {salida["base_fin"]}')
    if len(previo) < MIN_PREVIO:
        faltan.append(f'al menos {MIN_PREVIO} días con precio entre {salida["previo_inicio"]} y {salida["previo_fin"]}')
    if not base or not previo:
        return dict(salida, completo=False, faltan=faltan)
    pb, pp = [p for _, p in base], [p for _, p in previo]
    mb, mp = statistics.median(pb), statistics.median(pp)
    amplitud = (base[-1][0] - base[0][0]).days
    if amplitud < MIN_AMPLITUD:
        faltan.append(f'que la base abarque al menos {MIN_AMPLITUD} días (abarca {amplitud})')
    salida.update(
        mediana_base=mb, p25_base=_cuantil(pb, .25), p75_base=_cuantil(pb, .75), mediana_previo=mp,
        amplitud_base_dias=amplitud,
        dias_desde_precio=(v['previo'][1] - previo[-1][0]).days,
        alza_previa_pct=100 * (mp / mb - 1),
        cambio_previo_pct=100 * (pp[-1] / pp[0] - 1),
        iqr_base_pct=100 * (_cuantil(pb, .75) - _cuantil(pb, .25)) / mb,
        iqr_previo_pct=100 * (_cuantil(pp, .75) - _cuantil(pp, .25)) / mp,
        log_precio_previo=math.log(mp))
    return dict(salida, completo=not faltan, faltan=faltan)


def evaluar_arbol(arbol: dict, x: dict) -> float:
    """Probabilidad de 'bajará' en la hoja que corresponde a x (mismo recorrido que scikit-learn)."""
    nodo = 0
    nodos = arbol['nodos']
    while nodos[nodo]['izq'] != -1:
        n = nodos[nodo]
        nodo = n['izq'] if float(x[n['variable']]) <= n['umbral'] else n['der']
    return float(nodos[nodo]['prob_bajada'])


def hoja_arbol(arbol: dict, x: dict) -> dict:
    """Hoja alcanzada: casos parecidos del entrenamiento y cuántos bajaron."""
    nodo, nodos = 0, arbol['nodos']
    while nodos[nodo]['izq'] != -1:
        n = nodos[nodo]
        nodo = n['izq'] if float(x[n['variable']]) <= n['umbral'] else n['der']
    return nodos[nodo]


def ruta_arbol(arbol: dict, x: dict) -> list[str]:
    """Reglas recorridas, para explicar la predicción en lenguaje simple."""
    pasos, nodo, nodos = [], 0, arbol['nodos']
    while nodos[nodo]['izq'] != -1:
        n = nodos[nodo]
        valor = float(x[n['variable']])
        izquierda = valor <= n['umbral']
        pasos.append(f"{arbol['nombres'].get(n['variable'], n['variable'])} = {valor:.2f} "
                     f"{'≤' if izquierda else '>'} {n['umbral']:.2f}")
        nodo = n['izq'] if izquierda else n['der']
    return pasos


def regla_precio(precio: float, mediana: float, p25: float, p75: float, umbral: float = 5) -> dict:
    ahorro = 100 * (1 - precio / mediana)
    estado = ('precio_favorable' if ahorro >= umbral and precio <= p25 else
              'precio_alto' if ahorro <= -umbral and precio >= p75 else 'sin_senal_clara')
    return dict(estado=estado, ahorro_pct=ahorro, mediana=mediana, p25=p25, p75=p75, umbral_pct=umbral)
