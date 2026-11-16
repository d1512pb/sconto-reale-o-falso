"""Reproduce la consulta operativa sobre copias transaccionales de SQLite."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from sconto.consulta_v2 import Consulta
from sconto.decisiones_v2 import VERSION, comparar_ofertas_actuales
from sconto.intraday import IntradayStore


def _copiar_snapshot(entrada, destino):
    original = Path(entrada).resolve(strict=True).as_uri() + '?mode=ro'
    with closing(sqlite3.connect(original, uri=True)) as fuente, closing(sqlite3.connect(destino)) as copia:
        fuente.backup(copia)
    with destino.open('rb') as contenido:
        return hashlib.file_digest(contenido, 'sha256').hexdigest()


def reproducir(base_intradia, catalogo, momento, *, productos=(), privadas=False):
    """Usa el mismo reloj explícito, normalización y política de visibilidad que la API."""
    ahora = datetime.fromisoformat(momento)
    if ahora.utcoffset() is None:
        raise ValueError('El instante de evaluación requiere huso horario')
    with TemporaryDirectory() as temporal:
        carpeta = Path(temporal)
        hash_intradia = _copiar_snapshot(base_intradia, carpeta / 'intradia.sqlite3')
        catalogo_snapshot = carpeta / 'catalogo.sqlite' if catalogo is not None else None
        hash_catalogo = _copiar_snapshot(catalogo, catalogo_snapshot) if catalogo_snapshot else None
        consulta = Consulta(IntradayStore(carpeta), catalogo_snapshot, privadas=privadas)
        catalogar = not productos
        if catalogar:
            productos = [fila['producto_id'] for fila in consulta.sql('''
                SELECT DISTINCT o.producto_id FROM ofertas o
                JOIN observaciones_intradia n USING (offer_id) ORDER BY o.producto_id
            ''')]
        resultados, cuenta, evaluables = [], 0, 0
        for producto in sorted(set(productos)):
            ofertas = consulta.ofertas(producto, 75, ahora)
            if catalogar and not ofertas:
                continue
            cuenta += sum(oferta['cobertura_previa']['suficiente'] for oferta in ofertas)
            evaluables += sum(oferta['decision']['estado'] != 'evidencia_insuficiente' for oferta in ofertas)
            resultados.append(dict(producto_id=producto, ofertas=ofertas,
                                   comparacion_actual=comparar_ofertas_actuales(ofertas)))
        return dict(
            esquema='sconto-cuaderno-operativo-v2', regla=VERSION, modo='operativo',
            evaluacion_utc=ahora.astimezone(timezone.utc).isoformat(),
            visibilidad='privada' if privadas else 'publica',
            tope_ofertas_por_producto=75,
            sha256_snapshot_intradia=hash_intradia, sha256_snapshot_catalogo=hash_catalogo,
            numero_ofertas=sum(len(fila['ofertas']) for fila in resultados),
            numero_ofertas_con_historia_previa=cuenta, numero_ofertas_evaluables=evaluables,
            productos=resultados,
        )
