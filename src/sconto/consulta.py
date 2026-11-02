"""Comparación descriptiva de una consulta; nunca etiqueta fraude ni predice precios futuros."""
from __future__ import annotations

import math


def _positivo(valor, nombre):
    valor = float(valor)
    if not math.isfinite(valor) or valor <= 0:
        raise ValueError(f'{nombre} debe ser finito y mayor que cero')
    return valor


def evaluar_oferta(referencia, precio, precio_tachado=None, pct_anunciado=None, serie_oferta_id=None,
                   moneda='MXN', canal='en_linea'):
    precio = _positivo(precio, 'precio')
    if precio_tachado is not None:
        precio_tachado = _positivo(precio_tachado, 'precio tachado')
    if pct_anunciado is not None:
        pct_anunciado = float(pct_anunciado)
        if not math.isfinite(pct_anunciado) or not -100 <= pct_anunciado <= 100:
            raise ValueError('El porcentaje anunciado debe estar entre -100 y 100')
    resultado = dict(estado='evidencia_insuficiente', precio_consultado=precio,
                     descuento_implicito_tachado_pct=100 * (1 - precio / precio_tachado) if precio_tachado else None,
                     pct_anunciado_textual=pct_anunciado, diferencia_frente_referencia_pct=None,
                     brecha_consulta_pp=None, anuncio_comparable=False, es_veredicto_fraude=False,
                     advertencia='No se verifican disponibilidad, envío, membresías ni autenticidad de la oferta.')
    if not referencia:
        resultado['mensaje'] = 'No hay una referencia histórica identificada para esta consulta.'
        return resultado
    if referencia.get('moneda') != moneda or referencia.get('canal') != canal:
        resultado['mensaje'] = 'Moneda o canal incompatibles. No se mezclan tiendas físicas y precios en línea.'
        return resultado
    if not referencia.get('cobertura_base') or not referencia.get('base_cerrada'):
        resultado['mensaje'] = 'La base requiere al menos cuatro fechas en 21 días y una ventana ya cerrada.'
        return resultado
    mediana = _positivo(referencia['mediana_base'], 'mediana histórica')
    resultado['diferencia_frente_referencia_pct'] = 100 * (1 - precio / mediana)
    minimo, maximo = referencia.get('p25_base'), referencia.get('p75_base')
    if minimo is None or maximo is None or not math.isfinite(float(minimo)) or not math.isfinite(float(maximo)):
        resultado['mensaje'] = 'Falta el rango central observado.'
        return resultado
    resultado['estado'] = 'debajo_del_rango' if precio < minimo else 'encima_del_rango' if precio > maximo else 'dentro_del_rango'
    mercado = referencia.get('contexto') == 'minimo_multitienda'
    resultado['tipo_referencia'] = 'mercado_multitienda' if mercado else 'serie_vendedor'
    if mercado:
        resultado['mensaje'] = 'Comparación con mínimos multitienda; NO representa el ahorro histórico de ese vendedor.'
    else:
        resultado['mensaje'] = 'Comparación descriptiva con la serie seleccionada; comprobar modelo, vendedor y condiciones.'
        comparable = serie_oferta_id is not None and serie_oferta_id == referencia.get('serie_id')
        resultado['anuncio_comparable'] = comparable
        if comparable and pct_anunciado is not None:
            resultado['brecha_consulta_pp'] = pct_anunciado - resultado['diferencia_frente_referencia_pct']
    resultado['nota_rango'] = 'P25–P75 de precios diarios observados; no es un intervalo de confianza.'
    resultado['nota_brecha'] = 'La brecha de una consulta no sustituye la mediana del evento ni demuestra engaño.'
    return resultado
