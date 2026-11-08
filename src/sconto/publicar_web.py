"""Construye la consulta estática de GitHub Pages desde la entrega verificada del ETL."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil

import pandas as pd

from sconto.catalogo import CATEGORIAS, categoria_app
from sconto.mart import registros
from sconto.web import leer, verificar


def construir(datos, salida, recursos):
    datos, salida, recursos = Path(datos), Path(salida), Path(recursos)
    manifest = verificar(datos)
    from sconto.app_datos import preparar_aplicacion

    if 'app_feed.json' in manifest['archivos'] and 'indice_busqueda.json' in manifest['archivos']:
        feed = json.loads((datos / 'app_feed.json').read_text(encoding='utf-8'))
        indice = json.loads((datos / 'indice_busqueda.json').read_text(encoding='utf-8'))
    else:
        nombres = ['productos', 'eventos', 'series', 'referencias_base', 'precios_diarios', 'ofertas']
        tablas = {n: pd.read_parquet(datos / (n + '.parquet')) for n in nombres}
        _, extras = preparar_aplicacion(tablas, manifest['fecha_corte'])
        feed, indice = extras['app_feed.json'], extras['indice_busqueda.json']
    feed['ventanas'] = registros(leer(datos, 'eventos'))
    feed['evento_actual'] = next((e['evento_id'] for e in feed['ventanas'] if str(e['d0']).startswith(feed['fecha_corte'][:4])), 'BF2026')
    feed['busqueda'] = indice
    feed['calidad'] = registros(leer(datos, 'calidad_fuentes'))
    feed.pop('historial', None)
    feed['procedencia'] = manifest['fuente']
    salida.mkdir(parents=True, exist_ok=True)
    ofertas, series, referencias, puntos = (defaultdict(list) for _ in range(4))
    for o in feed['ofertas']:
        ofertas[o['producto_canonico_id']].append(o)
    for s in feed['series']:
        if s['contexto'] == 'minimo_multitienda':
            series[s['producto_canonico_id']].append(s)
    for r in feed['referencias']:
        if r['evento_id'] == feed['evento_actual']:
            referencias[r['serie_id']].append(r)
    diarios = leer(datos, 'precios_diarios')
    ids = {s['serie_id'] for lista in series.values() for s in lista}
    for p in registros(diarios.loc[diarios.serie_id.isin(ids), ['serie_id', 'fecha_precio', 'precio_mediano']]):
        puntos[p['serie_id']].append(p)
    feed['detalles'] = {}
    for producto in feed['productos']:
        if not producto.get('categoria_app'):
            producto['categoria_app'] = categoria_app(producto['nombre'], producto.get('familia'), producto.get('categoria'))
            producto['categoria_app_nombre'] = CATEGORIAS[producto['categoria_app']]
        pid = producto['producto_canonico_id']
        ficha = dict(version='sconto-producto-v1', fecha_corte=feed['fecha_corte'], producto_canonico_id=pid,
                     ofertas=ofertas[pid], series=series[pid],
                     referencias=[r for s in series[pid] for r in referencias[s['serie_id']]],
                     precios_diarios=[p for s in series[pid] for p in puntos[s['serie_id']]])
        producto.setdefault('ultima_fecha_observada', max((p['fecha_precio'] for p in ficha['precios_diarios']), default=None))
        contenido = json.dumps(ficha, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        sha = hashlib.sha256(contenido).hexdigest()
        nombre = f'producto.{sha[:16]}.json'
        (salida / nombre).write_bytes(contenido)
        feed['detalles'][pid] = dict(archivo=nombre, sha256=sha)
    campos = ['obs_id', 'producto_canonico_id', 'fecha_precio', 'precio', 'moneda', 'plataforma',
              'identidad_oferta', 'indicador', 'ahorro_referencia_pct', 'brecha_pp', 'contexto_referencia']
    feed['ofertas'] = [{k: o.get(k) for k in campos} for o in feed['ofertas']]
    feed['series'], feed['referencias'], feed['precios_diarios'] = [], [], []
    feed['version'] = 'sconto-app-v2'
    feed['categorias'] = registros(pd.DataFrame(feed['productos']).groupby(['categoria_app', 'categoria_app_nombre'], as_index=False).size())
    contenido = json.dumps(feed, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    sha = hashlib.sha256(contenido).hexdigest()
    archivo_datos = f'datos.{sha[:16]}.json'
    (salida / archivo_datos).write_bytes(contenido)
    (salida / 'snapshot.json').write_text(json.dumps(dict(version='sconto-app-v2', fecha_corte=manifest['fecha_corte'],
        archivo=archivo_datos, sha256=sha)), encoding='utf-8')
    for archivo in recursos.rglob('*'):
        if archivo.is_file():
            destino = salida / archivo.relative_to(recursos)
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archivo, destino)
    recursos_shell = ['index.html', 'styles.css', 'interfaz.css', 'app.mjs', 'motor.mjs', 'datos.mjs', 'interfaz.mjs', 'manifest.webmanifest',
                      'icons/icon-192.png', 'icons/icon-512.png', 'icons/apple-touch-icon.png', 'icons/logo.svg']
    version = hashlib.sha256(b''.join((salida / p).read_bytes() for p in recursos_shell + ['sw.js'])).hexdigest()[:16]
    trabajador = (salida / 'sw.js').read_text(encoding='utf-8').replace('__SCONTO_VERSION__', version)
    (salida / 'sw.js').write_text(trabajador, encoding='utf-8')
    (salida / '.nojekyll').write_text('', encoding='utf-8')
    return dict(fecha_corte=manifest['fecha_corte'], productos=len(feed['productos']), puntos=sum(map(len, puntos.values())), bytes_indice=len(contenido))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--datos', type=Path, default=Path('data/analitica'))
    p.add_argument('--salida', type=Path, default=Path('data/analitica/site'))
    p.add_argument('--recursos', type=Path, default=Path('web'))
    a = p.parse_args()
    print(json.dumps(construir(a.datos, a.salida, a.recursos)))
