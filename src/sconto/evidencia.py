"""Proyección pública de precios: conserva los campos usados por el parser, no cuentas ni reservas."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from sconto.rutas import DATA, RAW


def proyectar(contenido):
    original = json.loads(contenido)
    props = original['props']
    producto = props.get('producto') or {}
    campos_producto = ('id', 'nombre', 'marca', 'modelo', 'caracteristicas', 'palabras_claves',
                       'variante', 'fecha_creacion', 'tiendas_activas')
    limpio = {campo: producto[campo] for campo in campos_producto if campo in producto}
    for grupo, campos in [('categoria', ('nombre', 'slug_path')), ('facetas', ('marca', 'linea', 'color', 'capacidad'))]:
        valores = producto.get(grupo) or {}
        limpio[grupo] = {campo: valores[campo] for campo in campos if campo in valores}
    ofertas = []
    campos_oferta = ('id', 'enlace_referencia', 'enlace', 'vendedor', 'nombre', 'precio_final',
                     'envio', 'prime', 'marketplace', 'pickup', 'precio')
    for oferta in props.get('resultados') or []:
        valores = {campo: oferta[campo] for campo in campos_oferta if campo in oferta}
        valores['tienda'] = {'nombre': (oferta.get('tienda') or {}).get('nombre')}
        ofertas.append(valores)
    grafico = props.get('datosGrafica') or {}
    resultado = dict(formato='sconto-evidencia-precios-v1',
                     sha256_respuesta_original=hashlib.sha256(contenido).hexdigest(),
                     props=dict(producto=limpio, resultados=ofertas,
                                datosGrafica={campo: grafico[campo] for campo in
                                              ('fechas', 'precios', 'tiendas', 'vendedores') if campo in grafico}))
    return json.dumps(resultado, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def preservar(origen: Path = RAW / 'preciometro', destino: Path = DATA / 'evidencia' / 'preciometro'):
    cantidad = 0
    for archivo in sorted(origen.glob('*/*.json.gz')):
        ruta = destino / archivo.relative_to(origen)
        if ruta.exists():
            continue
        contenido = proyectar(gzip.decompress(archivo.read_bytes()))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix('.gz.tmp')
        temporal.write_bytes(gzip.compress(contenido, mtime=0))
        temporal.replace(ruta)
        cantidad += 1
    return cantidad


if __name__ == '__main__':
    print(f'Evidencias de precios preservadas: {preservar()}')
