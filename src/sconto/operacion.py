"""Ciclo programado: captura, preparación, reporte, paquete y verificación de salud."""
from __future__ import annotations

import argparse
import json
import logging
import os

import pandas as pd
from dotenv import load_dotenv

from sconto.almacen import _Candado, ahora_utc, combinar_estados, hoy
from sconto.rutas import DATA, ESTADO_FUENTES, LOGS, asegurar_directorios


def salud(entorno, fecha=None):
    fecha = fecha or hoy()
    combinar_estados()
    estados = pd.read_csv(ESTADO_FUENTES, dtype=str) if ESTADO_FUENTES.exists() else pd.DataFrame()
    requeridas = ['preciometro'] if entorno == 'github' else ['preciometro', 'tiendas']
    faltantes = []
    for fuente in requeridas:
        filas = estados.loc[estados.fuente.eq(fuente) & estados.fecha.eq(fecha)] if len(estados) else estados
        if filas.empty or not filas.estado.eq('ok').any():
            faltantes.append(fuente)
    return dict(fecha=fecha, entorno=entorno, ok=not faltantes, fuentes_sin_cobertura_completa=faltantes)


def preparar(entorno):
    from sconto.dataset import construir
    from sconto.diccionario import generar as generar_diccionario
    from sconto.exportar import empaquetar
    from sconto.evidencia import preservar
    from sconto.reportes import generar as generar_reportes

    preservar()
    manifiesto = construir()
    generar_diccionario()
    generar_reportes()
    paquete = empaquetar()
    resultado = dict(fecha=hoy(), entorno=entorno, construido_utc=ahora_utc(),
                     filas=manifiesto['tablas']['observaciones']['filas'],
                     paquete=paquete.relative_to(DATA).as_posix(), fuentes=manifiesto['fuentes'],
                     salud=salud(entorno))
    ruta = DATA / 'estado' / f'ciclo_{entorno}.json'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    return resultado


def ejecutar(entorno='local', solo_preparar=False, respaldo=False, max_productos=None, qqp_semanal=False):
    asegurar_directorios()
    if os.environ.get('SCONTO_ENVFILE'):
        load_dotenv(os.environ['SCONTO_ENVFILE'])
    with _Candado(DATA / 'ciclo', espera_max=0):
        if not solo_preparar:
            from sconto.run_diario import main as recolectar
            argumentos = ['--entorno', entorno]
            if max_productos:
                argumentos += ['--max-productos', str(max_productos)]
            recolectar(argumentos)
            if respaldo:
                recolectar(argumentos + ['--solo-si-falta', '--fuentes', 'preciometro', 'mercadolibre'])
            if qqp_semanal:
                revisar_qqp(entorno)
        return preparar(entorno)


def revisar_qqp(entorno):
    from sconto.fuentes.qqp import diario
    marca = DATA / 'cache' / 'revision_qqp.json'
    previo = json.loads(marca.read_text(encoding='utf-8')) if marca.exists() else {}
    revision_ok = previo and not previo.get('resultado', {}).get('fallos') and not previo.get('resultado', {}).get('bloqueado')
    if revision_ok and (pd.Timestamp(hoy()) - pd.Timestamp(previo['fecha'])).days < 7:
        return
    resultado = diario(entorno=entorno)
    marca.parent.mkdir(parents=True, exist_ok=True)
    marca.write_text(json.dumps({'fecha': hoy(), 'resultado': resultado}, ensure_ascii=False), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entorno', choices=['local', 'github'], default='local')
    parser.add_argument('--solo-preparar', action='store_true')
    parser.add_argument('--respaldo', action='store_true')
    parser.add_argument('--qqp-semanal', action='store_true')
    parser.add_argument('--max-productos', type=int)
    parser.add_argument('--verificar', action='store_true')
    argumentos = parser.parse_args(argv)
    if argumentos.max_productos is not None and argumentos.max_productos < 1:
        parser.error('--max-productos debe ser positivo')
    if argumentos.verificar:
        resultado = salud(argumentos.entorno)
        print(json.dumps(resultado, ensure_ascii=False))
        return 0 if resultado['ok'] else 2
    asegurar_directorios()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(
                            LOGS / f'operacion_{hoy()}_{argumentos.entorno}.log', encoding='utf-8')])
    resultado = ejecutar(argumentos.entorno, argumentos.solo_preparar, argumentos.respaldo,
                         argumentos.max_productos, argumentos.qqp_semanal)
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
