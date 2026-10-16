"""Crudos comprimidos con SHA-256, tablas bronze idempotentes y estado diario de fuentes."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from sconto.rutas import ALERTA, BRONZE, ESTADO_FUENTES, RAIZ, RAW


def ahora_utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def hoy():
    return date.today().isoformat()


def sha256_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def _seguro(nombre: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', nombre)[:150]


def guardar_crudo(fuente: str, nombre: str, contenido: bytes | str, fecha: str | None = None) -> tuple[str, str]:
    """Guarda la respuesta tal cual (gzip) en data/raw/<fuente>/<fecha>/. Devuelve (ruta relativa, sha256 del original)."""
    if isinstance(contenido, str):
        contenido = contenido.encode('utf-8')
    carpeta = RAW / fuente / (fecha or hoy())
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / (_seguro(nombre) + '.gz')
    with gzip.open(ruta, 'wb', compresslevel=6) as f:
        f.write(contenido)
    return ruta.relative_to(RAIZ).as_posix(), sha256_bytes(contenido)


def leer_crudo(ruta_relativa: str) -> bytes:
    with gzip.open(RAIZ / ruta_relativa, 'rb') as f:
        return f.read()


def escribir_bronze(fuente: str, filas: list[dict] | pd.DataFrame, fecha: str | None = None,
                    clave: list[str] | None = None) -> Path:
    """Una tabla por fuente y fecha de captura. Re-ejecutar el mismo día reemplaza filas con la misma clave."""
    df = filas if isinstance(filas, pd.DataFrame) else pd.DataFrame(filas)
    ruta = BRONZE / fuente / f'{fecha or hoy()}.parquet'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists() and len(df):
        df = pd.concat([pd.read_parquet(ruta), df], ignore_index=True)
    if clave and len(df):
        df = df.drop_duplicates(clave, keep='last')
    df.to_parquet(ruta, index=False)
    return ruta


def leer_bronze(fuente: str) -> pd.DataFrame:
    partes = sorted((BRONZE / fuente).glob('*.parquet'))
    if not partes:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)


CAMPOS_ESTADO = ['fuente', 'fecha', 'estado', 'filas', 'detalle', 'inicio_utc', 'fin_utc', 'entorno']


class _Candado:
    """Candado entre procesos por archivo (varias fuentes pueden terminar a la vez)."""
    def __init__(self, ruta: Path, espera_max=60):
        self.ruta, self.espera_max = ruta.with_suffix(ruta.suffix + '.lock'), espera_max

    def __enter__(self):
        import os
        import time
        inicio = time.monotonic()
        while True:
            try:
                self.fd = os.open(self.ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.monotonic() - inicio > self.espera_max:
                    self.ruta.unlink(missing_ok=True)  # candado huérfano de un proceso caído
                time.sleep(0.2)

    def __exit__(self, *exc):
        import os
        os.close(self.fd)
        self.ruta.unlink(missing_ok=True)


def registrar_estado(fuente: str, estado: str, filas: int, detalle: str = '', inicio_utc: str = '',
                     fecha: str | None = None, entorno: str = 'local'):
    """Upsert por (fuente, fecha, entorno): correr dos veces el mismo día no duplica la fila."""
    assert estado in {'ok', 'fallo', 'bloqueado', 'parcial', 'sin_credenciales'}
    ESTADO_FUENTES.parent.mkdir(parents=True, exist_ok=True)
    with _Candado(ESTADO_FUENTES):
        _registrar_estado(fuente, estado, filas, detalle, inicio_utc, fecha, entorno)


def _registrar_estado(fuente, estado, filas, detalle, inicio_utc, fecha, entorno):
    fecha = fecha or hoy()
    filas_previas = []
    if ESTADO_FUENTES.exists():
        with open(ESTADO_FUENTES, newline='', encoding='utf-8') as f:
            filas_previas = [r for r in csv.DictReader(f)
                             if not (r['fuente'] == fuente and r['fecha'] == fecha and r.get('entorno', 'local') == entorno)]
    filas_previas.append(dict(fuente=fuente, fecha=fecha, estado=estado, filas=filas, detalle=detalle[:500],
                              inicio_utc=inicio_utc, fin_utc=ahora_utc(), entorno=entorno))
    filas_previas.sort(key=lambda r: (r['fecha'], r['fuente'], r.get('entorno', '')))
    ESTADO_FUENTES.parent.mkdir(parents=True, exist_ok=True)
    with open(ESTADO_FUENTES, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_ESTADO)
        w.writeheader()
        w.writerows(filas_previas)


def revisar_alertas() -> list[str]:
    """Fuente con fallo/bloqueo dos días seguidos → ALERTA.md. Sin fallas consecutivas, se elimina la alerta."""
    if not ESTADO_FUENTES.exists():
        return []
    df = pd.read_csv(ESTADO_FUENTES, dtype=str)
    malas = []
    for (fuente, entorno), g in df.groupby(['fuente', 'entorno']):
        ult = g.sort_values('fecha').tail(2)
        if len(ult) == 2 and ult.estado.isin(['fallo', 'bloqueado']).all():
            d0, d1 = pd.to_datetime(ult.fecha)
            if (d1 - d0).days == 1:
                malas.append(f'- **{fuente}** ({entorno}): {ult.estado.iloc[-1]} el {ult.fecha.iloc[0]} y el '
                             f'{ult.fecha.iloc[-1]}. Último detalle: {ult.detalle.iloc[-1]}')
    if malas:
        ALERTA.write_text('# ALERTA de recolección\n\nFuentes con falla dos días seguidos '
                          f'(generado {ahora_utc()}):\n\n' + '\n'.join(malas) + '\n', encoding='utf-8')
    elif ALERTA.exists():
        ALERTA.unlink()
    return malas


def escribir_manifiesto(ruta_archivo: Path, url: str, extra: dict | None = None) -> Path:
    manifiesto = {'url': url, 'archivo': ruta_archivo.name, 'descargado_utc': ahora_utc(),
                  'bytes': ruta_archivo.stat().st_size, 'sha256': sha256_archivo(ruta_archivo), **(extra or {})}
    ruta = ruta_archivo.with_name(ruta_archivo.name + '.manifest.json')
    ruta.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding='utf-8')
    return ruta
