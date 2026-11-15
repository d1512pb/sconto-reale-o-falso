"""Registra cotizaciones online autorizadas sin realizar solicitudes a minoristas."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sconto.fuentes.tiendas import validar_url
from sconto.intraday import RAIZ_INTRADIA, VERSION_COTIZACION, IntradayStore, Observacion, Oferta, Trabajo


FUENTE = 'tienda_manual'
ESTADOS = {'disponible', 'agotado', 'desconocido'}
TIPOS_EVIDENCIA = {'cotizacion_del_vendedor', 'archivo_autorizado'}
CONDICIONES = {'nuevo', 'reacondicionado', 'usado', 'desconocido'}
PERMISOS = {'interno', 'publicacion'}
CONTEXTOS_COSTO = {'envio_cdmx', 'envio_estado_de_mexico', 'retiro_sucursal', 'entrega_digital'}


def _texto(fila, clave, limite=120, opcional=False):
    valor = fila.get(clave)
    if valor is None and opcional:
        return None
    if not isinstance(valor, str) or not valor.strip() or len(valor) > limite or re.search(r'[\x00-\x1f]', valor):
        raise ValueError(f'{clave} requiere texto no vacío de hasta {limite} caracteres')
    return ' '.join(valor.split())


def _opcion(fila, clave, valores):
    valor = _texto(fila, clave)
    if valor not in valores:
        raise ValueError(f'{clave} fuera del vocabulario permitido')
    return valor


def _hora(fila, clave, opcional=False):
    texto = _texto(fila, clave, opcional=opcional)
    if texto is None:
        return None
    hora = datetime.fromisoformat(texto)
    if hora.utcoffset() is None or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', texto):
        raise ValueError(f'{clave} requiere ISO 8601 con segundos y huso explícito')
    return hora.astimezone(timezone.utc)


def _importe(fila, clave, opcional=False, cero=False):
    valor = fila.get(clave)
    if valor is None and opcional:
        return None
    try:
        importe = Decimal(str(valor))
    except InvalidOperation as error:
        raise ValueError(f'{clave} debe ser un importe MXN válido') from error
    if (not importe.is_finite() or importe < (0 if cero else Decimal('0.01'))
            or importe > 10000000 or importe != importe.quantize(Decimal('0.01'))):
        raise ValueError(f'{clave} debe ser un importe MXN válido')
    return importe


def _url(fila, tienda):
    partes = urlsplit(validar_url(_texto(fila, 'url', 500), tienda))
    # El resto de la consulta puede llevar una sesión o datos de ubicación.
    parametros = parse_qsl(partes.query, keep_blank_values=True)
    if parametros and (tienda != 'liverpool' or len(parametros) != 1
                       or parametros[0][0] != 'skuid' or not parametros[0][1].isdigit()):
        raise ValueError('Usa la URL de ficha sin sesión ni ubicación')
    return urlunsplit((partes.scheme, partes.hostname, partes.path, urlencode(parametros), ''))


def normalizar(fila, ahora):
    tienda = _opcion(fila, 'tienda', {'liverpool', 'sears'})
    url = _url(fila, tienda)
    modelo = _texto(fila, 'variante', opcional=True)
    sku = _texto(fila, 'sku')
    vendedor = _texto(fila, 'vendedor', opcional=True)
    condicion = _opcion(fila, 'condicion', CONDICIONES)
    disponibilidad = _opcion(fila, 'disponibilidad', ESTADOS)
    producto = _texto(fila, 'producto_id')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', producto):
        raise ValueError('producto_id requiere un identificador del catálogo de Sconto')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,79}', sku):
        raise ValueError('sku requiere un identificador de la ficha comercial')
    if tienda == 'liverpool' and (seleccion := dict(parse_qsl(urlsplit(url).query)).get('skuid')) and seleccion != sku:
        raise ValueError('El SKU seleccionado en la URL difiere del SKU observado')
    comprobada = fila.get('identidad_verificada', False)
    if not isinstance(comprobada, bool) or comprobada and (not modelo or not vendedor or condicion == 'desconocido'):
        raise ValueError('La identidad verificada necesita variante, vendedor y condición explícitos')
    visto = _hora(fila, 'observado_utc')
    actualizado = _hora(fila, 'actualizado_por_fuente_utc', opcional=True)
    if visto > ahora or actualizado and actualizado > visto:
        raise ValueError('La evidencia contiene una hora posterior a su observación o importación')
    precio = _importe(fila, 'precio_publicado_mxn')
    tachado = _importe(fila, 'precio_tachado_mxn', opcional=True)
    envio = _importe(fila, 'envio_mxn', opcional=True, cero=True)
    cargos = _importe(fila, 'otros_cargos_mxn', opcional=True, cero=True)
    total = _importe(fila, 'costo_total_mxn', opcional=True)
    contexto = _texto(fila, 'contexto_costo', limite=180, opcional=True)
    if contexto is not None and contexto not in CONTEXTOS_COSTO:
        raise ValueError('contexto_costo identifica una zona general o retiro, sin domicilio')
    promocion = _texto(fila, 'promocion_condicionada', limite=220, opcional=True)
    if total is not None and (envio is None or cargos is None or total != precio + envio + cargos or not contexto):
        raise ValueError('El costo total necesita precio, envío, cargos y contexto de entrega conciliados')
    permiso = _opcion(fila, 'alcance_permiso', PERMISOS)
    permiso_ref = _texto(fila, 'referencia_permiso', limite=140)
    documento = _opcion(fila, 'tipo_evidencia', TIPOS_EVIDENCIA)
    condiciones = dict(canal='online', metodo='cotizacion_documentada', publicable=permiso == 'publicacion',
                       identidad_verificada=comprobada, cargos_confirmados=total is not None,
                       costo_total_confirmado=float(total) if total is not None else None,
                       contexto_costo=contexto, promocion_condicionada=promocion)
    anuncio = Oferta(f'{tienda}:{sku}', producto, 'Sears' if tienda == 'sears' else 'Liverpool', url,
                    variante=modelo, vendedor=vendedor, condicion=condicion)
    observado = Observacion(anuncio, float(precio), 'MXN', observed_at=visto, source_updated_at=actualizado,
                           precio_tachado=float(tachado) if tachado is not None else None,
                           disponibilidad=disponibilidad, condiciones=condiciones)
    contexto_privado = dict(referencia_permiso=permiso_ref, tipo_evidencia=documento,
                            envio_mxn=str(envio) if envio is not None else None,
                            otros_cargos_mxn=str(cargos) if cargos is not None else None)
    return observado, contexto_privado


def importar(fila, evidencia, store, ahora=None):
    ahora = ahora or datetime.now(timezone.utc)
    observacion, contexto = normalizar(fila, ahora)
    # Se conserva la cita estructurada y la huella del soporte; el PDF o captura del tercero queda en custodia privada.
    with Path(evidencia).open('rb') as soporte:
        hash_evidencia = hashlib.file_digest(soporte, 'sha256').hexdigest()
    oferta = observacion.oferta
    crudo = json.dumps(dict(esquema=VERSION_COTIZACION, sha256_documento=hash_evidencia,
                           oferta=oferta.__dict__, precio_mxn=observacion.precio,
                           observado_utc=observacion.observed_at.isoformat(),
                           actualizado_por_fuente_utc=(observacion.source_updated_at.isoformat()
                                                      if observacion.source_updated_at else None),
                           precio_tachado_mxn=observacion.precio_tachado, disponibilidad=observacion.disponibilidad,
                           condiciones=observacion.condiciones, **contexto),
                       ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')
    sha = hashlib.sha256(crudo).hexdigest()
    ruta = store.root / 'raw' / FUENTE / observacion.observed_at.date().isoformat() / f'{sha}.gz'
    with store.exclusividad_colector() as permiso:
        if not permiso:
            raise RuntimeError('Otra importación usa el almacén')
        store.vencidos(ahora=ahora)
        tarea = Trabajo(FUENTE, oferta.enlace, observacion.observed_at, max_intentos=2)
        captura = store.tomar(tarea, ahora=ahora)
        if captura is None:
            with store._conexion() as conexion:
                previo = conexion.execute('''SELECT c.sha256 FROM capturas c JOIN intentos i USING(capture_id)
                    WHERE i.trabajo_id=? AND c.resultado='ok' ''', (tarea.trabajo_id,)).fetchone()
            if previo is not None and previo['sha256'] == sha:
                return {'nueva': False, 'sha256': sha, 'publicable': observacion.condiciones['publicable']}
            raise ValueError('Ya existe una evidencia diferente o incompleta para esta hora y anuncio')
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if not ruta.exists():
            temporal = ruta.with_suffix('.tmp')
            temporal.write_bytes(gzip.compress(crudo, mtime=0))
            temporal.replace(ruta)
        store.registrar(captura, fetched_at=observacion.observed_at, registrado_at=ahora,
                        resultado='ok', crudo=crudo, observaciones=[observacion],
                        crudo_preexistente=ruta, version_colector=VERSION_COTIZACION)
        return {'nueva': True, 'capture_id': captura.capture_id, 'sha256': sha,
                'publicable': observacion.condiciones['publicable']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cotizacion', type=Path, help='Archivo JSON documentado en reports/acceso_online_v2.md')
    parser.add_argument('--evidencia', required=True, type=Path, help='Soporte privado sin credenciales ni datos de pago')
    parser.add_argument('--almacen', type=Path, default=RAIZ_INTRADIA)
    args = parser.parse_args(argv)
    resultado = importar(json.loads(args.cotizacion.read_bytes()), args.evidencia, IntradayStore(args.almacen))
    print(json.dumps(resultado))


if __name__ == '__main__':
    main()
