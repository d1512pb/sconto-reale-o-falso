"""Regla de consulta online sobre precios totales comparables y evidencia vigente."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from statistics import median, quantiles


VERSION = 'precio-v2-provisional'
UMBRAL_PCT = 5
MIN_DIAS_BASE = 4
AMPLITUD_BASE_DIAS = 21
VIGENCIA_DIRECTA = timedelta(hours=2)


def _instante(valor):
    try:
        instante = datetime.fromisoformat(valor) if isinstance(valor, str) else valor
        if isinstance(instante, datetime) and instante.utcoffset() is not None:
            return instante.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        pass
    return None


def _dia(valor):
    try:
        return date.fromisoformat(valor) if isinstance(valor, str) else valor if type(valor) is date else None
    except ValueError:
        return None


def _monto(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and isfinite(valor) and valor > 0


def _texto(oferta, campo):
    valor = oferta.get(campo)
    return isinstance(valor, str) and bool(valor.strip())


def _misma_serie(oferta, fila):
    return all(_texto(oferta, campo) and oferta.get(campo) == fila.get(campo)
               for campo in ('offer_id', 'moneda', 'contexto_costo'))


def referencia_diaria(precios, oferta, *, base_inicio, base_fin, hoy=None):
    """Calcula cuantiles sobre totales confirmados. Cada día tiene el mismo peso."""
    inicio, fin = _dia(base_inicio), _dia(base_fin)
    hoy = _dia(hoy) if hoy is not None else datetime.now(timezone.utc).date()
    if inicio is None or fin is None or hoy is None or inicio > fin:
        raise ValueError('Fechas de la referencia inválidas')
    dias = defaultdict(list)
    for fila in precios:
        fecha = _dia(fila.get('fecha_precio'))
        total = fila.get('costo_total_confirmado')
        if (fecha is not None and inicio <= fecha <= fin and fecha < hoy
                and fila.get('verificacion') == 'directa' and fila.get('identidad_confirmada') is True
                and fila.get('disponibilidad') == 'en_stock' and _misma_serie(oferta, fila) and _monto(total)):
            dias[fecha].append(total)
    valores = [median(precios) for precios in dias.values()]
    cuartiles = quantiles(valores, n=4, method='inclusive') if len(valores) >= MIN_DIAS_BASE else [None] * 3
    return dict(offer_id=oferta.get('offer_id'), moneda=oferta.get('moneda'),
                contexto_costo=oferta.get('contexto_costo'), n_dias=len(dias),
                amplitud_dias=(max(dias) - min(dias)).days if dias else 0,
                inicio=inicio.isoformat(), fin=fin.isoformat(), cerrada=fin < hoy,
                mediana=median(valores) if valores else None, p25=cuartiles[0], p75=cuartiles[2])


def _referencia_suficiente(oferta, referencia):
    return (referencia is not None and _misma_serie(oferta, referencia) and referencia.get('cerrada') is True
            and type(referencia.get('n_dias')) is int and referencia['n_dias'] >= MIN_DIAS_BASE
            and type(referencia.get('amplitud_dias')) is int and referencia['amplitud_dias'] >= AMPLITUD_BASE_DIAS
            and all(_monto(referencia.get(k)) for k in ('mediana', 'p25', 'p75'))
            and referencia['p25'] <= referencia['mediana'] <= referencia['p75'])


def evaluar_decision(oferta, referencia=None, *, ahora=None):
    """Devuelve clasificación y causas de abstención sobre la oferta exacta."""
    consultado = _instante(ahora) if ahora is not None else datetime.now(timezone.utc)
    if consultado is None:
        raise ValueError('La hora de consulta requiere zona horaria')
    observado = _instante(oferta.get('observed_at')) if oferta.get('precision_temporal') == 'instante' else None
    verificacion_directa = oferta.get('verificacion') == 'directa'
    delta = consultado - observado if observado else None
    edad = delta.total_seconds() / 60 if delta is not None and delta >= timedelta(0) else None
    vigencia = observado + VIGENCIA_DIRECTA if observado and verificacion_directa else None
    vigente = verificacion_directa and edad is not None and consultado < vigencia
    total = oferta.get('costo_total_confirmado')
    motivos = []
    if oferta.get('canal') != 'en_linea':
        motivos.append('canal_fisico')
    if not verificacion_directa:
        motivos.append('fuente_sin_verificacion_directa')
    elif not vigente:
        motivos.append('fecha_insuficiente' if edad is None else 'dato_vencido')
    if (oferta.get('identidad_confirmada') is not True or
            not all(_texto(oferta, campo) for campo in ('offer_id', 'variante', 'vendedor', 'condicion'))):
        motivos.append('identidad_incompleta')
    if oferta.get('disponibilidad') != 'en_stock':
        motivos.append('disponibilidad_sin_confirmar' if oferta.get('disponibilidad') is None else 'sin_stock_confirmado')
    if not _monto(total) or oferta.get('moneda') != 'MXN' or not _texto(oferta, 'contexto_costo'):
        motivos.append('total_no_comparable')
    if not _referencia_suficiente(oferta, referencia):
        motivos.append('historia_insuficiente')
    resultado = dict(estado='evidencia_insuficiente', motivos=motivos, ahorro_pct=None,
                     edad_minutos=round(edad, 1) if edad is not None else None,
                     costo_total_confirmado=total if _monto(total) else None,
                     vigente_hasta_utc=vigencia.isoformat().replace('+00:00', 'Z') if vigencia else None,
                     regla=VERSION, referencia=None)
    if motivos:
        return resultado
    ahorro = 100 * (1 - total / referencia['mediana'])
    resultado.update(estado='sin_senal_clara', ahorro_pct=round(ahorro, 10),
                     referencia={clave: referencia.get(clave) for clave in (
                         'mediana', 'p25', 'p75', 'inicio', 'fin', 'n_dias', 'amplitud_dias')})
    if resultado['ahorro_pct'] >= UMBRAL_PCT and total <= referencia['p25']:
        resultado['estado'] = 'precio_favorable'
    elif resultado['ahorro_pct'] <= -UMBRAL_PCT and total >= referencia['p75']:
        resultado['estado'] = 'precio_alto'
    return resultado
