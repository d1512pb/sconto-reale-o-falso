"""Opera el piloto diario oficial y escribe avisos locales de cobertura y ejecución."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sconto.fuentes import profeco_buenfin as fuente
from sconto.importar_profeco_bf_v2 import importar
from sconto.intraday import CDMX, RAIZ_INTRADIA, IntradayStore
from sconto.rutas import DATA


INICIO = date(2026, 11, 15)
FIN = date(2026, 12, 1)
ESPERADOS = sum(map(len, fuente.MUESTRA.values()))
OPERACION = DATA / 'operacion' / 'v2' / 'profeco_campana'


def _escribir(ruta, texto):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + '.tmp')
    temporal.write_text(texto, encoding='utf-8')
    temporal.replace(ruta)


def _ultimo_estado(ruta, dia):
    intentos = sorted(ruta.glob(f'{dia.isoformat()}T*.json'))
    return json.loads(intentos[-1].read_bytes()) if intentos else None


def evaluar(ejecuciones, hoy, estado=None):
    faltantes, parciales = [], []
    dia = INICIO
    while dia < min(hoy, FIN + timedelta(days=1)):
        previo = _ultimo_estado(ejecuciones, dia)
        if previo is None:
            faltantes.append(dia.isoformat())
        elif previo['estado'] != 'ok':
            parciales.append(dia.isoformat())
        dia += timedelta(days=1)
    mensajes = []
    if faltantes:
        mensajes.append('Días sin ejecución registrada: ' + ', '.join(faltantes))
    if parciales:
        mensajes.append('Días con ejecución incompleta: ' + ', '.join(parciales))
    if estado and estado['estado'] != 'ok':
        mensajes.append(f"{estado['fecha_cdmx']}: {estado['estado']} ({estado['modelos']}/{ESPERADOS} fichas).")
    ultimo_precio = estado['ultimo_dia_precio'] if estado else None
    if ultimo_precio and (hoy - date.fromisoformat(ultimo_precio)).days >= 3:
        mensajes.append('La última fecha de levantamiento publicada es ' + ultimo_precio + '.')
    return mensajes


def ejecutar(dia, crudos, salida, store, sin_red=False):
    anteriores = sorted(f for f in fuente.CATALOGOS.values() if (crudos / (f + '.json')).exists())
    datos = dict(fecha_cdmx=dia.isoformat(), estado='fallo', modelos=0, observaciones=0,
                 exclusiones=0, ultimo_dia_precio=None, error=None)
    if not sin_red:
        try:
            fuente.capturar(crudos)
        except (fuente.Bloqueado, fuente.NoPermitido) as error:
            datos.update(estado='bloqueado', error=type(error).__name__)
        except (OSError, RuntimeError, ValueError) as error:
            datos['error'] = type(error).__name__
    presentes = [f for f in fuente.CATALOGOS.values() if (crudos / (f + '.json')).exists()]
    if len(presentes) != len(fuente.CATALOGOS):
        datos['error'] = datos['error'] or 'Falta un catálogo de la consulta oficial'
        return datos
    with store.exclusividad_colector() as permiso:
        if not permiso:
            datos['error'] = 'Otro proceso está importando precios'
            return datos
        try:
            store.vencidos()
            ingesta = importar(crudos, store)
            filas, faltantes = fuente.observaciones(crudos)
            limpias, descartadas = fuente.consolidar_observaciones(filas)
            salida.mkdir(parents=True, exist_ok=True)
            fuente._escribir_csv(salida / 'profeco_bf2026_observaciones.csv', limpias, fuente.CAMPOS)
            fuente._escribir_csv(salida / 'profeco_bf2026_exclusiones.csv', descartadas, fuente.CAMPOS + ('motivo',))
        except (OSError, ValueError, KeyError) as error:
            datos['error'] = datos['error'] or type(error).__name__
            return datos
    datos.update(modelos=ESPERADOS - len(faltantes), observaciones=len(limpias), exclusiones=len(descartadas),
                 ultimo_dia_precio=max((f['fecha_precio'] for f in limpias), default=None),
                 importadas=ingesta['importadas'], rechazadas=len(ingesta['rechazadas']),
                 catalogos_reutilizados=len(anteriores))
    if datos['estado'] != 'bloqueado':
        datos['estado'] = 'ok' if (not faltantes and not ingesta['rechazadas'] and limpias and not datos['error']) else 'parcial'
    return datos


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crudos', type=Path, default=fuente.RAW / 'campana')
    parser.add_argument('--salida', type=Path, default=fuente.OUT / 'campana')
    parser.add_argument('--operacion', type=Path, default=OPERACION)
    parser.add_argument('--almacen', type=Path, default=RAIZ_INTRADIA)
    parser.add_argument('--sin-red', action='store_true', help='Conciliar crudos ya archivados, sin nuevas consultas')
    parser.add_argument('--revisar', action='store_true', help='Actualizar el aviso únicamente, incluso si la campaña cerró')
    args = parser.parse_args(argv)
    hoy = datetime.now(CDMX).date()
    if not INICIO <= hoy <= FIN and not args.revisar:
        print(f'Campaña oficial fuera del intervalo {INICIO}–{FIN}.')
        return 0
    estado = None
    carpeta = args.operacion / 'ejecuciones'
    if args.revisar:
        estado = _ultimo_estado(carpeta, min(hoy, FIN))
    else:
        estado = ejecutar(hoy, args.crudos / hoy.isoformat(), args.salida / hoy.isoformat(),
                          IntradayStore(args.almacen), args.sin_red)
        estado['reportado_utc'] = datetime.now(timezone.utc).isoformat()
        estado['modo'] = 'reproduccion' if args.sin_red else 'consulta'
        etiqueta = datetime.now(CDMX).strftime('%Y-%m-%dT%H%M%S%f')
        _escribir(carpeta / f'{etiqueta}.json', json.dumps(estado, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(estado, ensure_ascii=False))
    avisos = evaluar(carpeta, hoy, estado)
    _escribir(args.operacion / 'ALERTA.md', '# Continuidad PROFECO Buen Fin\n\n' + '\n'.join(
        '- ' + a for a in avisos or ['Sin alertas de recolección al momento de esta revisión.']) + '\n')
    return 2 if avisos else 0


if __name__ == '__main__':
    raise SystemExit(main())
