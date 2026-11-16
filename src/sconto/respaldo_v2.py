"""Copia SQLite consistente y crudos verificables para restauración privada."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import gzip
from hashlib import file_digest
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile

from sconto.intraday import RAIZ_INTRADIA

BASE = 'intradia.sqlite3'
ESQUEMA = 'sconto-respaldo-v1'
SHA = re.compile('[0-9a-f]{64}')


def _hash(ruta, crudo=False):
    abrir = gzip.open if crudo else open
    with abrir(ruta, 'rb') as archivo:
        return file_digest(archivo, 'sha256').hexdigest()


def _abrir(ruta):
    return sqlite3.connect(ruta.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)


def _validar_base(db, *, portable=False):
    if db.execute('PRAGMA integrity_check').fetchone() != ('ok',) or db.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('SQLite no pasó la verificación de integridad')
    referencias = db.execute('SELECT DISTINCT sha256, ruta_cruda FROM capturas WHERE sha256 IS NOT NULL').fetchall()
    if portable and any(ruta != f'raw/{sha}.gz' for sha, ruta in referencias):
        raise ValueError('El respaldo contiene rutas a crudos fuera del paquete')
    return referencias


def respaldar(origen, destino, raices_crudas=()):
    origen, destino = Path(origen).resolve(strict=True), Path(destino).resolve()
    permitidas = [origen, *(Path(ruta).resolve(strict=True) for ruta in raices_crudas)]
    if destino.exists():
        raise FileExistsError(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino.parent) as temp:
        trabajo = Path(temp)
        copia = trabajo / BASE
        archivos = {}
        with closing(_abrir(origen / BASE)) as fuente, closing(sqlite3.connect(copia)) as db:
            fuente.backup(db)
            for sha, relativa in _validar_base(db):
                path = (origen / relativa).resolve(strict=True)
                if (not SHA.fullmatch(sha) or not any(path.is_relative_to(r) for r in permitidas) or
                        _hash(path, crudo=True) != sha):
                    raise ValueError('Crudo no permitido o incongruente con la captura')
                nombre = f'raw/{sha}.gz'
                if nombre not in archivos:
                    guardar = trabajo / nombre
                    guardar.parent.mkdir(exist_ok=True)
                    shutil.copyfile(path, guardar)
                    if _hash(guardar, crudo=True) != sha:
                        raise ValueError('El crudo cambió durante el respaldo')
                    archivos[nombre] = _hash(guardar)
                db.execute('UPDATE capturas SET ruta_cruda=? WHERE sha256=? AND ruta_cruda=?', (nombre, sha, relativa))
            db.commit()
            db.execute('PRAGMA journal_mode=DELETE')
            _validar_base(db, portable=True)
        archivos[BASE] = _hash(copia)
        manifiesto = dict(version=ESQUEMA, generado_utc=datetime.now(timezone.utc).isoformat(), archivos=archivos)
        temporal = trabajo / 'respaldo.zip'
        with ZipFile(temporal, 'x', compression=ZIP_STORED) as z:
            z.writestr('manifest.json', json.dumps(manifiesto, indent=2))
            for nombre in archivos:
                z.write(trabajo / nombre, nombre)
        # La publicación atómica del archivo se hace de forma exclusiva.
        if os.name == 'nt':
            temporal.rename(destino)
        else:
            destino.hardlink_to(temporal)
    return manifiesto


def restaurar(respaldo, destino):
    respaldo, destino = Path(respaldo), Path(destino).resolve()
    if destino.exists():
        raise FileExistsError(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino.parent) as temp, ZipFile(respaldo) as z:
        staging = Path(temp) / 'recuperacion'
        staging.mkdir()
        manifest = z.getinfo('manifest.json')
        if manifest.file_size > 8 * 1024 * 1024:
            raise ValueError('Manifiesto de respaldo demasiado grande')
        manifiesto = json.loads(z.read(manifest))
        archivos = manifiesto['archivos']
        if (manifiesto['version'] != ESQUEMA or BASE not in archivos or
                sorted(z.namelist()) != sorted(['manifest.json', *archivos]) or
                any(n != BASE and not re.fullmatch(r'raw/[0-9a-f]{64}\.gz', n) for n in archivos)):
            raise ValueError('Estructura inválida del respaldo')
        for nombre, sha in archivos.items():
            ruta = staging / nombre
            ruta.parent.mkdir(exist_ok=True)
            with z.open(nombre) as entrada, ruta.open('xb') as salida:
                shutil.copyfileobj(entrada, salida)
            if _hash(ruta) != sha or (nombre != BASE and _hash(ruta, crudo=True) != ruta.stem):
                raise ValueError(f'Hash inválido en {nombre}')
        with closing(_abrir(staging / BASE)) as db:
            referencias = _validar_base(db, portable=True)
            if set(archivos) - {BASE} != {ruta for _, ruta in referencias}:
                raise ValueError('El respaldo no incluye exactamente los crudos referidos')
        staging.rename(destino)
    return manifiesto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operacion', required=True)
    copia = sub.add_parser('respaldar')
    copia.add_argument('zip', type=Path)
    copia.add_argument('--origen', type=Path, default=RAIZ_INTRADIA)
    copia.add_argument('--raiz-crudos', type=Path, action='append', default=[])
    rec = sub.add_parser('restaurar')
    rec.add_argument('zip', type=Path)
    rec.add_argument('destino', type=Path)
    args = parser.parse_args()
    resultado = (respaldar(args.origen, args.zip, args.raiz_crudos) if args.operacion == 'respaldar'
                 else restaurar(args.zip, args.destino))
    print(json.dumps(dict(version=resultado['version'], archivos=len(resultado['archivos']))))


if __name__ == '__main__':
    main()
