"""Verificación de un mismo corte para la operación y la reproducción portable."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from sconto.cuaderno import cargar_entrada, reconstruir


def conciliar_por_fuente(bronze, gold):
    capturas = gold['observaciones'].groupby('fuente').n_capturas.sum()
    conteos = pd.concat([
        bronze.groupby('fuente', dropna=False).size().rename('filas_bronze'),
        gold['observaciones'].groupby('fuente', dropna=False).size().rename('observaciones_gold'),
        capturas.rename('capturas_representadas'),
        gold['exclusiones'].groupby('fuente', dropna=False).size().rename('exclusiones'),
    ], axis=1).fillna(0).astype('int64').rename_axis('fuente').reset_index()
    conteos['diferencia'] = conteos.filas_bronze - conteos.capturas_representadas - conteos.exclusiones
    return conteos


def comprobar_gold(reconstruido, referencia):
    """Compara todas las tablas comunes con el mismo orden y representación del ETL diario."""
    faltantes = set(referencia) - set(reconstruido)
    if faltantes:
        raise ValueError(f'Tablas fuera de la reconstrucción: {sorted(faltantes)}')
    for nombre, esperado in referencia.items():
        calculado = reconstruido[nombre]
        if nombre == 'observaciones':
            calculado = calculado.assign(**{
                c: calculado[c].dt.date.astype(str) for c in ('fecha_precio', 'fecha_captura')})
        try:
            pd.testing.assert_frame_equal(calculado, esperado, check_dtype=False, check_exact=True)
        except AssertionError as error:
            raise AssertionError(f'{nombre}: {error}') from error


def reconstruir_corte(entrada, referencia, sha256_gold):
    bruto, metadatos = cargar_entrada(entrada)
    if metadatos['gold_sha256'] != sha256_gold:
        raise ValueError('El paquete bronze corresponde a otro snapshot gold')
    gold, auditoria = reconstruir(
        bruto['bronze_observaciones'], bruto['productos'], bruto['eventos'], metadatos['fecha_corte'])
    por_fuente = conciliar_por_fuente(bruto['bronze_observaciones'], gold)
    if por_fuente.diferencia.ne(0).any():
        raise ValueError('El conteo bronze y gold discrepa por fuente')
    comprobar_gold(gold, referencia)
    return gold, auditoria, por_fuente


CAMPOS_PROFECO = ('producto_profeco_id', 'categoria_profeco_id', 'tipo_producto', 'marca',
                  'sucursal_ref', 'zona_sucursal', 'fecha_precio', 'precio_mxn', 'consultado_utc')


def empaquetar_profeco(observaciones, exclusiones, destino, fecha_corte):
    """Prepara precios y exclusiones para acceso privado, sin direcciones ni rutas crudas."""
    tablas = [pd.read_csv(p, dtype={'producto_profeco_id': str}) for p in (observaciones, exclusiones)]
    claves = sorted(set().union(*(zip(t.sucursal, t.direccion) for t in tablas)))
    sucursales = {clave: f'S{indice:04}' for indice, clave in enumerate(claves, 1)}
    cuerpo = {}
    for nombre, tabla in zip(('observaciones', 'exclusiones'), tablas):
        tabla['sucursal_ref'] = [sucursales[clave] for clave in zip(tabla.sucursal, tabla.direccion)]
        columnas = list(CAMPOS_PROFECO) + (['motivo'] if nombre == 'exclusiones' else [])
        cuerpo[nombre] = tabla[columnas].to_csv(index=False, lineterminator='\n').encode('utf-8')
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    manifest = dict(version='sconto-profeco-bf-v2', fecha_corte=fecha_corte,
                    publicacion='entrada privada de reproducción', tablas={})
    temporal = destino.with_suffix('.zip.tmp')
    with ZipFile(temporal, 'w', compression=ZIP_DEFLATED) as archivo:
        for (nombre, datos), tabla in zip(cuerpo.items(), tablas):
            manifest['tablas'][nombre] = dict(filas=len(tabla), sha256=hashlib.sha256(datos).hexdigest())
            archivo.writestr(nombre + '.csv', datos)
        archivo.writestr('profeco.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    temporal.replace(destino)
    return manifest


def cargar_profeco(entrada):
    tablas = {}
    with ZipFile(entrada) as archivo:
        manifiesto = json.loads(archivo.read('profeco.json'))
        if manifiesto['version'] != 'sconto-profeco-bf-v2':
            raise ValueError('Versión PROFECO no compatible')
        for nombre in ('observaciones', 'exclusiones'):
            esperada = manifiesto['tablas'][nombre]
            datos = archivo.read(nombre + '.csv')
            if hashlib.sha256(datos).hexdigest() != esperada['sha256']:
                raise ValueError(f'PROFECO {nombre}: SHA-256 incorrecto')
            campos = CAMPOS_PROFECO + (('motivo',) if nombre == 'exclusiones' else ())
            tabla = pd.read_csv(io.BytesIO(datos), dtype={'producto_profeco_id': str})
            if len(tabla) != esperada['filas'] or tuple(tabla.columns) != campos:
                raise ValueError(f'PROFECO {nombre}: esquema o conteo incorrecto')
            tablas[nombre] = tabla
    return tablas, manifiesto
