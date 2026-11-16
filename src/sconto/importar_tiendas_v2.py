"""Importa comprobaciones locales archivadas sin consultar ni copiar crudos de tiendas."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sconto.fuentes.tiendas import CONFIANZAS, _bloqueo, parsear_ficha, validar_url
from sconto.intraday import CDMX, RAIZ_INTRADIA, IntradayStore, Observacion, Oferta, Trabajo
from sconto.rutas import CONFIG, DATA


def importar(archivo_objetivos: Path, workspace: Path, store: IntradayStore) -> dict:
    resumen = dict(importadas=0, repetidas=0, con_precio=0, durante_buen_fin=0, rechazadas=[])
    with archivo_objetivos.open(encoding='utf-8-sig', newline='') as archivo:
        objetivos = [fila for fila in csv.DictReader(archivo)
                     if fila['habilitado'].casefold() in {'1', 'true', 'si', 'sí'}
                     and fila['confianza'].casefold() in CONFIANZAS]
    directorio = (workspace / 'data' / 'raw' / 'tiendas').resolve(strict=True)
    for objetivo in objetivos:
        url = validar_url(objetivo['url'], objetivo['tienda'])
        if not objetivo['producto_canonico_id'].strip():
            raise ValueError('La ficha requiere producto canónico')
        nombre = hashlib.sha256(url.encode()).hexdigest()[:24]
        for metadatos in sorted(directorio.glob(f'*/{nombre}.json.gz')):
            try:
                datos = json.loads(gzip.decompress(metadatos.read_bytes()))
                cuerpo = metadatos.with_name(f'{nombre}.body.gz').resolve(strict=True)
                if not cuerpo.is_relative_to(directorio):
                    raise ValueError('La referencia cruda sale del archivo de tiendas')
                crudo = gzip.decompress(cuerpo.read_bytes())
                hora = datetime.fromisoformat(datos['fecha_captura'])
                http = datos['http']
                if (datos['url'] != url or hashlib.sha256(crudo).hexdigest() != datos['hash_raw']
                        or hora.utcoffset() is None or isinstance(http, bool) or not 100 <= http <= 599):
                    raise ValueError('Los metadatos o el hash difieren de la evidencia original')
                bloqueo = _bloqueo(http, crudo)
                ficha = parsear_ficha(crudo, url) if http == 200 and not bloqueo else None
                observaciones = []
                if ficha:
                    variante = parse_qs(urlsplit(url).query).get('skuid', [None])[0]
                    oferta = Oferta(anuncio_id=nombre, producto_id=objetivo['producto_canonico_id'],
                                    plataforma=objetivo['tienda'], enlace=url, variante=variante,
                                    vendedor=ficha['vendedor'])
                    observaciones.append(Observacion(oferta, ficha['precio'], ficha['moneda'], observed_at=hora,
                                                    precio_tachado=ficha['precio_anterior'],
                                                    disponibilidad=ficha['disponibilidad'], condiciones={
                                                        'titulo': ficha['descripcion'], 'evidencia': ficha['evidencia'],
                                                        'marca': ficha['marca'], 'modelo': ficha['modelo'],
                                                        'pct_anunciado': ficha['pct'], 'envio_importe': None,
                                                        'confianza_lista_original': objetivo['confianza'],
                                                        'procedencia': 'archivo_local_preexistente',
                                                    }))
                trabajo = Trabajo('tiendas', url, hora)
                captura = store.tomar(trabajo)
                if captura is None:
                    resumen['repetidas'] += 1
                    continue
                resultado = 'ok' if ficha else ('bloqueado' if bloqueo else 'sin_oferta')
                store.registrar(captura, fetched_at=hora, resultado=resultado, crudo=crudo, estado_http=http,
                                observaciones=observaciones, ultimo_error=bloqueo, crudo_preexistente=cuerpo,
                                version_colector='tiendas-diario-v1', registrado_at=datetime.now(timezone.utc))
                resumen['importadas'] += 1
                resumen['con_precio'] += bool(ficha)
                resumen['durante_buen_fin'] += bool(ficha) and (
                    '2026-11-13' <= hora.astimezone(CDMX).date().isoformat() <= '2026-11-17')
            except (KeyError, TypeError, ValueError, OSError, EOFError) as error:
                resumen['rechazadas'].append(dict(archivo=metadatos.parent.name + '/' + metadatos.name,
                                                  motivo=f'{type(error).__name__}: {error}'))
    return resumen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--objetivos', type=Path, default=CONFIG / 'tiendas_objetivo.csv')
    parser.add_argument('--workspace', type=Path, default=DATA / 'operacion' / 'workspace')
    parser.add_argument('--salida', type=Path, default=RAIZ_INTRADIA)
    argumentos = parser.parse_args(argv)
    store = IntradayStore(argumentos.salida)
    with store.exclusividad_colector() as permiso:
        if not permiso:
            parser.error('Ya existe un recolector usando el almacén')
        store.vencidos()
        resultado = importar(argumentos.objetivos, argumentos.workspace, store)
    print(json.dumps(dict(resultado, almacen=store.estado()), ensure_ascii=False))
    return bool(resultado['rechazadas'])


if __name__ == '__main__':
    raise SystemExit(main())
