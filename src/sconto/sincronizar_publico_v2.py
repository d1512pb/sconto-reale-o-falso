"""Sincroniza observaciones publicables por el comando autenticado de Fly Machines."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from itertools import islice
import json
from math import isfinite
import os
from pathlib import Path
import re
import sqlite3
import sys
from time import sleep
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sconto.consulta_v2 import _enlace_publicable
from sconto.decisiones_v2 import normalizar_gtin
from sconto.intraday import CDMX, RAIZ_INTRADIA, VERSION_COTIZACION, IntradayStore, Oferta, Trabajo, _id, _utc


FUENTE = 'tienda_manual'
CONTEXTOS_COSTO = frozenset({'envio_cdmx', 'envio_estado_de_mexico', 'retiro_sucursal', 'entrega_digital'})
COMANDO_FLY = '/usr/sbin/runuser -u sconto -- /usr/local/bin/python -m sconto.sincronizar_publico_v2 recibir'
ESQUEMA = 'sconto-publico-v2.1'
MAX_FILAS = 16
MAX_BYTES = 32_768
MAX_POR_PASO = 256
MAX_PRECIO = 10_000_000
ESTADOS = {'disponible', 'agotado', 'desconocido'}
CONDICIONES = {'nuevo', 'reacondicionado', 'usado', 'desconocido'}
CAMPOS = frozenset({
    'capture_id', 'intento', 'inicio_utc', 'fin_utc', 'anuncio_id', 'producto_id', 'variante',
    'plataforma', 'vendedor', 'condicion', 'enlace', 'observed_at', 'source_updated_at',
    'precio', 'precio_tachado', 'disponibilidad', 'condiciones',
})


def _json(objeto):
    return json.dumps(objeto, ensure_ascii=True, allow_nan=False, separators=(',', ':'), sort_keys=True)


def _monto(importe):
    return type(importe) in (int, float) and 0 < importe <= MAX_PRECIO and isfinite(importe)


def condiciones_publicas(valores):
    """Mantiene sólo datos autorizados para consulta y los estados explícitamente conocidos."""
    cargo = valores.get('costo_total_confirmado')
    contexto = valores.get('contexto_costo')
    resultado = {k: valores.get(k) is True for k in ('publicable', 'identidad_verificada', 'cargos_confirmados')}
    if contexto in CONTEXTOS_COSTO:
        resultado['contexto_costo'] = contexto
    if resultado['cargos_confirmados'] and _monto(cargo):
        resultado['costo_total_confirmado'] = cargo
    if gtin := normalizar_gtin(valores.get('gtin')):
        resultado['gtin'] = gtin
    promocion = valores.get('promocion_condicionada')
    if type(promocion) is bool or isinstance(promocion, str) and promocion.strip():
        resultado['promocion_condicionada'] = bool(promocion)
    return resultado


def _texto(texto, limite, opcional=False):
    return (texto is None and opcional) or (isinstance(texto, str) and 0 < len(texto) <= limite
            and texto == ' '.join(texto.split()) and texto.isprintable())


def _hora(valor):
    if not isinstance(valor, str):
        raise ValueError('La hora debe incluir zona')
    fecha = datetime.fromisoformat(valor)
    if valor != _utc(fecha):
        raise ValueError('La hora debe ser UTC canónica')
    return fecha


def _validar(fila, ahora):
    if not isinstance(fila, dict) or fila.keys() != CAMPOS:
        raise ValueError('Campos inesperados en la cotización')
    if not (_texto(fila['producto_id'], 80) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', fila['producto_id'])
            and _texto(fila['anuncio_id'], 90) and _texto(fila['variante'], 120, opcional=True)
            and _texto(fila['vendedor'], 120, opcional=True) and fila['condicion'] in CONDICIONES
            and fila['disponibilidad'] in ESTADOS and _texto(fila['enlace'], 500)
            and _enlace_publicable(fila['enlace']) and _monto(fila['precio'])
            and (fila['precio_tachado'] is None or _monto(fila['precio_tachado']))
            and type(fila['intento']) is int and fila['intento'] in (1, 2)):
        raise ValueError('Identidad, enlace, precio o estado inválido')

    liga = urlsplit(fila['enlace'])
    tienda = 'sears' if liga.netloc in ('www.sears.com.mx', 'sears.com.mx') else 'liverpool'
    plataforma = {'sears': 'Sears', 'liverpool': 'Liverpool'}[tienda]
    if (not re.fullmatch(tienda + r':[A-Za-z0-9][A-Za-z0-9_.+-]{0,79}', fila['anuncio_id'])
            or fila['plataforma'] != plataforma
            or not liga.path.startswith('/producto/' if tienda == 'sears' else '/tienda/pdp/')
            or (liga.query and (tienda != 'liverpool' or liga.query != 'skuid=' + fila['anuncio_id'].split(':')[1]))):
        raise ValueError('El anuncio y su enlace no coinciden')

    condiciones = fila['condiciones']
    if (not isinstance(condiciones, dict) or condiciones.get('publicable') is not True
            or condiciones != condiciones_publicas(condiciones)
            or any(type(condiciones.get(k)) is not bool
                   for k in ('publicable', 'identidad_verificada', 'cargos_confirmados'))
            or ('promocion_condicionada' in condiciones and type(condiciones['promocion_condicionada']) is not bool)):
        raise ValueError('Permiso insuficiente o dato privado en la cotización')
    if condiciones['identidad_verificada'] and (
            not fila['variante'] or not fila['vendedor'] or fila['condicion'] == 'desconocido'):
        raise ValueError('Falta identidad verificable')
    if condiciones['cargos_confirmados'] and (
            not _monto(condiciones.get('costo_total_confirmado'))
            or condiciones['costo_total_confirmado'] < fila['precio'] or not condiciones.get('contexto_costo')):
        raise ValueError('Falta costo total conciliado')

    momento = _hora(fila['observed_at'])
    inicio, fin = _hora(fila['inicio_utc']), _hora(fila['fin_utc'])
    actualizado = fila['source_updated_at']
    if (not momento <= inicio <= fin <= ahora or (actualizado is not None and _hora(actualizado) > momento)):
        raise ValueError('Fechas fuera del orden de observación y captura')
    trabajo_id = Trabajo(FUENTE, fila['enlace'], momento, max_intentos=2).trabajo_id
    if fila['capture_id'] != _id(trabajo_id, str(fila['intento'])):
        raise ValueError('La identidad de captura difiere de la evidencia')
    oferta = Oferta(fila['anuncio_id'], fila['producto_id'], plataforma, fila['enlace'],
                    fila['variante'], fila['vendedor'], fila['condicion'])
    return trabajo_id, oferta.identificador(FUENTE), momento.astimezone(CDMX).date().isoformat()


def lote(filas):
    filas = list(filas)
    cuerpo = _json(dict(esquema=ESQUEMA, sha256=sha256(_json(filas).encode()).hexdigest(), filas=filas))
    if not 1 <= len(filas) <= MAX_FILAS or len(cuerpo) > MAX_BYTES:
        raise ValueError('Tamaño de lote público inválido')
    return cuerpo


def recibir(store, cuerpo, ahora=None):
    """Valida el lote entero y escribe sus observaciones en una única transacción."""
    ahora = ahora or datetime.now(timezone.utc)
    if len(cuerpo.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Lote público demasiado grande')
    datos = json.loads(cuerpo)
    if not isinstance(datos, dict) or set(datos) != {'esquema', 'sha256', 'filas'} or datos['esquema'] != ESQUEMA:
        raise ValueError('Esquema de lote público inválido')
    filas = datos['filas']
    if (not isinstance(filas, list) or not 1 <= len(filas) <= MAX_FILAS
            or sha256(_json(filas).encode()).hexdigest() != datos['sha256']):
        raise ValueError('La huella o el tamaño del lote no coincide')
    llaves = [_validar(fila, ahora) for fila in filas]
    if len(filas) != len({f['capture_id'] for f in filas}):
        raise ValueError('El lote repite un identificador de captura')

    inserciones = 0
    with store._conexion() as db:
        db.execute('BEGIN IMMEDIATE')
        for fila, (trabajo_id, offer_id, fecha) in zip(filas, llaves, strict=True):
            captura_id = fila['capture_id']
            cotizacion = (captura_id, offer_id, fila['observed_at'], fila['source_updated_at'], 'instante',
                          None, fecha, fila['precio'], 'MXN', fila['precio_tachado'], fila['disponibilidad'],
                          json.dumps(fila['condiciones'], ensure_ascii=False, allow_nan=False, sort_keys=True),
                          fila['enlace'])
            previo = db.execute('SELECT * FROM observaciones_intradia WHERE capture_id=?', (captura_id,)).fetchall()
            if previo:
                if [tuple(f) for f in previo] != [cotizacion]:
                    raise ValueError('Una captura existente difiere de la entrega pública')
                continue
            db.execute('INSERT OR IGNORE INTO trabajos VALUES (?,?,?,?,?)',
                       (trabajo_id, FUENTE, fila['enlace'], fila['observed_at'], 2))
            db.execute('INSERT INTO intentos VALUES (?,?,?,?,?,NULL,NULL)',
                       (captura_id, trabajo_id, fila['intento'], fila['inicio_utc'], fila['fin_utc']))
            db.execute('INSERT INTO capturas VALUES (?,?,?,?,NULL,\'ok\',NULL,NULL,?)',
                       (captura_id, FUENTE, fila['enlace'], fila['observed_at'], VERSION_COTIZACION))
            db.execute('INSERT OR IGNORE INTO ofertas VALUES (?,?,?,?,?,?,?,?,?)',
                       (offer_id, FUENTE, fila['anuncio_id'], fila['producto_id'], fila['variante'],
                        fila['plataforma'], fila['vendedor'], fila['condicion'], fila['enlace']))
            db.execute('INSERT INTO observaciones_intradia VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', cotizacion)
            inserciones += 1
    return dict(sha256=datos['sha256'], recibidas=len(filas), nuevas=inserciones)


def _publicables(store):
    with store._conexion() as db:
        return [dict(f, condiciones=condiciones_publicas(json.loads(f['condiciones']))) for f in db.execute('''
            SELECT n.capture_id,i.intento,i.inicio_utc,i.fin_utc,o.anuncio_id,o.producto_id,o.variante,
                   o.plataforma,o.vendedor,o.condicion,n.enlace,n.observed_at,n.source_updated_at,
                   n.precio,n.precio_tachado,n.disponibilidad,n.condiciones_json AS condiciones
            FROM observaciones_intradia n JOIN ofertas o USING(offer_id)
            JOIN capturas c USING(capture_id) JOIN intentos i USING(capture_id)
            WHERE o.fuente=? AND c.fuente=? AND c.resultado='ok' AND c.version_colector=?
              AND n.precision_temporal='instante' AND n.moneda='MXN'
              AND json_type(n.condiciones_json,'$.publicable')='true'
            ORDER BY n.observed_at, n.capture_id
        ''', (FUENTE, FUENTE, VERSION_COTIZACION))]


class _SinRedireccion(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _enviar_fly(app, maquina, cuerpo):
    credencial = os.environ.get('SCONTO_SYNC_FLY_TOKEN', '')
    if not re.fullmatch(r'FlyV1 [!-~]+', credencial):
        raise RuntimeError('Falta una credencial FlyV1 de sincronización en el entorno local')
    url = f'https://api.machines.dev/v1/apps/{app}/machines/{maquina}/exec'
    datos = _json(dict(cmd=COMANDO_FLY, stdin=cuerpo, timeout=30)).encode()
    solicitud = Request(url, data=datos, headers={'Authorization': credencial, 'Content-Type': 'application/json'},
                        method='POST')
    try:
        with build_opener(_SinRedireccion()).open(solicitud, timeout=40) as respuesta:
            resultado = json.loads(respuesta.read(8192))
        if resultado.get('exit_code', 0) != 0 or resultado.get('exit_signal'):
            raise ValueError('El receptor no confirmó la transacción')
        return json.loads(resultado['stdout'])
    except (URLError, ValueError, KeyError, AttributeError, TimeoutError) as error:
        raise RuntimeError('Fly Machines no confirmó el lote. Sigue pendiente de reintento') from error


def enviar(store, app, maquina, *, reconciliar=False, transporte=_enviar_fly):
    if not (re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', app)
            and re.fullmatch(r'[a-f0-9]{8,32}', maquina)):
        raise ValueError('Identificador Fly de aplicación o máquina inválido')
    destino = f'{app}/{maquina}'
    filas = _publicables(store)
    estado = store.root / 'sincronizacion_publica.sqlite3'
    resumen = dict(confirmadas=0, nuevas=0, por_enviar=0)
    with closing(sqlite3.connect(estado, timeout=15)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS confirmadas (
            destino TEXT, captura TEXT, sha256 TEXT, PRIMARY KEY(destino,captura,sha256))''')
        if reconciliar:
            db.execute('DELETE FROM confirmadas WHERE destino=?', (destino,))
    with closing(sqlite3.connect(estado, timeout=15)) as db:
        registradas = set(db.execute('SELECT captura,sha256 FROM confirmadas WHERE destino=?', (destino,)))
        pendientes = [(f, sha256(_json(f).encode()).hexdigest()) for f in filas]
        pendientes = [(f, huella) for f, huella in pendientes if (f['capture_id'], huella) not in registradas]
        seleccion = iter(pendientes[:MAX_POR_PASO])
        while grupo := list(islice(seleccion, MAX_FILAS)):
            for fila, _ in grupo:
                _validar(fila, datetime.now(timezone.utc))
            cuerpo = lote(f for f, _ in grupo)
            recibo = transporte(app, maquina, cuerpo)
            if (not isinstance(recibo, dict) or recibo.get('sha256') != json.loads(cuerpo)['sha256']
                    or recibo.get('recibidas') != len(grupo) or type(recibo.get('nuevas')) is not int
                    or not 0 <= recibo['nuevas'] <= len(grupo)):
                raise RuntimeError('El acuse no corresponde al lote enviado')
            with db:
                db.executemany('INSERT OR IGNORE INTO confirmadas VALUES (?,?,?)',
                               ((destino, f['capture_id'], huella) for f, huella in grupo))
            resumen['confirmadas'] += len(grupo)
            resumen['nuevas'] += recibo['nuevas']
            if resumen['confirmadas'] < min(len(pendientes), MAX_POR_PASO):
                sleep(1)
    resumen['por_enviar'] = len(pendientes) - resumen['confirmadas']
    return resumen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--almacen', type=Path, default=Path(os.getenv('SCONTO_API_DATOS', RAIZ_INTRADIA)))
    acciones = parser.add_subparsers(dest='accion', required=True)
    acciones.add_parser('recibir')
    remitente = acciones.add_parser('enviar')
    remitente.add_argument('--app', required=True)
    remitente.add_argument('--maquina', required=True)
    remitente.add_argument('--reconciliar', action='store_true')
    args = parser.parse_args()
    store = IntradayStore(args.almacen)
    try:
        if args.accion == 'recibir':
            resultado = recibir(store, sys.stdin.buffer.read(MAX_BYTES + 1).decode('utf-8'))
        else:
            resultado = enviar(store, args.app, args.maquina, reconciliar=args.reconciliar)
    except (ValueError, RuntimeError, TypeError, sqlite3.Error, OverflowError) as error:
        # El cuerpo y la credencial no van a la salida ni a la bitácora de Windows.
        print(_json(dict(estado='rechazado', motivo=type(error).__name__)), file=sys.stderr)
        return 2
    print(_json(resultado))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
