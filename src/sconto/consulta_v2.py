"""Consulta SQLite y construcción reproducible de decisiones para API y notebook."""
from __future__ import annotations

from contextlib import closing
from datetime import date
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import urlsplit

from sconto.decisiones_v2 import (cobertura_historica, comparar_ofertas_actuales, evaluar_decision,
                                  normalizar_gtin, referencia_diaria)
from sconto.intraday import CDMX


TIENDAS = {'www.sears.com.mx', 'sears.com.mx', 'www.liverpool.com.mx', 'liverpool.com.mx'}


def leer_sql(ruta, sql, params=()):
    with closing(sqlite3.connect(Path(ruta).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.create_function('normalizado', 1, _normalizar, deterministic=True)
        conn.create_function('enlace_publicable', 1, _enlace_publicable, deterministic=True)
        return [dict(fila) for fila in conn.execute(sql, params)]


def _normalizar(valor):
    return ''.join(c for c in unicodedata.normalize('NFKD', (valor or '').casefold())
                   if not unicodedata.combining(c))


def _enlace_publicable(url):
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    # Aceptar sólo enlaces comerciales canónicos previamente revisados en la importación.
    return (partes.scheme == 'https' and partes.netloc.lower() in TIENDAS and partes.path and
            not partes.fragment and re.fullmatch(r'(?:skuid=\d+)?', partes.query) is not None)


class Consulta:
    def __init__(self, store, catalogo=None, datos_profeco=False, privadas=False):
        self.store = store
        self.catalogo = Path(catalogo) if catalogo else None
        self.datos_profeco = datos_profeco
        self.privadas = privadas

    def sql(self, sql, params=()):
        return leer_sql(self.store.database, sql, params)

    def productos(self, q, limite, producto_id=None, canal=None):
        consulta = _normalizar(q).split()
        if producto_id is not None:
            filtro, params = 'producto_id = ?', [producto_id]
        else:
            filtro = ' AND '.join("instr(normalizado(nombre || ' ' || producto_id), ?) > 0" for _ in consulta) or '1=1'
            params = consulta
        catalogo = []
        if self.catalogo is not None and canal != 'tienda_fisica':
            catalogo = leer_sql(self.catalogo, f'''
                SELECT producto_id, nombre, categoria, 'en_linea' AS canal FROM (
                    SELECT producto_canonico_id AS producto_id, nombre, categoria_app AS categoria
                    FROM catalogo_consulta
                ) WHERE {filtro} ORDER BY nombre, producto_id LIMIT ?
            ''', (*params, limite))
        if self.datos_profeco and canal != 'en_linea':
            catalogo.extend(self.sql(f'''
                SELECT producto_id, nombre, 'profeco_buen_fin' AS categoria, 'tienda_fisica' AS canal FROM (
                    SELECT producto_id, MIN(COALESCE(json_extract(condiciones_json, '$.marca') || ' ', '') ||
                        json_extract(condiciones_json, '$.descripcion')) AS nombre
                    FROM ofertas JOIN observaciones_diarias_fuente USING(offer_id)
                    WHERE fuente='profeco_buen_fin' GROUP BY producto_id
                ) WHERE {filtro} ORDER BY nombre, producto_id LIMIT ?
            ''', (*params, limite)))
        if producto_id is not None and not catalogo and canal != 'tienda_fisica':
            filas = self.store.ofertas(producto_id, 75)
            if filas and any(self.oferta_visible(fila) for fila in filas):
                catalogo.append(dict(producto_id=producto_id, nombre=producto_id, categoria=None, canal='en_linea'))
        return sorted(catalogo, key=lambda fila: (_normalizar(fila['nombre']), fila['producto_id']))[:limite]

    def oferta_visible(self, oferta):
        return self.privadas or (oferta['fuente'] == 'tienda_manual' and
            oferta['condiciones'].get('publicable') is True and _enlace_publicable(oferta['enlace']))

    def ventana_base(self, ahora):
        if self.catalogo is None:
            return None
        filas = leer_sql(self.catalogo, 'SELECT base_inicio, base_fin FROM eventos WHERE evento_id=?',
                         (f'BF{ahora.astimezone(CDMX).year}',))
        return filas[0] if filas else None

    def referencia(self, oferta, ahora, base):
        if not base or oferta['fuente'] != 'tienda_manual':
            return None
        filas = self.sql('''
            SELECT offer_id, fecha_cdmx AS fecha_precio, moneda, precio, observed_at, source_updated_at,
                   precision_temporal, disponibilidad, condiciones_json
            FROM observaciones_intradia WHERE offer_id=? AND moneda=? AND fecha_cdmx BETWEEN ? AND ?
        ''', (oferta['offer_id'], oferta['moneda'], base['base_inicio'], base['base_fin']))
        registros = []
        for fila in filas:
            condiciones = json.loads(fila.pop('condiciones_json'))
            if condiciones.get('publicable') is not True and not self.privadas:
                continue
            registros.append(_calidad_descriptor(fila, oferta, condiciones))
        return referencia_diaria(registros, oferta, base_inicio=date.fromisoformat(base['base_inicio']),
                                 base_fin=date.fromisoformat(base['base_fin']), hoy=ahora.astimezone(CDMX).date())

    def ofertas(self, producto_id, limite, ahora):
        filas = self.store.ofertas(producto_id, 75)
        base = self.ventana_base(ahora)
        ofertas = []
        # Exponer una lista cerrada de campos, incluso en la vista de revisión local.
        campos = ('offer_id', 'producto_id', 'fuente', 'plataforma', 'vendedor', 'variante', 'condicion',
                  'enlace', 'precio', 'moneda', 'precio_tachado', 'observed_at', 'source_updated_at',
                  'fetched_at_utc', 'precision_temporal', 'disponibilidad')
        for fila in filas:
            if not self.oferta_visible(fila):
                continue
            oferta = _calidad_descriptor({k: fila[k] for k in campos}, fila, fila['condiciones'])
            oferta['fecha_precio'] = fila['fecha_precio'] or fila['fecha_cdmx']
            referencia = self.referencia(oferta, ahora, base)
            oferta['decision'] = evaluar_decision(oferta, referencia, ahora=ahora)
            oferta['cobertura_previa'] = cobertura_historica(oferta, referencia, base)
            ofertas.append(oferta)
        return ofertas[:limite]

    def comparacion_actual(self, producto_id, ahora):
        return comparar_ofertas_actuales(self.ofertas(producto_id, 75, ahora))

    def historia(self, producto_id, limite):
        if producto_id.startswith('PROFECO-BF26-') and self.datos_profeco:
            # El precio físico se devuelve por día y sucursal, sin inventar hora de levantamiento.
            return self.sql('''
                SELECT d.offer_id, d.fecha_precio, d.moneda, d.precio, d.valores_distintos,
                       d.ultima_consulta_utc AS fetched_at_utc, o.vendedor, 'tienda_fisica' AS canal,
                       'dia' AS precision_temporal, 'profeco_buen_fin' AS fuente FROM precios_diarios_fuente d
                JOIN ofertas o USING(offer_id) WHERE o.producto_id=? AND o.fuente='profeco_buen_fin'
                ORDER BY d.fecha_precio DESC, d.offer_id, d.moneda LIMIT ?
            ''', (producto_id, limite))
        if self.privadas:
            return [dict(row, canal='en_linea', fecha_precio=row['fecha'], precio=row['mediana'])
                    for row in self.store.precios_diarios(producto_id, limite)]
        # La condición de publicación se aplica a cada punto, también cuando la última captura cambió.
        return self.sql('''
            SELECT n.offer_id, n.fecha_cdmx AS fecha_precio, n.moneda, MIN(n.precio) AS minimo,
                   MAX(n.precio) AS maximo, COUNT(*) AS comprobaciones, 'en_linea' AS canal,
                   'tienda_manual' AS fuente FROM observaciones_intradia n JOIN ofertas o USING(offer_id)
            WHERE o.producto_id=? AND o.fuente='tienda_manual' AND
                json_type(n.condiciones_json, '$.publicable')='true' AND enlace_publicable(n.enlace)
            GROUP BY n.offer_id,n.fecha_cdmx,n.moneda ORDER BY n.fecha_cdmx DESC,n.offer_id,n.moneda LIMIT ?
        ''', (producto_id, limite))


def _calidad_descriptor(destino, identidad, condiciones):
    manual = identidad['fuente'] == 'tienda_manual'
    if manual:
        destino['disponibilidad'] = {'disponible': 'en_stock', 'agotado': 'agotado'}.get(destino['disponibilidad'])
    destino.update(canal='en_linea', vendedor=identidad['vendedor'], variante=identidad['variante'],
                   condicion=identidad['condicion'], verificacion='directa' if manual else 'archivada',
                   identidad_confirmada=manual and condiciones.get('identidad_verificada') is True,
                   costo_total_confirmado=condiciones.get('costo_total_confirmado')
                   if manual and condiciones.get('cargos_confirmados') is True else None,
                   contexto_costo=condiciones.get('contexto_costo') if manual else None,
                   gtin=normalizar_gtin(condiciones.get('gtin')) if manual else None,
                   promocion_condicionada=bool(condiciones['promocion_condicionada'])
                   if condiciones.get('promocion_condicionada') is not None else None)
    return destino
