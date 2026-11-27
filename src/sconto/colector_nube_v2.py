"""Programador persistente de las consultas oficiales y del respaldo privado de Sconto."""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
from threading import Event

import requests

from sconto.cliente import Bloqueado, Cliente, NoPermitido
from sconto.fuentes import profeco_buenfin, qqp_vigilar
from sconto.intraday import CDMX, IntradayStore
from sconto.operacion_profeco_bf_v2 import FIN, INICIO, _escribir, ejecutar, registrar_estado

ESQUEMA = '''
CREATE TABLE IF NOT EXISTS trabajos_nube (
    tarea TEXT NOT NULL,
    fecha_cdmx TEXT NOT NULL,
    intento INTEGER NOT NULL,
    inicio_utc TEXT NOT NULL,
    fin_utc TEXT,
    estado TEXT NOT NULL,
    siguiente_utc TEXT,
    resultado_json TEXT,
    PRIMARY KEY(tarea, fecha_cdmx, intento)
);
'''
ESTADOS_REINTENTABLES = {'interrumpido', 'fallo', 'parcial'}
QQP_INICIO = date(2026, 11, 22)
QQP_REFERENCIAS = {2026: {'bytes': 59971365,
                         'huella_inicio': '31a376c765e66d8d67e4c7542e424577685666e0d8446af30cbc5f5cf0fcef02'}}
BACKUP_ENV = ('SCONTO_BACKUP_BUCKET', 'SCONTO_BACKUP_ACCESS_KEY_ID', 'SCONTO_BACKUP_SECRET_ACCESS_KEY',
              'SCONTO_BACKUP_AGE_RECIPIENT')
RESERVA_VOLUMEN_QQP = 192 * 1024 * 1024


@dataclass(frozen=True)
class Tarea:
    nombre: str
    hora_cdmx: time
    intentos: int = 2
    pausa: timedelta = timedelta(minutes=15)


PROFECO = Tarea('profeco_buen_fin', time(17))
QQP = Tarea('qqp', time(12, 5))
RESPALDO = Tarea('respaldo_privado', time(20, 30))


def ahora_utc():
    return datetime.now(timezone.utc)


def _iso(ahora):
    if ahora.utcoffset() is None:
        raise ValueError('La fecha de operación debe incluir huso')
    return ahora.astimezone(timezone.utc).isoformat(timespec='microseconds')


class Programador:
    def __init__(self, store):
        self.store = store
        with store._conexion() as db:
            db.executescript(ESQUEMA)

    def recuperar_interrumpidos(self, ahora):
        # Se ejecuta sólo después de obtener el bloqueo exclusivo del programador.
        with self.store._conexion() as db:
            db.execute('''
                UPDATE trabajos_nube SET estado='interrumpido', fin_utc=?
                WHERE estado='ejecutando'
            ''', (_iso(ahora),))

    def tomar(self, tarea, ahora):
        local = ahora.astimezone(CDMX)
        if local.time() < tarea.hora_cdmx:
            return None
        slot = local.date().isoformat()
        with self.store._conexion() as db:
            db.execute('BEGIN IMMEDIATE')
            previa = db.execute('''
                SELECT intento, estado, siguiente_utc FROM trabajos_nube
                WHERE tarea=? AND fecha_cdmx=? ORDER BY intento DESC LIMIT 1
            ''', (tarea.nombre, slot)).fetchone()
            intento = 1
            if previa:
                intento = previa['intento'] + 1
                if (intento > tarea.intentos or previa['estado'] not in ESTADOS_REINTENTABLES
                        or (previa['siguiente_utc'] and previa['siguiente_utc'] > _iso(ahora))):
                    return None
            pausa = db.execute('''
                SELECT MAX(siguiente_utc) FROM trabajos_nube WHERE tarea=? AND estado='bloqueado'
            ''', (tarea.nombre,)).fetchone()[0]
            if pausa and pausa > _iso(ahora):
                return None
            db.execute('''
                INSERT INTO trabajos_nube(tarea,fecha_cdmx,intento,inicio_utc,estado) VALUES(?,?,?,?,'ejecutando')
            ''', (tarea.nombre, slot, intento, _iso(ahora)))
        return local.date(), intento

    def cerrar(self, tarea, dia, intento, fin, resultado):
        estado = resultado['estado']
        siguiente = resultado.get('siguiente_utc')
        if estado in ESTADOS_REINTENTABLES:
            siguiente = _iso(fin + tarea.pausa)
        if siguiente:
            siguiente = _iso(datetime.fromisoformat(siguiente))
        with self.store._conexion() as db:
            db.execute('''
                UPDATE trabajos_nube SET fin_utc=?, estado=?, siguiente_utc=?, resultado_json=?
                WHERE tarea=? AND fecha_cdmx=? AND intento=? AND estado='ejecutando'
            ''', (_iso(fin), estado, siguiente, json.dumps(resultado, ensure_ascii=False),
                  tarea.nombre, dia.isoformat(), intento))


