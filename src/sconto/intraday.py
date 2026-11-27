"""Evidencia intradía separada del contrato diario y de los crudos anteriores."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sconto.rutas import DATA

VERSION = 'captura-v2.1'
VERSION_COTIZACION = 'cotizacion-tienda-v2.1'
CDMX = ZoneInfo('America/Mexico_City')
RAIZ_INTRADIA = DATA / 'operacion' / 'v2' / 'intradia'
ESTADOS = {'ok', 'sin_oferta', 'bloqueado', 'no_permitido', 'fallo', 'interrumpido'}

ESQUEMA = '''
CREATE TABLE IF NOT EXISTS trabajos (
    trabajo_id TEXT PRIMARY KEY,
    fuente TEXT NOT NULL,
    url TEXT NOT NULL,
    vencimiento_utc TEXT NOT NULL,
    max_intentos INTEGER NOT NULL CHECK(max_intentos >= 1),
    UNIQUE(fuente, url, vencimiento_utc)
);
CREATE TABLE IF NOT EXISTS intentos (
    capture_id TEXT PRIMARY KEY,
    trabajo_id TEXT NOT NULL REFERENCES trabajos(trabajo_id),
    intento INTEGER NOT NULL,
    inicio_utc TEXT NOT NULL,
    fin_utc TEXT,
    reintento_permitido INTEGER CHECK(reintento_permitido IN (0, 1)),
    ultimo_error TEXT,
    UNIQUE(trabajo_id, intento)
);
CREATE TABLE IF NOT EXISTS capturas (
    capture_id TEXT PRIMARY KEY REFERENCES intentos(capture_id),
    fuente TEXT NOT NULL,
    url TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    estado_http INTEGER,
    resultado TEXT NOT NULL,
    sha256 TEXT,
    ruta_cruda TEXT,
    version_colector TEXT NOT NULL,
    CHECK((sha256 IS NULL) = (ruta_cruda IS NULL))
);
CREATE TABLE IF NOT EXISTS ofertas (
    offer_id TEXT PRIMARY KEY,
    fuente TEXT NOT NULL,
    anuncio_id TEXT NOT NULL,
    producto_id TEXT NOT NULL,
    variante TEXT,
    plataforma TEXT NOT NULL,
    vendedor TEXT,
    condicion TEXT,
    enlace TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ofertas_producto ON ofertas(producto_id);
CREATE TABLE IF NOT EXISTS observaciones_intradia (
    capture_id TEXT NOT NULL REFERENCES capturas(capture_id),
    offer_id TEXT NOT NULL REFERENCES ofertas(offer_id),
    observed_at TEXT,
    source_updated_at TEXT,
    precision_temporal TEXT NOT NULL CHECK(precision_temporal IN ('instante', 'dia')),
    fecha_precio TEXT,
    fecha_cdmx TEXT NOT NULL,
    precio REAL NOT NULL CHECK(precio > 0),
    moneda TEXT NOT NULL,
    precio_tachado REAL CHECK(precio_tachado > 0),
    disponibilidad TEXT,
    condiciones_json TEXT NOT NULL,
    enlace TEXT NOT NULL,
    PRIMARY KEY(capture_id, offer_id),
    CHECK((precision_temporal = 'dia' AND observed_at IS NULL AND fecha_precio IS NOT NULL)
       OR (precision_temporal = 'instante' AND observed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS observaciones_oferta_dia ON observaciones_intradia(offer_id, fecha_cdmx);
CREATE INDEX IF NOT EXISTS capturas_fuente_fecha ON capturas(fuente, fetched_at_utc);
CREATE TABLE IF NOT EXISTS observaciones_diarias_fuente (
    capture_id TEXT NOT NULL REFERENCES capturas(capture_id),
    offer_id TEXT NOT NULL REFERENCES ofertas(offer_id),
    fecha_precio TEXT NOT NULL,
    precio REAL NOT NULL CHECK(precio > 0),
    moneda TEXT NOT NULL,
    condiciones_json TEXT NOT NULL,
    PRIMARY KEY(capture_id, offer_id, fecha_precio, moneda)
);
CREATE INDEX IF NOT EXISTS diarios_fuente_oferta ON observaciones_diarias_fuente(offer_id, fecha_precio);
CREATE VIEW IF NOT EXISTS precios_diarios_fuente AS
SELECT offer_id, fecha_precio, moneda,
       CASE WHEN MIN(precio) = MAX(precio) THEN MIN(precio) END AS precio,
       MIN(fetched_at_utc) AS primera_consulta_utc,
       MAX(fetched_at_utc) AS ultima_consulta_utc,
       COUNT(*) AS consultas, COUNT(DISTINCT precio) AS valores_distintos
FROM observaciones_diarias_fuente JOIN capturas USING(capture_id)
GROUP BY offer_id, fecha_precio, moneda;
'''


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(valor: datetime) -> str:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError('La hora requiere un huso explícito')
    return valor.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _id(*partes: str | None) -> str:
    return hashlib.sha256(json.dumps(partes, ensure_ascii=False).encode()).hexdigest()


def _clave_texto(valor: str | None) -> str | None:
    return ' '.join(valor.casefold().split()) if valor else None


def _validar_fuente_url(fuente: str, url: str) -> None:
    partes = urlsplit(url)
    if (not re.fullmatch(r'[a-z][a-z0-9_]*', fuente) or partes.scheme != 'https'
            or not partes.hostname or partes.username is not None or partes.password is not None
            or partes.port not in (None, 443) or partes.fragment or re.search(r'[\s\\\x00-\x1f]', url)):
        raise ValueError('Fuente o URL HTTPS inválida')


@dataclass(frozen=True)
class Oferta:
    anuncio_id: str
    producto_id: str
    plataforma: str
    enlace: str
    variante: str | None = None
    vendedor: str | None = None
    condicion: str | None = None

    def identificador(self, fuente: str) -> str:
        return _id(fuente, self.anuncio_id, self.producto_id, self.variante,
                   _clave_texto(self.plataforma), _clave_texto(self.vendedor), _clave_texto(self.condicion))


@dataclass(frozen=True)
class Observacion:
    oferta: Oferta
    precio: float
    moneda: str
    observed_at: datetime | None = None
    source_updated_at: datetime | None = None
    precision_temporal: str = 'instante'
    fecha_precio: date | None = None
    precio_tachado: float | None = None
    disponibilidad: str | None = None
    condiciones: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Trabajo:
    fuente: str
    url: str
    vencimiento: datetime
    max_intentos: int = 1

    @property
    def trabajo_id(self) -> str:
        return _id(self.fuente, self.url, _utc(self.vencimiento))


@dataclass(frozen=True)
class Captura:
    trabajo: Trabajo
    capture_id: str
    intento: int


class IntradayStore:
    def __init__(self, root: Path = RAIZ_INTRADIA):
        self.root = Path(root).resolve()
        self.database = self.root / 'intradia.sqlite3'
        self.root.mkdir(parents=True, exist_ok=True)
        with self._conexion() as conexion:
            conexion.execute('PRAGMA journal_mode=WAL')
            conexion.executescript(ESQUEMA)

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.database, timeout=15)) as conexion, conexion:
            conexion.row_factory = sqlite3.Row
            conexion.execute('PRAGMA foreign_keys=ON')
            yield conexion

    @contextmanager
    def exclusividad_colector(self, nombre: str = 'colector.lock') -> Iterator[bool]:
        """El sistema operativo libera el bloqueo incluso si se interrumpe el proceso."""
        if nombre not in {'colector.lock', 'programador-nube.lock'}:
            raise ValueError('Nombre de bloqueo desconocido')
        with (self.root / nombre).open('a+b') as candado:
            candado.seek(0)
            adquirido = False
            if os.name == 'nt':
                import msvcrt

                def adquirir():
                    msvcrt.locking(candado.fileno(), msvcrt.LK_NBLCK, 1)

                def liberar():
                    candado.seek(0)
                    msvcrt.locking(candado.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                def adquirir():
                    fcntl.flock(candado, fcntl.LOCK_EX | fcntl.LOCK_NB)

                def liberar():
                    fcntl.flock(candado, fcntl.LOCK_UN)

            try:
                adquirir()
                adquirido = True
            except OSError as error:
                if error.errno not in (11, 13, 36):
                    raise
            try:
                yield adquirido
            finally:
                if adquirido:
                    liberar()

    def vencidos(self, tolerancia: timedelta = timedelta(minutes=15), ahora: datetime | None = None) -> int:
        """Cierra intentos abandonados sin fabricar una respuesta HTTP."""
        if tolerancia <= timedelta(0):
            raise ValueError('La tolerancia debe ser positiva')
        ahora = ahora or _ahora()
        limite = _utc(ahora - tolerancia)
        with self._conexion() as conexion:
            conexion.execute('BEGIN IMMEDIATE')
            conexion.execute('''
                INSERT INTO capturas(capture_id, fuente, url, fetched_at_utc, resultado, version_colector)
                SELECT capture_id, fuente, url, ?, 'interrumpido', ? FROM intentos JOIN trabajos USING(trabajo_id)
                WHERE fin_utc IS NULL AND inicio_utc < ?
            ''', (_utc(ahora), VERSION, limite))
            cursor = conexion.execute('''
                UPDATE intentos SET fin_utc=?, reintento_permitido=1,
                    ultimo_error='proceso interrumpido; sin confirmación de respuesta'
                WHERE fin_utc IS NULL AND inicio_utc < ?
            ''', (_utc(ahora), limite))
            return cursor.rowcount

    def tomar(self, trabajo: Trabajo, ahora: datetime | None = None) -> Captura | None:
        _validar_fuente_url(trabajo.fuente, trabajo.url)
        if trabajo.max_intentos < 1:
            raise ValueError('El trabajo requiere al menos un intento')
        inicio = _utc(ahora or _ahora())
        vencimiento = _utc(trabajo.vencimiento)
        if inicio < vencimiento:
            return None
        trabajo_id = trabajo.trabajo_id
        with self._conexion() as conexion:
            conexion.execute('BEGIN IMMEDIATE')
            conexion.execute('INSERT OR IGNORE INTO trabajos VALUES (?, ?, ?, ?, ?)',
                             (trabajo_id, trabajo.fuente, trabajo.url, vencimiento, trabajo.max_intentos))
            previo = conexion.execute('''
                SELECT i.intento, i.reintento_permitido, t.max_intentos
                FROM intentos i JOIN trabajos t USING(trabajo_id)
                WHERE trabajo_id=? ORDER BY i.intento DESC LIMIT 1
            ''', (trabajo_id,)).fetchone()
            if previo and (not previo['reintento_permitido'] or previo['intento'] >= previo['max_intentos']):
                return None
            intento = 1 if previo is None else previo['intento'] + 1
            capture_id = _id(trabajo_id, str(intento))
            conexion.execute('INSERT INTO intentos(capture_id, trabajo_id, intento, inicio_utc) VALUES (?, ?, ?, ?)',
                             (capture_id, trabajo_id, intento, inicio))
            return Captura(trabajo, capture_id, intento)

    def resultado_trabajo(self, trabajo: Trabajo) -> str | None:
        """Distingue una captura terminada de un intento todavía sin evidencia."""
        with self._conexion() as conexion:
            fila = conexion.execute('''
                SELECT resultado FROM intentos LEFT JOIN capturas USING(capture_id)
                WHERE trabajo_id=? ORDER BY intento DESC LIMIT 1
            ''', (trabajo.trabajo_id,)).fetchone()
        return fila['resultado'] if fila else None

    def registrar(self, captura: Captura, *, fetched_at: datetime, resultado: str,
                  estado_http: int | None = None, crudo: bytes | None = None,
                  observaciones: Iterable[Observacion] = (), ultimo_error: str | None = None,
                  reintento_permitido: bool = False, crudo_preexistente: Path | None = None,
                  version_colector: str = VERSION, diario_publicado: bool = False,
                  registrado_at: datetime | None = None) -> bool:
        """Registra evidencia inmutable por intento; confirma las filas en una transacción."""
        if resultado not in ESTADOS or (estado_http is not None and not 100 <= estado_http <= 599):
            raise ValueError('Resultado o estado HTTP inválido')
        observaciones = tuple(observaciones)
        fuente = captura.trabajo.fuente
        if fuente == 'tienda_manual':
            tiene_evidencia = (crudo is not None and estado_http is None and crudo_preexistente is not None
                               and version_colector == VERSION_COTIZACION)
        else:
            tiene_evidencia = crudo is not None and estado_http == 200
        if crudo_preexistente is not None and crudo is None:
            raise ValueError('Una referencia cruda requiere contenido verificado')
        if (bool(observaciones) != (resultado == 'ok')
                or observaciones and not tiene_evidencia
                or reintento_permitido and resultado not in {'fallo', 'interrumpido'}):
            raise ValueError('El resultado no es compatible con la evidencia')
        fetched_at_utc = _utc(fetched_at)
        fin_utc = _utc(registrado_at or fetched_at)
        _validar_fuente_url(fuente, captura.trabajo.url)
        with self._conexion() as conexion:
            conexion.execute('BEGIN IMMEDIATE')
            intento = conexion.execute('''
                SELECT inicio_utc, fin_utc FROM intentos WHERE capture_id=? AND trabajo_id=? AND intento=?
            ''', (captura.capture_id, captura.trabajo.trabajo_id, captura.intento)).fetchone()
            if (intento is None or fin_utc < intento['inicio_utc'] or fetched_at_utc > fin_utc
                    or (crudo_preexistente is None and fetched_at_utc < intento['inicio_utc'])):
                raise ValueError('Intento desconocido o anterior al comienzo del trabajo')
            if intento['fin_utc'] is not None:
                return False
            conexion.execute('INSERT INTO capturas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (captura.capture_id, fuente, captura.trabajo.url, fetched_at_utc,
                              estado_http, resultado, None, None, version_colector))
            for observacion in observaciones:
                self._registrar_precio(conexion, captura, fetched_at, observacion, diario_publicado)
            if crudo is not None:
                sha256 = hashlib.sha256(crudo).hexdigest()
                if crudo_preexistente is not None:
                    archivo = crudo_preexistente.resolve(strict=True)
                    if gzip.decompress(archivo.read_bytes()) != crudo:
                        raise ValueError('La referencia original cambió durante la importación')
                    ruta = Path(os.path.relpath(archivo, self.root)).as_posix()
                else:
                    ruta = self._guardar_crudo(captura, fetched_at_utc, crudo, sha256)
                conexion.execute('UPDATE capturas SET sha256=?, ruta_cruda=? WHERE capture_id=?',
                                 (sha256, ruta, captura.capture_id))
            conexion.execute('''
                UPDATE intentos SET fin_utc=?, reintento_permitido=?, ultimo_error=? WHERE capture_id=?
            ''', (fin_utc, int(reintento_permitido), ultimo_error, captura.capture_id))
        return True

    def _guardar_crudo(self, captura: Captura, fetched_at_utc: str, crudo: bytes, sha256: str) -> str:
        nombre = fetched_at_utc.replace(':', '') + '_' + captura.capture_id + '.gz'
        ruta = self.root / 'raw' / captura.trabajo.fuente / fetched_at_utc[:10] / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if ruta.exists():
            if hashlib.sha256(gzip.decompress(ruta.read_bytes())).hexdigest() != sha256:
                raise ValueError('El crudo del intento ya existe con otro contenido')
            return ruta.relative_to(self.root).as_posix()
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(dir=ruta.parent, suffix='.tmp', delete=False) as archivo:
                temporal = Path(archivo.name)
                archivo.write(gzip.compress(crudo, mtime=0))
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, ruta)
        finally:
            if temporal:
                temporal.unlink(missing_ok=True)
        return ruta.relative_to(self.root).as_posix()

    def _registrar_precio(self, conexion, captura: Captura, fetched_at: datetime, obs: Observacion,
                          diario_publicado: bool) -> None:
        oferta = obs.oferta
        _validar_fuente_url(captura.trabajo.fuente, oferta.enlace)
        if (not all(valor.strip() for valor in (oferta.anuncio_id, oferta.producto_id, oferta.plataforma))
                or not re.fullmatch(r'[A-Z]{3}', obs.moneda)
                or any(isinstance(precio, bool) or not math.isfinite(precio) or precio <= 0
                       for precio in (obs.precio, obs.precio_tachado) if precio is not None)
                or obs.precio is None):
            raise ValueError('Identidad, moneda o precio inválidos')
        if obs.precision_temporal == 'dia':
            if obs.observed_at is not None or obs.fecha_precio is None:
                raise ValueError('Un precio diario requiere fecha y conserva hora desconocida')
            observed_at = None
            dia = obs.fecha_precio.isoformat()
        elif obs.precision_temporal == 'instante':
            observacion = obs.observed_at or fetched_at
            observed_at = _utc(observacion)
            if observed_at > _utc(fetched_at):
                raise ValueError('La observación es posterior a la captura')
            dia = observacion.astimezone(CDMX).date().isoformat()
        else:
            raise ValueError('Precisión temporal desconocida')
        offer_id = oferta.identificador(captura.trabajo.fuente)
        conexion.execute('INSERT OR IGNORE INTO ofertas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (offer_id, captura.trabajo.fuente, oferta.anuncio_id, oferta.producto_id,
                          oferta.variante, oferta.plataforma, oferta.vendedor, oferta.condicion, oferta.enlace))
        condiciones = json.dumps(obs.condiciones, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if diario_publicado:
            if obs.precision_temporal != 'dia' or dia > fetched_at.astimezone(CDMX).date().isoformat():
                raise ValueError('Un historial publicado requiere días observados sin horas ni fechas futuras')
            conexion.execute('INSERT INTO observaciones_diarias_fuente VALUES (?, ?, ?, ?, ?, ?)',
                             (captura.capture_id, offer_id, dia, obs.precio, obs.moneda, condiciones))
            return
        conexion.execute('INSERT INTO observaciones_intradia VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (captura.capture_id, offer_id, observed_at,
                          _utc(obs.source_updated_at) if obs.source_updated_at else None,
                          obs.precision_temporal, obs.fecha_precio.isoformat() if obs.fecha_precio else None,
                          dia, obs.precio, obs.moneda, obs.precio_tachado, obs.disponibilidad,
                          condiciones, oferta.enlace))

    def estado(self) -> dict:
        with self._conexion() as conexion:
            fuentes = conexion.execute('''
                SELECT fuente, resultado, COUNT(*) AS capturas, MAX(fetched_at_utc) AS ultima_captura
                FROM capturas GROUP BY fuente, resultado ORDER BY fuente, resultado
            ''').fetchall()
            trabajos = conexion.execute('SELECT COUNT(*) FROM trabajos').fetchone()[0]
            intentos = conexion.execute('SELECT COUNT(*) FROM intentos').fetchone()[0]
            precios = conexion.execute('SELECT COUNT(*) FROM observaciones_intradia').fetchone()[0]
            diarios_fuente = conexion.execute('SELECT COUNT(*) FROM observaciones_diarias_fuente').fetchone()[0]
        return dict(version=VERSION, trabajos=trabajos, intentos=intentos, observaciones=precios,
                    observaciones_diarias_fuente=diarios_fuente, fuentes=[dict(fuente) for fuente in fuentes])

    def ofertas(self, producto_id: str, limite: int = 50) -> list[dict]:
        """Devuelve la comprobación más reciente por oferta y moneda."""
        with self._conexion() as conexion:
            filas = conexion.execute('''
                WITH comprobaciones AS (
                    SELECT o.offer_id, o.fuente, o.anuncio_id, o.producto_id, o.variante, o.plataforma,
                           o.vendedor, o.condicion, n.enlace, n.capture_id, n.observed_at, n.source_updated_at,
                           n.precision_temporal, n.fecha_precio, n.fecha_cdmx, n.precio, n.moneda,
                           n.precio_tachado, n.disponibilidad, n.condiciones_json, c.fetched_at_utc,
                           ROW_NUMBER() OVER (PARTITION BY o.offer_id, n.moneda
                               ORDER BY n.fecha_cdmx DESC, n.observed_at DESC, c.fetched_at_utc DESC,
                                        n.capture_id DESC) AS posicion
                    FROM ofertas o JOIN observaciones_intradia n USING(offer_id)
                    JOIN capturas c USING(capture_id) WHERE o.producto_id=?
                )
                SELECT * FROM comprobaciones WHERE posicion=1
                ORDER BY fecha_cdmx DESC, precio, offer_id LIMIT ?
            ''', (producto_id, max(0, limite))).fetchall()
        resultado = []
        for fila in filas:
            oferta = dict(fila)
            oferta.pop('posicion')
            oferta['condiciones'] = json.loads(oferta.pop('condiciones_json'))
            resultado.append(oferta)
        return resultado

    def precios_diarios(self, producto_id: str, limite: int = 400) -> list[dict]:
        """Cada fila representa una fecha, una oferta y una moneda en CDMX."""
        with self._conexion() as conexion:
            filas = conexion.execute('''
                WITH ordenadas AS (
                    SELECT n.*, ROW_NUMBER() OVER fecha AS ultimo,
                           ROW_NUMBER() OVER precios AS posicion,
                           COUNT(*) OVER (PARTITION BY n.offer_id, n.moneda, n.fecha_cdmx) AS comprobaciones
                    FROM observaciones_intradia n JOIN ofertas o USING(offer_id)
                    JOIN capturas c USING(capture_id) WHERE o.producto_id=?
                    WINDOW fecha AS (PARTITION BY n.offer_id, n.moneda, n.fecha_cdmx
                             ORDER BY n.observed_at DESC, c.fetched_at_utc DESC, n.capture_id DESC),
                           precios AS (PARTITION BY n.offer_id, n.moneda, n.fecha_cdmx
                             ORDER BY n.precio, n.capture_id)
                )
                SELECT offer_id, fecha_cdmx AS fecha, moneda, MIN(precio) AS minimo,
                       AVG(CASE WHEN posicion IN ((comprobaciones+1)/2, (comprobaciones+2)/2)
                                THEN precio END) AS mediana,
                       MAX(precio) AS maximo, MAX(CASE WHEN ultimo=1 THEN precio END) AS ultimo,
                       COUNT(*) AS comprobaciones
                FROM ordenadas GROUP BY offer_id, fecha_cdmx, moneda
                ORDER BY fecha_cdmx DESC, offer_id, moneda LIMIT ?
            ''', (producto_id, max(0, limite))).fetchall()
        return [dict(fila) for fila in filas]
