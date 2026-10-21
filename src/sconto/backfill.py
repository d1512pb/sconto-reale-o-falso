"""Plan y ejecución acotada de fuentes históricas; ninguna API actual reconstruye días inexistentes."""
from __future__ import annotations

import argparse
import importlib
import json

import pandas as pd

from sconto.almacen import ahora_utc, hoy
from sconto.rutas import BRONZE, CONFIG, RAW, REPORTS, asegurar_directorios

FUENTES = ('qqp', 'preciometro', 'wayback', 'commoncrawl')


def ejecutar(fuentes, anios, max_productos=5, sin_red=False, limite_minutos=2, actualizar_qqp=False):
    productos = pd.read_csv(CONFIG / 'productos_objetivo.csv', dtype=str, keep_default_na=False)
    productos = productos.loc[productos.confianza_match.eq('exacto')].head(max_productos)
    resumen = {'inicio_utc': ahora_utc(), 'sin_red': sin_red, 'fuentes': {}}
    for fuente in fuentes:
        try:
            modulo = importlib.import_module(f'sconto.fuentes.{fuente}' if fuente != 'preciometro'
                                             else 'sconto.fuentes.preciometro_lote')
            if fuente == 'qqp':
                resultados = []
                if actualizar_qqp and not sin_red:
                    resultados.append({'revision_archivo_actual': modulo.diario(entorno='local')})
                for anio in anios:
                    tabla = BRONZE / 'qqp_cdmx' / f'{anio}.parquet'
                    if tabla.exists():
                        resultados.append({'anio': anio, 'estado': 'reutilizado',
                                           'filas': len(pd.read_parquet(tabla))})
                    elif sin_red:
                        resultados.append({'anio': anio, 'estado': 'sin_bronze',
                                           'accion': 'Ejecutar sconto.fuentes.qqp extraer --anios ' + str(anio)})
                    else:
                        resultados.append(modulo.backfill([anio], nacional=False))
                resumen['fuentes'][fuente] = resultados
            elif fuente == 'preciometro':
                lista = pd.read_csv(CONFIG / 'preciometro_lista.csv', dtype=str)
                fecha = hoy()
                if sin_red:
                    carpetas = sorted(carpeta for carpeta in (RAW / fuente).glob('*') if carpeta.is_dir())
                    if not carpetas:
                        resumen['fuentes'][fuente] = {'estado': 'sin_cache', 'filas': 0}
                        continue
                    fecha = carpetas[-1].name
                    lista = lista.loc[lista.preciometro_id.map(lambda identificador:
                                      (RAW / fuente / fecha / f'{identificador}.json.gz').exists())]
                resumen['fuentes'][fuente] = modulo.correr(lista.head(max_productos).url.tolist(), fecha=fecha)
            elif sin_red:
                tablas = sorted((BRONZE / fuente).glob('*.parquet'))
                resumen['fuentes'][fuente] = {'estado': 'reutilizado' if tablas else 'sin_cache',
                                               'filas': sum(len(pd.read_parquet(tabla)) for tabla in tablas)}
            elif fuente == 'wayback':
                resumen['fuentes'][fuente] = modulo.backfill(
                    productos=productos, incluir_tiendas=False, solo_ventanas=True,
                    max_por_id=2, limite_minutos=limite_minutos)
            else:
                resumen['fuentes'][fuente] = modulo.backfill(
                    productos=productos, incluir_tiendas=False, max_crawls=2,
                    max_por_id=2, limite_minutos=limite_minutos)
        except Exception as error:
            resumen['fuentes'][fuente] = {'estado': 'fallo', 'motivo': f'{type(error).__name__}: {error}'}
    resumen['fin_utc'] = ahora_utc()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / 'ultima_ejecucion_backfill.json').write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return resumen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fuentes', nargs='+', choices=FUENTES, default=['qqp', 'preciometro'])
    parser.add_argument('--anios', nargs='+', type=int, default=[2024, 2025, 2026])
    parser.add_argument('--max-productos', type=int, default=5)
    parser.add_argument('--limite-minutos', type=float, default=2)
    parser.add_argument('--sin-red', action='store_true')
    parser.add_argument('--ejecutar', action='store_true', help='Sin esta opción sólo muestra el plan.')
    parser.add_argument('--actualizar-qqp', action='store_true', help='Con red: revisa nuevas versiones del archivo oficial del año actual.')
    argumentos = parser.parse_args(argv)
    if argumentos.max_productos < 1 or argumentos.limite_minutos <= 0:
        parser.error('Los límites deben ser positivos')
    if argumentos.actualizar_qqp and argumentos.sin_red:
        parser.error('--actualizar-qqp necesita red; no combinar con --sin-red')
    if any(anio < 2018 or anio > int(hoy()[:4]) for anio in argumentos.anios):
        parser.error('Los años deben estar entre 2018 y el año actual')
    plan = dict(fuentes=argumentos.fuentes, anios=argumentos.anios,
                max_productos=argumentos.max_productos, sin_red=argumentos.sin_red,
                actualizar_qqp=argumentos.actualizar_qqp,
                limite_minutos_por_archivo=argumentos.limite_minutos)
    if not argumentos.ejecutar:
        print(json.dumps({'plan': plan, 'nota': 'Añadir --ejecutar para correr; no se hizo ninguna petición.'}))
        return 0
    asegurar_directorios()
    resultado = ejecutar(**{clave: valor for clave, valor in plan.items() if clave != 'limite_minutos_por_archivo'},
                         limite_minutos=argumentos.limite_minutos)
    print(json.dumps(resultado, ensure_ascii=False, default=str))
    return int(any(isinstance(valor, dict) and valor.get('estado') == 'fallo'
                   for valor in resultado['fuentes'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
