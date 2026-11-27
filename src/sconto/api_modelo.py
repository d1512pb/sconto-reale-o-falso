"""Servicios del modelo final para la API: tarjeta, predicciones, evaluación de precios y predicción con historial propio.

Sólo usa la biblioteca estándar y los archivos exportados por `app_modelo` y `publicar_web`.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from pydantic import BaseModel, ConfigDict, Field

from sconto import prediccion_ligera as L

ID = Annotated[str, PathParam(min_length=1, max_length=96, pattern=r'^[A-Za-z0-9_-]+$')]
ATIPICO = 0.5  # precios menores a la mitad de la mediana: otro producto o error de captura (0.6 % de los días)
EJEMPLO = {
    'inicio_evento': '2026-11-13',
    'precio_actual': 7999,
    'precios': [{'fecha': f, 'precio': p} for f, p in (
        ('2026-09-15', 8999), ('2026-09-22', 8999), ('2026-09-29', 9199), ('2026-10-06', 8999), ('2026-10-13', 8999),
        ('2026-10-20', 9099), ('2026-10-27', 8999), ('2026-10-31', 8799), ('2026-11-07', 8499), ('2026-11-11', 8399))],
}


class Precio(BaseModel):
    fecha: date
    precio: float = Field(gt=0, lt=10_000_000, description='Precio total en MXN de ese día')


class Historial(BaseModel):
    model_config = ConfigDict(json_schema_extra={'examples': [EJEMPLO]})
    precios: list[Precio] = Field(min_length=1, max_length=2000,
                                  description='Precios fechados del mismo producto, tienda y variante')
    inicio_evento: date = Field(default=date(2026, 11, 13), description='Primer día del Buen Fin a predecir')
    precio_actual: float | None = Field(default=None, gt=0, lt=10_000_000,
                                        description='Precio que ves hoy, para compararlo con la base')


class Sitio:
    """Lee las fichas publicadas de la app (mismo corte que ve el usuario)."""

    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        snapshot = json.loads((self.raiz / 'snapshot.json').read_text(encoding='utf-8'))
        feed = json.loads((self.raiz / snapshot['archivo']).read_text(encoding='utf-8'))
        self.fecha_corte = feed['fecha_corte']
        self.evento = next(e for e in feed['ventanas'] if e['evento_id'] == feed['evento_actual'])
        self.detalles = feed['detalles']
        self.nombres = {p['producto_canonico_id']: p['nombre'] for p in feed['productos']}
        self.ficha = lru_cache(maxsize=256)(self._ficha)

    def _ficha(self, producto_id: str) -> dict | None:
        archivo = self.detalles.get(producto_id)
        if not archivo:
            return None
        return json.loads((self.raiz / archivo['archivo']).read_text(encoding='utf-8'))

    def referencia(self, producto_id: str) -> dict | None:
        ficha = self.ficha(producto_id)
        if not ficha:
            return None
        serie = next((s for s in ficha['series'] if s['contexto'] == 'minimo_multitienda'), None)
        if not serie:
            return dict(ref=None, puntos=[])
        ref = next((r for r in ficha['referencias'] if r['serie_id'] == serie['serie_id']
                    and r['evento_id'] == self.evento['evento_id']), None)
        puntos = sorted((p['fecha_precio'], p['precio_mediano']) for p in ficha['precios_diarios']
                        if p['serie_id'] == serie['serie_id'])
        return dict(ref=ref, puntos=puntos)


def registrar(api: FastAPI, modelo_dir: Path, sitio: Path | None = None) -> None:
    modelo_dir = Path(modelo_dir)
    tarjeta = json.loads((modelo_dir / 'modelo.json').read_text(encoding='utf-8'))
    arbol = json.loads((modelo_dir / 'arbol.json').read_text(encoding='utf-8'))
    datos_sitio = Sitio(sitio) if sitio and (Path(sitio) / 'snapshot.json').is_file() else None
    reglas = tarjeta['reglas']
    version = 'sconto-api-v1'

    @api.get('/v1/modelo', tags=['Modelo'], summary='Tarjeta del modelo: pregunta, esquema temporal, métricas y reglas')
    def modelo():
        return {'version': version, **{k: v for k, v in tarjeta.items() if k != 'predicciones'},
                'productos_con_prediccion': len(tarjeta['predicciones'])}

    @api.get('/v1/modelo/predicciones', tags=['Modelo'], summary='Productos con predicción del Buen Fin 2026 y su resultado')
    def predicciones(limit: Annotated[int, Query(ge=1, le=200)] = 20,
                     solo: Annotated[str | None, Query(pattern=r'^(aciertos|fallos)$')] = None):
        filas = []
        for pid, p in tarjeta['predicciones'].items():
            if solo == 'aciertos' and not p['acierto'] or solo == 'fallos' and p['acierto']:
                continue
            nombre = datos_sitio.nombres.get(pid) if datos_sitio else None
            filas.append(dict(producto_id=pid, nombre=nombre, **p))
        filas.sort(key=lambda f: -f['prob_bajada'])
        return {'version': version, 'total': len(filas), 'predicciones': filas[:limit]}

    @api.get('/v1/products/{producto_id}/prediccion', tags=['Modelo'],
             summary='Predicción del modelo para un producto y resultado observado en el Buen Fin 2026')
    def prediccion(producto_id: ID):
        p = tarjeta['predicciones'].get(producto_id)
        if not p:
            raise HTTPException(404, 'Este producto no tiene una serie con base, previo y evento en 2026')
        return {'version': version, 'producto_id': producto_id, 'modelo': tarjeta['modelo'], **p}

    @api.get('/v1/products/{producto_id}/evaluar-precio', tags=['Precio'],
             summary='Compara el precio que ves contra la historia del producto (regla 5 % + cuartiles)')
    def evaluar_precio(producto_id: ID, precio: Annotated[float, Query(gt=0, lt=10_000_000)]):
        if datos_sitio is None:
            raise HTTPException(503, 'El catálogo de la app no está cargado en este servidor')
        r = datos_sitio.referencia(producto_id)
        if r is None:
            raise HTTPException(404, 'Producto fuera del catálogo')
        ref = r['ref']
        respuesta = {'version': version, 'producto_id': producto_id, 'nombre': datos_sitio.nombres.get(producto_id),
                     'precio': precio, 'fecha_corte': datos_sitio.fecha_corte}
        if not ref or not ref.get('cobertura_base') or (ref.get('n_fechas_base') or 0) < reglas['min_fechas_base'] \
                or (ref.get('amplitud_base_dias') or 0) < reglas['min_amplitud_dias']:
            return {**respuesta, 'estado': 'evidencia_insuficiente',
                    'motivo': 'Se necesitan al menos 4 días con precio en 21 días o más dentro de la base.'}
        base = [p for f, p in r['puntos'] if ref['base_inicio'] <= f <= ref['base_fin']]
        evaluacion = L.regla_precio(precio, ref['mediana_base'], ref['p25_base'], ref['p75_base'], reglas['umbral_pct'])
        return {**respuesta, **evaluacion, 'base_inicio': ref['base_inicio'], 'base_fin': ref['base_fin'],
                'dias_base': ref['n_fechas_base'],
                'mas_barato_que_pct_de_dias': 100 * sum(v > precio for v in base) / len(base) if base else None,
                'minimo_historico': min((p for _, p in r['puntos'] if p >= ATIPICO * ref['mediana_base']), default=None),
                'dias_atipicos_omitidos': sum(p < ATIPICO * ref['mediana_base'] for _, p in r['puntos']),
                'ultimo_registro': dict(zip(('fecha', 'precio'), r['puntos'][-1])) if r['puntos'] else None}

    @api.post('/v1/predecir', tags=['Modelo'],
              summary='Trae el historial de cualquier producto de tecnología: ¿bajará en el Buen Fin?')
    def predecir(historial: Historial):
        precios = [(p.fecha, p.precio) for p in historial.precios if p.fecha < historial.inicio_evento]
        x = L.caracteristicas(precios, historial.inicio_evento)
        salida = {'version': version, 'modelo': {k: tarjeta['modelo'][k] for k in ('familia', 'variante')},
                  'inicio_evento': historial.inicio_evento.isoformat(),
                  'precios_usados': len(precios), 'caracteristicas': {k: x.get(k) for k in arbol['variables']},
                  'completo': x['completo'], 'faltan': x['faltan'], 'prediccion': None, 'evaluacion_precio': None,
                  'aviso': 'Usa precios del mismo producto, variante y tienda. La predicción es una señal, no una garantía.'}
        if x['completo']:
            prob = L.evaluar_arbol(arbol, x)
            hoja = L.hoja_arbol(arbol, x)
            salida['prediccion'] = dict(
                bajara=prob >= .5, prob_modelo=round(prob, 4), casos_parecidos=hoja.get('casos'),
                pct_bajaron_parecidos=round(100 * hoja['bajaron'] / hoja['casos'], 1) if hoja.get('casos') else None,
                pct_bajada_general=round(100 * arbol['tasa_general'], 1) if arbol.get('tasa_general') else None,
                explicacion=L.ruta_arbol(arbol, x))
        if historial.precio_actual and x['n_base'] >= reglas['min_fechas_base'] and \
                x.get('amplitud_base_dias', 0) >= reglas['min_amplitud_dias']:
            salida['evaluacion_precio'] = L.regla_precio(historial.precio_actual, x['mediana_base'], x['p25_base'],
                                                         x['p75_base'], reglas['umbral_pct'])
        return salida
