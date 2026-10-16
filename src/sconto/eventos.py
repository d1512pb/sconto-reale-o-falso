"""Eventos Buen Fin y ventanas relativas a D0, iguales a las del Avance 1."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import yaml

from sconto.rutas import CONFIG


def cargar_eventos() -> pd.DataFrame:
    cfg = yaml.safe_load((CONFIG / 'eventos.yaml').read_text(encoding='utf-8'))
    v = cfg['ventanas_relativas']
    filas = []
    for e in cfg['eventos']:
        d0, fin = pd.Timestamp(e['inicio']), pd.Timestamp(e['fin'])
        filas.append(dict(
            evento_id=e['evento_id'], nombre=e['nombre'], d0=d0, fin=fin,
            base_inicio=d0 + timedelta(days=v['base'][0]), base_fin=d0 + timedelta(days=v['base'][1]),
            previo_inicio=d0 + timedelta(days=v['previo'][0]), previo_fin=d0 + timedelta(days=v['previo'][1]),
            evento_inicio=d0, evento_fin=fin,
            posterior_inicio=fin + timedelta(days=1), posterior_fin=fin + timedelta(days=v['posterior_dias']),
            fuente_fechas=e.get('fuente_fechas', '')))
    return pd.DataFrame(filas)


def ventana_de(fecha, ev: pd.Series) -> str | None:
    fecha = pd.Timestamp(fecha)
    for nombre in ('base', 'previo', 'evento', 'posterior'):
        if ev[f'{nombre}_inicio'] <= fecha <= ev[f'{nombre}_fin']:
            return nombre
    return None


def en_temporada_doble(d: date | None = None) -> bool:
    """Dos pasadas diarias solo del 10 al 20 de noviembre."""
    d = d or date.today()
    return d.month == 11 and 10 <= d.day <= 20
