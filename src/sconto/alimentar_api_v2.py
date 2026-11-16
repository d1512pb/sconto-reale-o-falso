"""Importa cotizaciones autorizadas desde un buzón privado y proyecta la base pública."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory

from sconto.importar_tienda_manual_v2 import FUENTE, importar
from sconto.intraday import RAIZ_INTRADIA, IntradayStore
from sconto.sincronizar_publico_v2 import condiciones_publicas


FOLIO = re.compile(r'[A-Za-z0-9_-]{1,80}')
ESQUEMA_COLA = '''
CREATE TABLE IF NOT EXISTS bandeja (
    folio TEXT NOT NULL, sha_entrada TEXT NOT NULL, ultima_ejecucion_utc TEXT NOT NULL,
    estado TEXT NOT NULL, motivo TEXT, capture_id TEXT,
    PRIMARY KEY(folio, sha_entrada)
);
'''


def _soporte(entrada, folio):
    candidatos = [entrada / (folio + extension) for extension in ('.pdf', '.txt', '.png', '.jpg')]
    existentes = [p for p in candidatos if p.is_file()]
    if len(existentes) > 1:
        raise ValueError('La cotización requiere un único soporte')
    if not existentes:
        return None
    soporte = existentes[0]
    if soporte.is_symlink() or not soporte.resolve().is_relative_to(entrada):
        raise ValueError('El soporte debe quedar dentro del buzón')
    return soporte


def procesar(entrada, store):
    entrada = Path(entrada).resolve(strict=True)
    resumen = dict(nuevas=0, repetidas=0, en_espera=0, rechazadas=0, publicables_nuevas=0)
    ahora = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(store.root / 'buzon_cotizaciones.sqlite3')) as db:
        db.executescript(ESQUEMA_COLA)
        for archivo in sorted(entrada.glob('*.json')):
            if not FOLIO.fullmatch(archivo.stem) or archivo.is_symlink() or not archivo.is_file():
                resumen['rechazadas'] += 1
                continue
            if archivo.stat().st_size > 32_768:
                resumen['rechazadas'] += 1
                continue
            contenido = archivo.read_bytes()
            try:
                soporte = _soporte(entrada, archivo.stem)
            except ValueError:
                resumen['rechazadas'] += 1
                continue
            if soporte is None:
                resumen['en_espera'] += 1
                continue
            with soporte.open('rb') as origen:
                digest = file_digest(origen, 'sha256').digest()
            clave = archivo.stem, sha256(sha256(contenido).digest() + digest).hexdigest()
            # Otro ejecutor nunca vuelve a importar una entrega ya procesada.
            with db:
                db.execute('BEGIN IMMEDIATE')
                anterior = db.execute('SELECT estado FROM bandeja WHERE folio=? AND sha_entrada=?', clave).fetchone()
                if anterior:
                    resumen['repetidas' if anterior[0] == 'importada' else 'rechazadas'] += 1
                    continue
                try:
                    datos = json.loads(contenido)
                    if not isinstance(datos, dict):
                        raise ValueError('Se requiere una cotización por archivo')
                    nueva = importar(datos, soporte, store)
                except (ValueError, KeyError, TypeError) as error:
                    db.execute('INSERT INTO bandeja VALUES (?,?,?,?,?,NULL)', (*clave, ahora, 'rechazada', type(error).__name__))
                    resumen['rechazadas'] += 1
                    continue
                db.execute('INSERT INTO bandeja VALUES (?,?,?,?,NULL,?)',
                           (*clave, ahora, 'importada', nueva.get('capture_id')))
                resumen['nuevas' if nueva['nueva'] else 'repetidas'] += 1
                resumen['publicables_nuevas'] += int(nueva['nueva'] and nueva['publicable'])
    return resumen


def exportar_corte(store, destino):
    """Crea SQLite portátil con observaciones autorizadas y campos públicos explícitos."""
    destino = Path(destino).resolve()
    if destino.exists():
        raise FileExistsError(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino.parent) as temp:
        salida = IntradayStore(Path(temp))
        with store._conexion() as src, salida._conexion() as dst:
            src.execute('BEGIN')
            dst.execute('BEGIN IMMEDIATE')
            seleccion = '''
                FROM observaciones_intradia n JOIN ofertas o USING(offer_id)
                JOIN capturas c USING(capture_id) JOIN intentos i USING(capture_id)
                JOIN trabajos t USING(trabajo_id)
                WHERE o.fuente=? AND c.fuente=? AND c.resultado='ok'
                  AND json_type(n.condiciones_json,'$.publicable')='true'
            '''
            tablas = {
                'trabajos': 't.trabajo_id,t.fuente,t.url,t.vencimiento_utc,t.max_intentos',
                'intentos': 'i.capture_id,i.trabajo_id,i.intento,i.inicio_utc,i.fin_utc,NULL,NULL',
                'capturas': 'c.capture_id,c.fuente,c.url,c.fetched_at_utc,c.estado_http,c.resultado,NULL,NULL,c.version_colector',
                'ofertas': 'o.offer_id,o.fuente,o.anuncio_id,o.producto_id,o.variante,o.plataforma,o.vendedor,o.condicion,o.enlace',
                'observaciones_intradia': 'n.capture_id,n.offer_id,n.observed_at,n.source_updated_at,n.precision_temporal,'
                    'n.fecha_precio,n.fecha_cdmx,n.precio,n.moneda,n.precio_tachado,n.disponibilidad,n.condiciones_json,n.enlace',
            }
            for tabla, campos in tablas.items():
                filas = src.execute(f'SELECT DISTINCT {campos} {seleccion} ORDER BY 1,2', (FUENTE, FUENTE))
                registros = (tuple(fila) for fila in filas)
                if tabla == 'observaciones_intradia':
                    registros = (fila[:11] + (json.dumps(condiciones_publicas(json.loads(fila[11])),
                        ensure_ascii=False, allow_nan=False, sort_keys=True), fila[12]) for fila in registros)
                parametros = ','.join('?' for _ in campos.split(','))
                dst.executemany(f'INSERT INTO {tabla} VALUES ({parametros})', registros)
            n = dst.execute('SELECT COUNT(*) FROM observaciones_intradia').fetchone()[0]
            if dst.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('La proyección tiene referencias sin resolver')
            dst.commit()
            dst.execute('PRAGMA journal_mode=DELETE')
            if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('La proyección pública no pasó la verificación')
        if os.name == 'nt':
            salida.database.rename(destino)
        else:
            destino.hardlink_to(salida.database)
    with destino.open('rb') as archivo:
        return {'observaciones_online': n, 'sha256': file_digest(archivo, 'sha256').hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--buzon', type=Path)
    parser.add_argument('--almacen', type=Path, default=RAIZ_INTRADIA)
    parser.add_argument('--corte-publico', type=Path)
    args = parser.parse_args()
    if not (args.buzon or args.corte_publico):
        parser.error('Se requiere --buzon o --corte-publico')
    store = IntradayStore(args.almacen)
    salida = {}
    if args.buzon:
        salida['buzon'] = procesar(args.buzon, store)
    if args.corte_publico:
        salida['corte_publico'] = exportar_corte(store, args.corte_publico)
    print(json.dumps(salida, ensure_ascii=False))
    return 2 if salida.get('buzon', {}).get('rechazadas') else 0


if __name__ == '__main__':
    raise SystemExit(main())
