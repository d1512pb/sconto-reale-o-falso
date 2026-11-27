"""Respalda evidencias Sconto con age y las conserva en almacenamiento S3 privado."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import file_digest
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_STORED, ZipFile

from sconto.intraday import RAIZ_INTRADIA
from sconto.respaldo_v2 import BASE, respaldar, restaurar

FORMATO = 'sconto-respaldo-nube-v1'
PREFIJO = 'sconto-v2/v1/'
PREFIJO_QQP = 'sconto-v2/qqp-v1/'
PAQUETE_BASE = 'intradia.zip'
CATALOGO = 'catalogo.sqlite'
MAX_BYTES = 64 * 1024 * 1024
MAX_QQP_ORIGINAL = 250 * 1024 * 1024
MAX_QQP_CIFRADO = 251 * 1024 * 1024
CUOTA_QQP = 1024 * 1024 * 1024
ENDPOINT = 'https://t3.storage.dev'
CLAVE_OBJETO = re.compile(PREFIJO + r'\d{4}-\d{2}-\d{2}T\d{6}\.\d{6}Z-([a-f0-9]{64})\.age')
FORMATO_QQP = 'sconto-qqp-rar-v1'
CARPETA_QQP = 'qqp/publicaciones'
NOMBRE_QQP = re.compile(r'QQP_(\d{4})\.([a-f0-9]{64})\.rar')
RUTAS_ADJUNTAS = (
    re.compile(r'profeco/raw/\d{4}-\d{2}-\d{2}/[A-Za-z0-9_.-]+\.(?:gz|json|jsonl)'),
    re.compile(r'profeco/operacion/ejecuciones/[A-Za-z0-9_.-]+\.json'),
    re.compile(r'profeco/operacion/ALERTA\.md'),
    re.compile(r'qqp/(?:estado|referencia)\.json'),
    re.compile(CARPETA_QQP + r'/(?:estado\.json|QQP_\d{4}\.[a-f0-9]{64}\.rar(?:\.json)?)'),
)


def _sha(ruta):
    with ruta.open('rb') as f:
        return file_digest(f, 'sha256').hexdigest()


def _adjunto(nombre):
    return any(patron.fullmatch(nombre) for patron in RUTAS_ADJUNTAS)


def _verificar_catalogo(ruta):
    with closing(sqlite3.connect(ruta.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise ValueError('El catálogo SQLite no pasó la comprobación de integridad')


def _anexos(origen, catalogo):
    rutas = {}
    for globo in ('profeco/raw/*/*', 'profeco/operacion/ejecuciones/*', 'profeco/operacion/ALERTA.md',
                  'qqp/estado.json', 'qqp/referencia.json', CARPETA_QQP + '/*.json'):
        for ruta in origen.glob(globo):
            nombre = ruta.relative_to(origen).as_posix()
            if ruta.is_file() and _adjunto(nombre):
                if ruta.is_symlink() or not ruta.resolve().is_relative_to(origen):
                    raise ValueError('Un adjunto de operación apunta fuera del volumen')
                rutas[nombre] = ruta
    if catalogo is not None:
        catalogo = Path(catalogo).resolve(strict=True)
        _verificar_catalogo(catalogo)
        rutas[CATALOGO] = catalogo
    return rutas


def _tamano(ruta, limite=MAX_BYTES):
    tamano = ruta.stat().st_size
    if not 0 < tamano <= limite:
        raise ValueError('El respaldo excede su límite operativo o está vacío')
    return tamano


def _age(accion, entrada, salida):
    try:
        subprocess.run(['age', *accion, '-o', str(salida), str(entrada)], check=True,
                       timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as error:
        raise ValueError('Falta el ejecutable age en PATH') from error
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise ValueError('age no pudo completar el cifrado o verificar la recuperación') from error


def _aceptados_qqp(origen):
    carpeta = origen / CARPETA_QQP
    rar = {p.name for p in carpeta.glob('QQP_*.rar') if NOMBRE_QQP.fullmatch(p.name)}
    recibos = {p.stem for p in carpeta.glob('QQP_*.rar.json') if NOMBRE_QQP.fullmatch(p.stem)}
    if rar != recibos:
        raise ValueError('Los RAR aceptados y sus comprobantes por SHA-256 deben estar completos')
    candidatos = {}
    for nombre in sorted(rar):
        archivo = carpeta / nombre
        recibo = carpeta / (nombre + '.json')
        if any(p.is_symlink() or not p.resolve().is_relative_to(origen) for p in (archivo, recibo)):
            raise ValueError('Un RAR de QQP apunta fuera del volumen')
        metadata = json.loads(recibo.read_bytes())
        sha = NOMBRE_QQP.fullmatch(nombre)[2]
        if (metadata.get('estado') != 'candidato_validado' or metadata.get('archivo') != nombre
                or metadata.get('sha256') != sha or not isinstance(metadata.get('miembros_csv'), int)
                or not 1 <= metadata['miembros_csv'] <= 30
                or metadata.get('bytes_descargados') != _tamano(archivo, MAX_QQP_ORIGINAL)
                or _sha(archivo) != sha):
            raise ValueError('RAR de QQP discordante con la validación del recolector')
        candidatos[nombre] = archivo
    return candidatos


def crear(origen, destino, destinatario, *, catalogo=None, raices_crudas=(), qqp_externo=None):
    origen, destino = Path(origen).resolve(strict=True), Path(destino).resolve()
    if not re.fullmatch(r'age1[0-9a-z]{58}', destinatario):
        raise ValueError('Se requiere un destinatario público age X25519 válido')
    if destino.exists():
        raise FileExistsError(destino)
    aceptados = _aceptados_qqp(origen)
    if qqp_externo is not None and set(qqp_externo) != set(aceptados):
        raise ValueError('El conjunto QQP cifrado por separado difiere del volumen')
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino.parent) as temp:
        trabajo = Path(temp)
        base = trabajo / PAQUETE_BASE
        respaldar(origen, base, raices_crudas)
        miembros = {PAQUETE_BASE: base, **_anexos(origen, catalogo)}
        if qqp_externo is None:
            miembros.update({f'{CARPETA_QQP}/{n}': p for n, p in aceptados.items()})
        if sum(ruta.stat().st_size for ruta in miembros.values()) > MAX_BYTES:
            raise ValueError('El conjunto de respaldo supera el límite operativo de 64 MiB')
        metadatos = {n: dict(bytes=r.stat().st_size, sha256=_sha(r)) for n, r in miembros.items()}
        archivo = trabajo / 'respaldo.zip'
        with ZipFile(archivo, 'x', compression=ZIP_STORED) as z:
            for nombre, ruta in miembros.items():
                z.write(ruta, nombre)
                if ruta.stat().st_size != metadatos[nombre]['bytes'] or _sha(ruta) != metadatos[nombre]['sha256']:
                    raise ValueError('Los datos cambiaron durante el respaldo, reintenta con el recolector en pausa')
            manifest = dict(formato=FORMATO, archivos=metadatos, qqp_externo=qqp_externo or [])
            z.writestr('manifest.json', json.dumps(manifest, separators=(',', ':')))
        cifrado = trabajo / 'respaldo.age'
        _age(['--encrypt', '--recipient', destinatario], archivo, cifrado)
        longitud, sha = _tamano(cifrado), _sha(cifrado)
        if os.name == 'nt':
            cifrado.rename(destino)
        else:
            destino.hardlink_to(cifrado)
    return dict(bytes=longitud, sha256=sha, archivos=len(miembros))


def abrir(cifrado, destino, identidad, *, sha256, cargar_qqp=None):
    cifrado, destino = Path(cifrado).resolve(strict=True), Path(destino).resolve()
    if destino.exists():
        raise FileExistsError(destino)
    _tamano(cifrado)
    if _sha(cifrado) != sha256:
        raise ValueError('No coincide el SHA-256 del objeto cifrado')
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino.parent) as temp:
        trabajo = Path(temp)
        archivo = trabajo / 'respaldo.zip'
        _age(['--decrypt', '--identity', str(Path(identidad).resolve(strict=True))], cifrado, archivo)
        _tamano(archivo)
        staging = trabajo / 'restaurada'
        with ZipFile(archivo) as z:
            cabecera = z.getinfo('manifest.json')
            if cabecera.file_size > 2 * 1024 * 1024:
                raise ValueError('Manifiesto de respaldo demasiado grande')
            manifiesto = json.loads(z.read(cabecera))
            archivos = manifiesto['archivos']
            qqp_externo = manifiesto.get('qqp_externo', [])
            if (manifiesto['formato'] != FORMATO or PAQUETE_BASE not in archivos or
                    sorted(z.namelist()) != sorted(['manifest.json', *archivos]) or
                    any(n not in (PAQUETE_BASE, CATALOGO) and not _adjunto(n) for n in archivos)):
                raise ValueError('Miembros inesperados en el respaldo')
            if (not isinstance(qqp_externo, list) or
                    any(not isinstance(n, str) or not NOMBRE_QQP.fullmatch(n)
                        or f'{CARPETA_QQP}/{n}.json' not in archivos for n in qqp_externo)
                    or len(qqp_externo) != len(set(qqp_externo))):
                raise ValueError('Referencias externas QQP inválidas')
            if sum(z.getinfo(n).file_size for n in archivos) > MAX_BYTES:
                raise ValueError('El respaldo descomprimido supera el límite operativo')
            for nombre, metadata in archivos.items():
                if z.getinfo(nombre).file_size != metadata['bytes']:
                    raise ValueError(f'Tamaño inesperado en {nombre}')
                if nombre == PAQUETE_BASE:
                    ruta = trabajo / PAQUETE_BASE
                else:
                    ruta = trabajo / 'adjuntos' / nombre
                ruta.parent.mkdir(parents=True, exist_ok=True)
                with z.open(nombre) as entrada, ruta.open('xb') as salida:
                    shutil.copyfileobj(entrada, salida)
                if _sha(ruta) != metadata['sha256']:
                    raise ValueError(f'Hash inválido en {nombre}')
        with ZipFile(trabajo / PAQUETE_BASE) as z_base:
            if any(i.compress_type != ZIP_STORED for i in z_base.infolist()):
                raise ValueError('Formato de compresión de la base no admitido')
        restaurar(trabajo / PAQUETE_BASE, staging)
        for nombre in set(archivos) - {PAQUETE_BASE}:
            origen = trabajo / 'adjuntos' / nombre
            if nombre == CATALOGO:
                _verificar_catalogo(origen)
            ruta = staging / nombre
            ruta.parent.mkdir(parents=True, exist_ok=True)
            origen.rename(ruta)
        if qqp_externo:
            if cargar_qqp is None:
                raise ValueError('Esta versión requiere recuperar sus objetos QQP externos')
            for nombre in qqp_externo:
                cargar_qqp(nombre, staging / CARPETA_QQP / nombre)
        qqp_recuperados = len(_aceptados_qqp(staging))
        if destino.exists():
            raise FileExistsError(destino)
        staging.rename(destino)
    return dict(archivos=len(archivos), catalogo=CATALOGO in archivos, sha256=sha256,
                archivos_qqp=qqp_recuperados)


def _sha_clave(clave):
    verificada = CLAVE_OBJETO.fullmatch(clave)
    if not verificada:
        raise ValueError('Clave de respaldo inválida')
    return verificada[1]


def _metadatos_s3(respuesta, sha=None, *, formato=FORMATO, limite=MAX_BYTES):
    largo = respuesta.get('ContentLength', 0)
    metadata = respuesta.get('Metadata', {})
    digest = metadata.get('sha256', '')
    if (not 0 < largo <= limite or metadata.get('formato') != formato
            or not re.fullmatch(r'[a-f0-9]{64}', digest) or (sha and sha != digest)):
        raise ValueError('El tamaño o la metadata S3 del objeto no coinciden con el respaldo')
    return largo, digest


def _subir(s3, bucket, clave, cifrado, formato, limite):
    tamano, sha = _tamano(cifrado, limite), _sha(cifrado)
    with cifrado.open('rb') as cuerpo:
        s3.put_object(Bucket=bucket, Key=clave, Body=cuerpo, ContentLength=tamano, IfNoneMatch='*',
                      ContentType='application/octet-stream', Metadata={'sha256': sha, 'formato': formato})
    respuesta = s3.head_object(Bucket=bucket, Key=clave)
    largo, _ = _metadatos_s3(respuesta, sha, formato=formato, limite=limite)
    if largo != tamano:
        raise ValueError('El respaldo enviado no coincide con el recibido por S3')
    return tamano, sha


def enviar(cifrado, bucket, s3):
    sha = _sha(cifrado)
    clave = PREFIJO + datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%S.%fZ') + '-' + sha + '.age'
    tamano, sha = _subir(s3, bucket, clave, cifrado, FORMATO, MAX_BYTES)
    return dict(clave=clave, sha256=sha, bytes=tamano, estado='objeto_confirmado')


def _descargar(s3, bucket, clave, cifrado, *, sha=None, formato=FORMATO, limite=MAX_BYTES):
    respuesta = s3.get_object(Bucket=bucket, Key=clave)
    with closing(respuesta['Body']) as cuerpo:
        largo, digest = _metadatos_s3(respuesta, sha, formato=formato, limite=limite)
        escrito = 0
        with cifrado.open('xb') as archivo:
            for chunk in cuerpo.iter_chunks(chunk_size=1024 * 1024):
                escrito += len(chunk)
                if escrito > largo:
                    raise ValueError('El objeto recibido supera el tamaño declarado')
                archivo.write(chunk)
    if escrito != largo or _sha(cifrado) != digest:
        raise ValueError('El objeto recibido está incompleto o alterado')


def _objetos(bucket, s3, prefijo):
    paginas = s3.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefijo)
    return (obj for obj in paginas.search('Contents[]') if obj)


def _clave_qqp(nombre):
    return PREFIJO_QQP + NOMBRE_QQP.fullmatch(nombre)[2] + '.age'


def enviar_qqp(origen, destinatario, bucket, s3):
    candidatos = _aceptados_qqp(Path(origen).resolve(strict=True))
    if not candidatos:
        return []
    existentes = {obj['Key']: obj['Size'] for obj in _objetos(bucket, s3, PREFIJO_QQP)}
    ocupacion = sum(existentes.values())
    for nombre, ruta in candidatos.items():
        clave = _clave_qqp(nombre)
        if clave in existentes:
            respuesta = s3.head_object(Bucket=bucket, Key=clave)
            if _metadatos_s3(respuesta, formato=FORMATO_QQP, limite=MAX_QQP_CIFRADO)[0] != existentes[clave]:
                raise ValueError('La versión QQP remota cambió')
            continue
        with TemporaryDirectory() as temp:
            cifrado = Path(temp) / 'qqp.age'
            _age(['--encrypt', '--recipient', destinatario], ruta, cifrado)
            tamano = _tamano(cifrado, MAX_QQP_CIFRADO)
            if ocupacion + tamano > CUOTA_QQP:
                raise ValueError('La cuota externa de 1 GiB para los RAR QQP se agotó')
            _subir(s3, bucket, clave, cifrado, FORMATO_QQP, MAX_QQP_CIFRADO)
            existentes[clave] = tamano
            ocupacion += tamano
    return sorted(candidatos)


def recuperar(clave, destino, identidad, bucket, s3):
    sha = _sha_clave(clave)
    with TemporaryDirectory() as temp:
        trabajo = Path(temp)
        cifrado = trabajo / 'respaldo.age'
        _descargar(s3, bucket, clave, cifrado, sha=sha)

        def recuperar_qqp(nombre, salida):
            archivo_qqp = trabajo / 'qqp.age'
            _descargar(s3, bucket, _clave_qqp(nombre), archivo_qqp, formato=FORMATO_QQP, limite=MAX_QQP_CIFRADO)
            _age(['--decrypt', '--identity', str(Path(identidad).resolve(strict=True))], archivo_qqp, salida)
            archivo_qqp.unlink()

        return abrir(cifrado, destino, identidad, sha256=sha, cargar_qqp=recuperar_qqp)


def listar(bucket, s3):
    return sorted((obj['Key'] for obj in _objetos(bucket, s3, PREFIJO) if CLAVE_OBJETO.fullmatch(obj['Key'])),
                  reverse=True)


def _conectar_s3():
    import boto3
    from botocore.config import Config

    bucket = os.environ.get('SCONTO_BACKUP_BUCKET', '')
    acceso = os.environ.get('SCONTO_BACKUP_ACCESS_KEY_ID')
    secreto = os.environ.get('SCONTO_BACKUP_SECRET_ACCESS_KEY')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', bucket) or not acceso or not secreto:
        raise ValueError('Configura el bucket privado y sus dos credenciales de alcance limitado')
    config = Config(retries={'total_max_attempts': 2, 'mode': 'standard'},
                    connect_timeout=5, read_timeout=45, max_pool_connections=2,
                    request_checksum_calculation='when_required',
                    response_checksum_validation='when_required', s3={'addressing_style': 'path'})
    cliente = boto3.client('s3', endpoint_url=ENDPOINT, region_name='auto', config=config,
                          aws_access_key_id=acceso, aws_secret_access_key=secreto)
    return bucket, cliente


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operacion', required=True)
    prepara = sub.add_parser('crear')
    prepara.add_argument('archivo', type=Path)
    publica = sub.add_parser('enviar')
    prepara.add_argument('--origen', type=Path, default=RAIZ_INTRADIA)
    publica.add_argument('--origen', type=Path, required=True)
    for operacion in (prepara, publica):
        operacion.add_argument('--catalogo', type=Path)
        operacion.add_argument('--raiz-crudos', type=Path, action='append', default=[])
    local = sub.add_parser('abrir')
    local.add_argument('archivo', type=Path)
    local.add_argument('--sha256', required=True)
    remota = sub.add_parser('recuperar')
    remota.add_argument('clave')
    for operacion in (local, remota):
        operacion.add_argument('destino', type=Path)
        operacion.add_argument('--identidad', type=Path, required=True)
    sub.add_parser('listar')
    args = parser.parse_args()
    try:
        if args.operacion == 'abrir':
            resultado = abrir(args.archivo, args.destino, args.identidad, sha256=args.sha256)
        elif args.operacion == 'crear':
            resultado = crear(args.origen, args.archivo, os.environ.get('SCONTO_BACKUP_AGE_RECIPIENT', ''),
                             catalogo=args.catalogo, raices_crudas=args.raiz_crudos)
        else:
            bucket, cliente = _conectar_s3()
            with closing(cliente):
                if args.operacion == 'recuperar':
                    resultado = recuperar(args.clave, args.destino, args.identidad, bucket, cliente)
                elif args.operacion == 'listar':
                    resultado = dict(claves=listar(bucket, cliente))
                else:
                    with TemporaryDirectory() as temp:
                        ruta = Path(temp) / 'respaldo.age'
                        destinatario = os.environ.get('SCONTO_BACKUP_AGE_RECIPIENT', '')
                        if not re.fullmatch(r'age1[0-9a-z]{58}', destinatario):
                            raise ValueError('Se requiere un destinatario público age X25519 válido')
                        qqp = enviar_qqp(args.origen, destinatario, bucket, cliente)
                        crear(args.origen, ruta, destinatario, catalogo=args.catalogo, raices_crudas=args.raiz_crudos,
                              qqp_externo=qqp)
                        resultado = enviar(ruta, bucket, cliente)
                        resultado['archivos_qqp'] = len(qqp)
    except Exception as error:
        # El informe no incorpora cuerpos HTTP, ubicaciones de llaves ni valores de entorno.
        print(json.dumps(dict(estado='error', tipo=type(error).__name__)), file=sys.stderr)
        return 1
    print(json.dumps(resultado, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
