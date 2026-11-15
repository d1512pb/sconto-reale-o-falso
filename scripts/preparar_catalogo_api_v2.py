"""Extrae el índice público y las ventanas desde el mart local verificado."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory


def exportar(origen, destino):
    origen = Path(origen).resolve(strict=True)
    destino = Path(destino).resolve()
    if destino.exists():
        raise FileExistsError(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino.parent) as tmp:
        etapa = Path(tmp) / destino.name
        with closing(sqlite3.connect(origen.as_uri() + '?mode=ro', uri=True)) as src, \
                closing(sqlite3.connect(etapa)) as dst, dst:
            dst.executescript('''
                CREATE TABLE catalogo_consulta(producto_canonico_id TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL, categoria_app TEXT);
                CREATE TABLE eventos(evento_id TEXT PRIMARY KEY, base_inicio TEXT NOT NULL, base_fin TEXT NOT NULL);
            ''')
            dst.executemany('INSERT INTO catalogo_consulta VALUES (?, ?, ?)', src.execute('''
                SELECT producto_canonico_id,nombre,categoria_app FROM catalogo_consulta ORDER BY producto_canonico_id
            '''))
            dst.executemany('INSERT INTO eventos VALUES (?, ?, ?)', src.execute('''
                SELECT evento_id,base_inicio,base_fin FROM eventos ORDER BY evento_id
            '''))
            if dst.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('No se pudo generar un catálogo íntegro')
        if os.name == 'nt':
            etapa.rename(destino)
        else:
            destino.hardlink_to(etapa)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origen', type=Path)
    parser.add_argument('destino', type=Path)
    args = parser.parse_args()
    exportar(args.origen, args.destino)