def estado(raiz):
    archivo = raiz / 'intradia.sqlite3'
    if not archivo.is_file():
        return []
    with closing(sqlite3.connect(archivo.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trabajos_nube'").fetchone():
            return []
        return [dict(fila) for fila in db.execute('''
            SELECT tarea,fecha_cdmx,intento,inicio_utc,fin_utc,estado,siguiente_utc
              FROM trabajos_nube ORDER BY inicio_utc DESC LIMIT 100
        ''')]


def _operar_profeco(store, dia, *, sin_red=False):
    raiz = store.root / 'profeco'
    crudos = raiz / 'raw' / dia.isoformat()
    resultado = ejecutar(dia, crudos, raiz / 'exportaciones' / dia.isoformat(), store, sin_red)
    suspension = crudos / 'bf_suspension.json'
    if suspension.is_file():
        bloqueo = json.loads(suspension.read_bytes())
        # Aunque se restauren sólo los archivos, el marcador impide otra descarga ese día.
        resultado['estado'] = 'bloqueado'
        resultado['siguiente_utc'] = bloqueo.get('siguiente_utc')
    registrar_estado(raiz / 'operacion', dia, resultado, sin_red=sin_red)
    return resultado


def _operar_qqp(store, dia):
    raiz = store.root / 'qqp'
    salida = raiz / 'publicaciones'
    salida.mkdir(parents=True, exist_ok=True)
    conocido = raiz / 'anual' / f'QQP_{dia.year}.rar'
    cliente = Cliente(reintentos=0, timeout=(10, 40))
    try:
        observacion = qqp_vigilar.vigilar(cliente, dia.year, salida, conocido, ahora_utc(),
                                         referencia=QQP_REFERENCIAS.get(dia.year),
                                         reserva_bytes=RESERVA_VOLUMEN_QQP)
        resultado = {'estado': 'ok', 'revision': observacion['estado']}
    except (Bloqueado, NoPermitido) as error:
        observacion = {'estado': 'bloqueado', 'clase_error': type(error).__name__}
        resultado = {**observacion, 'siguiente_utc': profeco_buenfin.reintento_desde(error, ahora_utc())}
    except qqp_vigilar.EspacioInsuficiente:
        observacion = {'estado': 'sin_espacio_para_candidato'}
        resultado = {'estado': 'fallo', 'revision': observacion['estado']}
    except (requests.RequestException, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        observacion = {'estado': 'fallo_de_verificacion', 'clase_error': type(error).__name__}
        resultado = {'estado': 'fallo', 'error': type(error).__name__}
    finally:
        cliente.sesion.close()
    observacion['consultado_utc'] = _iso(ahora_utc())
    serializada = json.dumps(observacion, ensure_ascii=False, indent=2) + '\n'
    _escribir(salida / 'estado.json', serializada)
    _escribir(raiz / 'estado.json', serializada)
    return resultado


def _respaldar(store, _dia):
    if not all(os.getenv(var) for var in BACKUP_ENV):
        return {'estado': 'sin_configurar'}
    cmd = [sys.executable, '-m', 'sconto.respaldo_nube_v2', 'enviar', '--origen', str(store.root)]
    catalogo = os.getenv('SCONTO_API_CATALOGO')
    if catalogo and Path(catalogo).is_file():
        cmd.extend(['--catalogo', catalogo])
    proceso = subprocess.run(cmd, capture_output=True, timeout=1800, check=False)
    if proceso.returncode != 0:
        return {'estado': 'fallo', 'codigo': proceso.returncode}
    return {'estado': 'ok', 'objeto_verificado': True}


def _tareas(dia):
    if QQP_INICIO <= dia and dia.weekday() == 6:
        yield QQP, _operar_qqp
    if INICIO <= dia <= FIN:
        yield PROFECO, _operar_profeco
    yield RESPALDO, _respaldar


def paso(programador, reloj=ahora_utc):
    dia_actual = reloj().astimezone(CDMX).date()
    for tarea, operacion in _tareas(dia_actual):
        inicio = reloj()
        if inicio.astimezone(CDMX).date() != dia_actual:
            break
        tomada = programador.tomar(tarea, inicio)
        if not tomada:
            continue
        dia, intento = tomada
        print(json.dumps(dict(tarea=tarea.nombre, fecha_cdmx=dia.isoformat(), intento=intento,
                              estado='ejecutando')), flush=True)
        try:
            resultado = operacion(programador.store, dia)
        except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as error:
            resultado = {'estado': 'fallo', 'error': type(error).__name__}
        programador.cerrar(tarea, dia, intento, reloj(), resultado)
        print(json.dumps(dict(tarea=tarea.nombre, fecha_cdmx=dia.isoformat(), intento=intento, **resultado),
                         ensure_ascii=False), flush=True)


def reproducir(store, origen):
    origen = origen.resolve(strict=True)
    fechas = []
    for nombre in profeco_buenfin.CATALOGOS.values():
        metadata = json.loads((origen / f'{nombre}.json').read_bytes())
        fecha = datetime.fromisoformat(metadata['fetched_at_utc'])
        if fecha.utcoffset() is None:
            raise ValueError('Archivo de origen sin huso explícito')
        fechas.append(fecha.astimezone(CDMX).date())
    if len(set(fechas)) != 1:
        raise ValueError('Los catálogos corresponden a fechas distintas')
    dia = fechas[0]
    destino = store.root / 'profeco' / 'raw' / dia.isoformat()
    if destino != origen:
        if destino.exists():
            raise FileExistsError('La reproducción requiere un destino dedicado')
        destino.mkdir(parents=True)
        for archivo in origen.rglob('*'):
            oficial = re.fullmatch(r'bf_cdmx_(?:audio|computo|producto_\d+)(?:_[\w-]+)?\.(?:json|gz)', archivo.name)
            bitacora = archivo.name in {'bf_suspension.json', 'bf_fallos.jsonl'}
            if (oficial or bitacora) and archivo.is_file() and not archivo.is_symlink():
                copia = destino / archivo.relative_to(origen)
                copia.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(archivo, copia)
    resultado = _operar_profeco(store, dia, sin_red=True)
    print(json.dumps(resultado, ensure_ascii=False))
    return 0 if resultado['estado'] == 'ok' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', type=Path, default=Path(os.getenv('SCONTO_API_DATOS', '/data/intradia')))
    modos = parser.add_mutually_exclusive_group()
    modos.add_argument('--estado', action='store_true', help='Consultar la bitácora sin escribir en el almacén')
    modos.add_argument('--una-vez', action='store_true', help='Ejecutar las tareas vencidas de hoy y terminar')
    modos.add_argument('--reproducir', type=Path, help='Importar la pasada archivada a un almacén aislado sin red')
    args = parser.parse_args(argv)
    if args.estado:
        print(json.dumps(estado(args.raiz), ensure_ascii=False))
        return 0
    store = IntradayStore(args.raiz)
    with store.exclusividad_colector('programador-nube.lock') as disponible:
        if not disponible:
            parser.error('Ya existe un programador activo en este volumen')
        if args.reproducir:
            return reproducir(store, args.reproducir)
        programa = Programador(store)
        programa.recuperar_interrumpidos(ahora_utc())
        terminado = Event()
        for signo in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signo, lambda *_: terminado.set())
        while not terminado.is_set():
            paso(programa)
            if args.una_vez:
                break
            terminado.wait(30)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
