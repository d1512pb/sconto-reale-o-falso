"""Corte operativo por tráfico del servidor. No mide la factura de Fly.io."""
from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from uuid import UUID


ARCHIVO = 'presupuesto-fly-v2.json'
LIMITE_SALIDA_BYTES = 5_000_000_000
RUTA_RED = Path('/proc/net/dev')
RUTA_ARRANQUE = Path('/proc/sys/kernel/random/boot_id')


@dataclass(frozen=True)
class Consumo:
    mes_utc: str
    arranque: str | None
    ultimo_tx: int | None
    bytes_mes: int
    detenido: bool


def _ahora():
    return datetime.now(timezone.utc)


def _arranque(texto):
    canonico = str(UUID(texto))
    if texto != canonico:
        raise ValueError('Identificador de arranque inválido')
    return canonico


def _tx(texto):
    cabecera, columnas, *filas = texto.splitlines()
    if not cabecera.startswith('Inter-|') or 'Transmit' not in cabecera or not columnas.lstrip().startswith('face |'):
        raise ValueError('Formato de contador inválido')
    interfaces = {}
    for fila in filas:
        nombre, separador, datos = fila.partition(':')
        nombre = nombre.strip()
        campos = datos.split()
        if (not separador or not nombre or nombre in interfaces or len(campos) != 16
                or any(not re.fullmatch(r'[0-9]+', valor) for valor in campos)):
            raise ValueError('Datos de contador inválidos')
        interfaces[nombre] = int(campos[8])
    interfaces.pop('lo', None)
    if not interfaces:
        raise ValueError('Sin una interfaz contabilizable')
    return sum(interfaces.values())


def _sin_claves_duplicadas(elementos):
    resultado = dict(elementos)
    if len(resultado) != len(elementos):
        raise ValueError('Registro de consumo inválido')
    return resultado


def _leer(ruta, mes):
    if ruta.is_symlink():
        raise ValueError('Registro de consumo inválido')
    try:
        texto = ruta.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    if len(texto) > 4096:
        raise ValueError('Registro de consumo inválido')
    datos = json.loads(texto, object_pairs_hook=_sin_claves_duplicadas)
    estado = Consumo(**datos)
    if (not re.fullmatch(r'[0-9]{4}-[0-9]{2}', estado.mes_utc)
            or date.fromisoformat(estado.mes_utc + '-01').isoformat()[:7] != estado.mes_utc
            or estado.mes_utc > mes or type(estado.bytes_mes) is not int or estado.bytes_mes < 0
            or type(estado.detenido) is not bool):
        raise ValueError('Registro de consumo inválido')
    if estado.arranque is None:
        if estado.ultimo_tx is not None or not estado.detenido:
            raise ValueError('Registro de consumo inválido')
    elif (_arranque(estado.arranque) != estado.arranque
          or type(estado.ultimo_tx) is not int or estado.ultimo_tx < 0):
        raise ValueError('Registro de consumo inválido')
    return estado


def _guardar(ruta, estado):
    temporal = None
    try:
        with NamedTemporaryFile(dir=ruta.parent, prefix='.presupuesto-', delete=False,
                                mode='w', encoding='utf-8') as archivo:
            temporal = Path(archivo.name)
            json.dump(asdict(estado), archivo, separators=(',', ':'))
            archivo.flush()
            os.fsync(archivo.fileno())
        temporal.replace(ruta)
        if os.name != 'nt':
            directorio = os.open(ruta.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directorio)
            finally:
                os.close(directorio)
    finally:
        if temporal:
            with suppress(OSError):
                temporal.unlink(missing_ok=True)


class PresupuestoFly:
    def __init__(self, almacen: Path, *, red=RUTA_RED, arranque=RUTA_ARRANQUE, reloj=_ahora):
        self.ruta = Path(almacen) / ARCHIVO
        self.red = Path(red)
        self.arranque = Path(arranque)
        self.reloj = reloj

    def continuar(self) -> bool:
        """Devuelve False ante un corte mensual, medición inválida o persistencia fallida."""
        try:
            ahora = self.reloj()
            if ahora.utcoffset() is None:
                return False
            mes = ahora.astimezone(timezone.utc).date().isoformat()[:7]
            previo = _leer(self.ruta, mes)
            mismo_mes = previo is not None and previo.mes_utc == mes
            if mismo_mes and previo.detenido:
                return False
            try:
                arranque = _arranque(self.arranque.read_text(encoding='ascii').strip())
                tx = _tx(self.red.read_text(encoding='ascii'))
                anterior = previo.ultimo_tx if previo is not None and previo.arranque == arranque else 0
                if tx < anterior:
                    raise ValueError('Disminuyó el contador en el mismo arranque')
            except (OSError, TypeError, ValueError):
                bloqueo = (Consumo(mes, previo.arranque, previo.ultimo_tx, previo.bytes_mes, True)
                           if mismo_mes else Consumo(mes, None, None, 0, True))
                _guardar(self.ruta, bloqueo)
                return False
            acumulado = (previo.bytes_mes if mismo_mes else 0) + tx - anterior
            estado = Consumo(mes, arranque, tx, acumulado, acumulado >= LIMITE_SALIDA_BYTES)
            if estado != previo:
                _guardar(self.ruta, estado)
            return not estado.detenido
        except (OSError, AttributeError, TypeError, ValueError):
            return False
