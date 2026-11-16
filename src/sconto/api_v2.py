"""API de consulta. La escritura y las consultas a fuentes corren fuera del servidor HTTP."""
from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sconto.consulta_v2 import Consulta
from sconto.decisiones_v2 import VERSION as MOTOR_VERSION
from sconto.intraday import RAIZ_INTRADIA, VERSION as CAPTURA_VERSION, IntradayStore

VERSION = 'sconto-api-v1'
ID = Annotated[str, PathParam(min_length=1, max_length=96, pattern=r'^[A-Za-z0-9_-]+$')]


def crear_api(*, root=RAIZ_INTRADIA, catalogo=None, datos_profeco=False, privadas=False, origenes=(),
              max_peticiones=300, reloj=lambda: datetime.now(timezone.utc)):
    @asynccontextmanager
    async def lifespan(api):
        api.state.consulta = Consulta(IntradayStore(root), catalogo, datos_profeco, privadas)
        yield

    api = FastAPI(title='Sconto', version=VERSION, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    recientes = deque()
    lock = Lock()

    @api.middleware('http')
    async def presupuesto(request: Request, call_next):
        if request.url.path != '/health':
            ahora = monotonic()
            with lock:
                while recientes and ahora - recientes[0] >= 60:
                    recientes.popleft()
                if len(recientes) >= max_peticiones:
                    return JSONResponse({'detail': 'Límite temporal de consultas'}, 429,
                                        headers={'Retry-After': '60', 'Cache-Control': 'no-store'})
                recientes.append(ahora)
        respuesta = await call_next(request)
        respuesta.headers['Cache-Control'] = 'no-store'
        return respuesta

    if origenes:
        api.add_middleware(CORSMiddleware, allow_origins=list(origenes), allow_methods=['GET'], allow_headers=[])

    @api.get('/health')
    def health():
        api.state.consulta.sql('SELECT 1 FROM capturas LIMIT 1')
        return {'ok': True}

    @api.get('/v1/version')
    def version():
        return {'version': VERSION, 'captura': CAPTURA_VERSION, 'motor': MOTOR_VERSION,
                'revision': os.getenv('SCONTO_REVISION')}

    @api.get('/v1/status')
    def status():
        consulta = api.state.consulta
        estado = consulta.store.estado()
        fuentes = estado['fuentes'] if consulta.privadas else [f for f in estado['fuentes']
            if f['fuente'] == 'profeco_buen_fin' and consulta.datos_profeco]
        return {'version': VERSION, 'fuentes': fuentes, 'catalogo': consulta.catalogo is not None,
                'hora_utc': reloj().isoformat()}

    @api.get('/v1/products')
    def productos(q: Annotated[str, Query(max_length=100)] = '', limit: Annotated[int, Query(ge=1, le=50)] = 15,
                  canal: Annotated[str | None, Query(pattern=r'^(tienda_fisica|en_linea)$')] = None):
        return {'version': VERSION, 'productos': api.state.consulta.productos(q, limit, canal=canal)}

    def consultar(producto_id):
        consulta = api.state.consulta
        if not consulta.productos('', 1, producto_id):
            raise HTTPException(404, 'Producto fuera del catálogo disponible')
        return consulta

    @api.get('/v1/products/{producto_id}/offers')
    def ofertas(producto_id: ID, limit: Annotated[int, Query(ge=1, le=50)] = 25):
        ahora = reloj().astimezone(timezone.utc)
        return {'version': VERSION, 'producto_id': producto_id, 'evaluado_utc': ahora.isoformat(),
                'ofertas': consultar(producto_id).ofertas(producto_id, limit, ahora)}

    @api.get('/v1/products/{producto_id}/history')
    def historia(producto_id: ID, limit: Annotated[int, Query(ge=1, le=400)] = 100):
        return {'version': VERSION, 'producto_id': producto_id,
                'precios_diarios': consultar(producto_id).historia(producto_id, limit)}

    @api.get('/v1/products/{producto_id}/decision')
    def decision(producto_id: ID):
        ahora = reloj().astimezone(timezone.utc)
        filas = consultar(producto_id).ofertas(producto_id, 50, ahora)
        return {'version': VERSION, 'producto_id': producto_id, 'motor': MOTOR_VERSION,
                'evaluado_utc': ahora.isoformat(),
                'decisiones': [dict(offer_id=fila['offer_id'], **fila['decision']) for fila in filas]}

    @api.get('/v1/products/{producto_id}/comparacion-actual')
    def comparacion_actual(producto_id: ID):
        ahora = reloj().astimezone(timezone.utc)
        resultado = consultar(producto_id).comparacion_actual(producto_id, ahora)
        return {'version': VERSION, 'producto_id': producto_id, 'evaluado_utc': ahora.isoformat(), **resultado}

    return api


def app():
    return crear_api(root=Path(os.getenv('SCONTO_API_DATOS', RAIZ_INTRADIA)), catalogo=os.getenv('SCONTO_API_CATALOGO'),
                     origenes=tuple(x.strip() for x in os.getenv('SCONTO_API_ORIGENES', '').split(',') if x.strip()),
                     datos_profeco=os.getenv('SCONTO_API_PROFECO') == '1',
                     privadas=os.getenv('SCONTO_API_REVISION_PRIVADA') == '1')
