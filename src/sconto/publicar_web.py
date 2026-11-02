"""Construye la consulta estática de GitHub Pages desde la entrega verificada del ETL."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from sconto.mart import registros
from sconto.web import leer, verificar


def construir(datos, salida, recursos):
    datos, salida, recursos = Path(datos), Path(salida), Path(recursos)
    manifest = verificar(datos)
    feed = json.loads((datos / 'web_feed.json').read_text(encoding='utf-8'))
    ids = {serie['serie_id'] for serie in feed['series']}
    puntos = leer(datos, 'precios_diarios')
    feed['precios_diarios'] = registros(puntos.loc[puntos.serie_id.isin(ids), ['serie_id', 'fecha_precio', 'precio_mediano']])
    resultados = leer(datos, 'resultados_modelo')
    feed['casos'] = registros(resultados.loc[resultados.evento_id.eq('BF2025')].nlargest(20, 'puntaje_anomalia'))
    feed['ventanas'] = registros(leer(datos, 'eventos'))
    feed['procedencia'] = manifest['fuente']
    salida.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(feed, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    (salida / 'datos.json').write_bytes(contenido)
    (salida / 'snapshot.json').write_text(json.dumps(dict(fecha_corte=manifest['fecha_corte'],
        sha256=hashlib.sha256(contenido).hexdigest())), encoding='utf-8')
    for nombre in ['index.html', 'styles.css', 'app.mjs', 'consulta.mjs']:
        shutil.copy2(recursos / nombre, salida / nombre)
    (salida / '.nojekyll').write_text('', encoding='utf-8')
    return dict(fecha_corte=manifest['fecha_corte'], productos=len(feed['productos']), puntos=len(feed['precios_diarios']))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--datos', type=Path, default=Path('data/analitica'))
    p.add_argument('--salida', type=Path, default=Path('data/analitica/site'))
    p.add_argument('--recursos', type=Path, default=Path('web'))
    a = p.parse_args()
    print(json.dumps(construir(a.datos, a.salida, a.recursos)))
