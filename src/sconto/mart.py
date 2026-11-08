"""ETL de entrega Colab → tablas analíticas → SQLite/JSON para la miniweb."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
import zipfile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from sconto.colab import cargar_paquete
from sconto.mineria import modelar

VERSION = 'sconto-mart-v1'
FK = {
    'series': [('producto_canonico_id', 'productos', 'producto_canonico_id')],
    'observaciones': [('serie_id', 'series', 'serie_id')],
    'precios_diarios': [('serie_id', 'series', 'serie_id'), ('obs_ejemplo_id', 'observaciones', 'obs_id')],
    'referencias_base': [('serie_id', 'series', 'serie_id'), ('evento_id', 'eventos', 'evento_id')],
    'ofertas': [('serie_id', 'series', 'serie_id'), ('obs_id', 'observaciones', 'obs_id')],
    'resultados_modelo': [('serie_id', 'series', 'serie_id'), ('evento_id', 'eventos', 'evento_id')],
}
PK = {'productos': ['producto_canonico_id'], 'eventos': ['evento_id'], 'series': ['serie_id'],
      'observaciones': ['obs_id'], 'precios_diarios': ['serie_id', 'fecha_precio'],
      'referencias_base': ['serie_id', 'evento_id'], 'ofertas': ['obs_id'],
      'resultados_modelo': ['serie_evento_id']}
PK.update(catalogo_consulta=['producto_canonico_id'], ofertas_evaluadas=['obs_id'], revision_identidades=['obs_id'])
FK.update(catalogo_consulta=[('producto_canonico_id', 'productos', 'producto_canonico_id')],
          ofertas_evaluadas=[('obs_id', 'ofertas', 'obs_id'), ('referencia_serie_id', 'series', 'serie_id')],
          revision_identidades=[('obs_id', 'ofertas_evaluadas', 'obs_id')])


def registros(datos):
    return json.loads(datos.to_json(orient='records', force_ascii=False, date_format='iso'))


def _fechas(datos):
    datos = datos.copy()
    for columna in datos.columns:
        if pd.api.types.is_datetime64_any_dtype(datos[columna]):
            datos[columna] = datos[columna].dt.strftime('%Y-%m-%d')
    return datos


def preparar_tablas(gold, seleccion, fecha_corte, arboles=300, ampliar_catalogo=False):
    corte = pd.Timestamp(fecha_corte).normalize()
    obs = gold['observaciones'].copy()
    capturas = pd.to_datetime(obs.fecha_captura)
    if capturas.max().normalize() > corte:
        raise ValueError('Para un corte anterior se necesita su snapshot: gold consolidado no reconstruye versiones pasadas.')
    obs['fecha_precio'] = pd.to_datetime(obs.fecha_precio)
    if obs.fecha_precio.gt(corte).any():
        raise ValueError('El snapshot contiene precios posteriores al corte')
    eventos = gold['eventos'].copy()
    for columna in eventos.columns:
        if columna != 'evento_id' and (columna.endswith(('_inicio', '_fin')) or columna in ('d0', 'fin')):
            eventos[columna] = pd.to_datetime(eventos[columna])
    analisis = modelar(gold['series_evento'], eventos, corte.date().isoformat(), arboles=arboles)
    productos = gold['productos'].copy()
    if productos.producto_canonico_id.duplicated().any():
        raise ValueError('Catálogo canónico no único')
    from sconto.catalogo import ampliar_seleccion, categoria_app, CATEGORIAS
    ids = ampliar_seleccion(productos, obs, seleccion) if ampliar_catalogo else seleccion.producto_canonico_id.tolist()
    orden = {identificador: indice + 1 for indice, identificador in enumerate(ids)}
    productos['nombre'] = productos.descripcion_externa.fillna('').replace('', pd.NA).fillna(productos.descripcion_qqp)
    productos['orden_web'] = productos.producto_canonico_id.map(orden)
    productos['en_catalogo_web'] = productos.orden_web.notna()
    productos['en_piloto'] = productos.orden_web.le(30)
    productos['en_seguimiento_diario'] = productos.producto_canonico_id.isin(seleccion.producto_canonico_id)
    productos['categoria_app'] = [categoria_app(n, f, c) for n, f, c in zip(productos.nombre, productos.familia, productos.categoria)]
    productos['categoria_app_nombre'] = productos.categoria_app.map(CATEGORIAS)
    productos['identidad'] = np.where(productos.origen.eq('preciometro'), 'id_nativo_del_agregador', 'referencia_QQP')
    columnas_producto = ['producto_canonico_id', 'nombre', 'marca', 'modelo_normalizado', 'familia', 'categoria',
                         'origen', 'confianza_match', 'identidad', 'en_catalogo_web', 'en_piloto', 'orden_web',
                         'en_seguimiento_diario', 'categoria_app', 'categoria_app_nombre']
    productos = productos[columnas_producto].sort_values('producto_canonico_id')
    if len(orden) != int(productos.en_catalogo_web.sum()):
        raise ValueError('La lista diaria contiene productos ausentes o duplicados en el catálogo del snapshot')
    series_modelo = set(analisis['resultados'].get('serie_id', pd.Series(dtype=str)))
    sub = obs.loc[obs.producto_canonico_id.isin(orden) | obs.serie_id.isin(series_modelo)].copy()
    if sub.empty:
        raise ValueError('No hay observaciones para construir el mart')
    columnas_serie = ['serie_id', 'producto_canonico_id', 'fuente', 'plataforma_serie', 'canal', 'tipo_precio',
                      'id_externo', 'vendedor_serie', 'moneda', 'descripcion_original']
    series = sub.sort_values(['fecha_precio', 'obs_id']).drop_duplicates('serie_id', keep='last')[columnas_serie].copy()
    series['contexto'] = np.where(series.tipo_precio.eq('minimo_diario_multitienda'), 'minimo_multitienda', 'serie_vendedor')
    series['vendedor_confirmado'] = ~series.vendedor_serie.fillna('SIN_VENDEDOR').str.startswith('SIN_VENDEDOR')
    columnas_obs = ['obs_id', 'serie_id', 'fuente', 'metodo', 'fecha_precio', 'fecha_captura', 'precio',
                    'precio_anterior_anunciado', 'pct_descuento_anunciado', 'moneda', 'condiciones', 'url', 'ruta_raw', 'hash_raw']
    observaciones = sub[columnas_obs].sort_values('obs_id')
    diarios = sub.sort_values('obs_id').groupby(['serie_id', 'fecha_precio'], as_index=False).agg(
        precio_mediano=('precio', 'median'), n_observaciones=('precio', 'size'), obs_ejemplo_id=('obs_id', 'first'))
    referencias = []
    for evento in eventos.itertuples():
        base = diarios.loc[diarios.fecha_precio.between(evento.base_inicio, min(evento.base_fin, corte))]
        grupos = base.groupby('serie_id')
        estadisticas = grupos.agg(n_fechas_base=('fecha_precio', 'size'), mediana_base=('precio_mediano', 'median'),
                                  minimo_base=('precio_mediano', 'min'), maximo_base=('precio_mediano', 'max'),
                                  inicio_observado=('fecha_precio', 'min'), fin_observado=('fecha_precio', 'max'))
        cuartiles = grupos.precio_mediano.quantile([.25, .75]).unstack()
        cuartiles = cuartiles.reindex(columns=[.25, .75]).rename(columns={.25: 'p25_base', .75: 'p75_base'})
        estadisticas = estadisticas.join(cuartiles)
        referencia = series[['serie_id', 'contexto', 'vendedor_confirmado', 'moneda', 'canal']].merge(
            estadisticas, on='serie_id', how='left')
        referencia['evento_id'] = evento.evento_id
        referencia['n_fechas_base'] = referencia.n_fechas_base.fillna(0).astype(int)
        referencia['amplitud_base_dias'] = (referencia.fin_observado - referencia.inicio_observado).dt.days
        referencia['base_cerrada'] = corte >= evento.base_fin
        referencia['cobertura_base'] = (referencia.n_fechas_base.ge(4) & referencia.amplitud_base_dias.ge(21)
                                        & referencia.vendedor_confirmado)
        referencia['base_inicio'] = evento.base_inicio
        referencia['base_fin'] = evento.base_fin
        referencias.append(referencia)
    referencias = pd.concat(referencias, ignore_index=True)
    actuales = sub.loc[sub.fuente.isin(['preciometro_ofertas', 'mercadolibre', 'amazon', 'tiendas'])].copy()
    actuales = actuales.sort_values(['fecha_precio', 'fecha_captura', 'obs_id']).drop_duplicates('serie_id', keep='last')
    actuales['edad_dias'] = (corte - actuales.fecha_precio).dt.days
    actuales['observada_en_corte'] = actuales.edad_dias.eq(0)
    columnas_oferta = ['obs_id', 'serie_id', 'producto_canonico_id', 'fecha_precio', 'plataforma',
                       'vendedor_o_cadena', 'precio', 'precio_anterior_anunciado', 'pct_descuento_anunciado',
                       'moneda', 'disponibilidad', 'condiciones', 'url', 'edad_dias', 'observada_en_corte']
    calidad = obs.groupby('fuente', as_index=False).agg(filas=('precio', 'size'), ids_externos=('id_externo', 'nunique'),
        primera_fecha=('fecha_precio', 'min'), ultima_fecha=('fecha_precio', 'max'),
        ultima_captura=('fecha_captura', 'max'), con_tachado=('precio_anterior_anunciado', 'count'))
    resultados = analisis['resultados']
    if resultados.empty:
        resultados = pd.DataFrame(columns=['serie_evento_id', 'serie_id', 'evento_id', 'puntaje_anomalia', 'etapa'])
    evaluacion = analisis['evaluacion']
    if len(evaluacion.columns) == 0:
        evaluacion = pd.DataFrame(columns=['experimento', 'metrica', 'valor', 'n_casos', 'interpretacion'])
    tablas = dict(productos=productos, eventos=eventos, series=series.sort_values('serie_id'),
                  observaciones=observaciones, precios_diarios=diarios.sort_values(['serie_id', 'fecha_precio']),
                  referencias_base=referencias.sort_values(['serie_id', 'evento_id']), ofertas=actuales[columnas_oferta],
                  resultados_modelo=resultados, evaluacion_modelo=evaluacion,
                  sensibilidad=gold['sensibilidad'], calidad_fuentes=calidad)
    tablas = {nombre: _fechas(tabla.reset_index(drop=True)) for nombre, tabla in tablas.items()}
    return tablas, analisis


def _identificador(nombre):
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', nombre):
        raise ValueError('Identificador SQL no permitido')
    return '"' + nombre + '"'


def guardar_sqlite(tablas, ruta):
    temporal = ruta.with_name(ruta.stem + '.' + uuid.uuid4().hex + '.sqlite.tmp')
    with closing(sqlite3.connect(temporal)) as conexion, conexion:
        conexion.execute('PRAGMA foreign_keys=ON')
        for nombre, tabla in tablas.items():
            if len(tabla.columns) == 0:
                continue
            columnas = []
            for columna in tabla.columns:
                tipo = 'INTEGER' if pd.api.types.is_bool_dtype(tabla[columna]) or pd.api.types.is_integer_dtype(tabla[columna]) else 'REAL' if pd.api.types.is_numeric_dtype(tabla[columna]) else 'TEXT'
                columnas.append(f'{_identificador(columna)} {tipo}')
            if nombre in PK:
                columnas.append('PRIMARY KEY (' + ','.join(_identificador(columna) for columna in PK[nombre]) + ')')
            for columna, destino, clave in FK.get(nombre, []):
                columnas.append(f'FOREIGN KEY ({_identificador(columna)}) REFERENCES {_identificador(destino)}({_identificador(clave)})')
            for campo in ('precio', 'precio_mediano'):
                if campo in tabla:
                    columnas.append(f'CHECK ({_identificador(campo)} > 0)')
            conexion.execute(f'CREATE TABLE {_identificador(nombre)} (' + ','.join(columnas) + ')')
            tabla.to_sql(nombre, conexion, if_exists='append', index=False)
        if conexion.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Referencias de SQLite inválidas')
        if conexion.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Integridad SQLite incorrecta')
        for nombre, tabla in tablas.items():
            if len(tabla.columns) and conexion.execute(f'SELECT COUNT(*) FROM {_identificador(nombre)}').fetchone()[0] != len(tabla):
                raise ValueError('Se perdieron filas en la exportación SQLite')
    temporal.replace(ruta)


def exportar(tablas, analisis, salida, fuente, fecha_corte, extras_json=None):
    salida.mkdir(parents=True, exist_ok=True)
    archivos = []
    for nombre, tabla in tablas.items():
        if len(tabla.columns) == 0:
            continue
        parquet = salida / f'{nombre}.parquet'
        csv = salida / f'{nombre}.csv.gz'
        tabla.to_parquet(parquet, index=False)
        tabla.to_csv(csv, index=False, compression={'method': 'gzip', 'mtime': 0})
        archivos.extend([parquet, csv])
    base = salida / 'sconto_web.sqlite'
    guardar_sqlite(tablas, base)
    archivos.append(base)
    tarjeta = salida / 'modelo.json'
    tarjeta.write_text(json.dumps(analisis['tarjeta'], ensure_ascii=False, indent=2), encoding='utf-8')
    archivos.append(tarjeta)
    revision = salida / 'casos_para_revision.csv'
    analisis['revision'].to_csv(revision, index=False)
    archivos.append(revision)
    eventos = tablas['eventos']
    candidatos = eventos.loc[pd.to_datetime(eventos.d0).dt.year.eq(pd.Timestamp(fecha_corte).year)]
    evento_actual = candidatos.evento_id.iloc[0] if len(candidatos) else None
    productos_web = tablas['productos'].loc[tablas['productos'].en_catalogo_web].sort_values('orden_web')
    series_web = tablas['series'].loc[tablas['series'].producto_canonico_id.isin(productos_web.producto_canonico_id)]
    referentes = tablas['referencias_base'].loc[tablas['referencias_base'].evento_id.eq(evento_actual)]
    referentes = referentes.loc[referentes.serie_id.isin(series_web.serie_id)]
    feed = dict(version=VERSION, fecha_corte=fecha_corte, evento_actual=evento_actual,
                productos=registros(productos_web), series=registros(series_web),
                referencias=registros(referentes), ofertas=registros(tablas['ofertas']),
                calidad=registros(tablas['calidad_fuentes']), modelo=analisis['tarjeta'])
    feed_ruta = salida / 'web_feed.json'
    feed_ruta.write_text(json.dumps(feed, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    archivos.append(feed_ruta)
    for nombre, objeto in (extras_json or {}).items():
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*\.json', nombre):
            raise ValueError('Nombre de JSON inválido')
        destino = salida / nombre
        if destino.name in {archivo.name for archivo in archivos} or destino.name == 'manifest.json':
            raise ValueError('Un extra no puede reemplazar un archivo del contrato')
        destino.write_text(json.dumps(objeto, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')
        archivos.append(destino)
    manifiesto = dict(version=VERSION, generado_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      fecha_corte=fecha_corte, fuente=fuente, revision_codigo=os.environ.get('GITHUB_SHA'),
                      tablas={nombre: len(tabla) for nombre, tabla in tablas.items()},
                      archivos={archivo.name: hashlib.sha256(archivo.read_bytes()).hexdigest() for archivo in archivos},
                      advertencias=['No hay etiquetas verificadas de fraude ni exactitud supervisada.',
                                    'El mínimo multitienda es referencia de mercado, no historial de una tienda.',
                                    'No se imputa ni se extrapolan precios futuros.',
                                    'La fecha de corte corresponde al snapshot, no al reloj del navegador.'])
    (salida / 'manifest.json').write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding='utf-8')
    paquete = salida / 'sconto_web.zip'
    temporal = paquete.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporal, 'w', compression=zipfile.ZIP_DEFLATED) as archivo_zip:
        for archivo in archivos + [salida / 'manifest.json']:
            archivo_zip.write(archivo, archivo.name)
    temporal.replace(paquete)
    return manifiesto


def ejecutar(paquete, seleccion, salida, arboles=300, ampliar_catalogo=True):
    from sconto.app_datos import preparar_aplicacion
    contenido = Path(paquete).read_bytes()
    gold = cargar_paquete(io.BytesIO(contenido))
    with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
        origen = json.loads(archivo.read('paquete.json'))
    captura = pd.Timestamp(origen['dataset_construido_utc'])
    if captura.tzinfo is None:
        captura = captura.tz_localize('UTC')
    corte = captura.tz_convert(ZoneInfo('America/Mexico_City')).date().isoformat()
    tablas, analisis = preparar_tablas(gold, pd.read_csv(seleccion, dtype=str), corte, arboles=arboles, ampliar_catalogo=ampliar_catalogo)
    fuente = dict(archivo=Path(paquete).name, sha256=hashlib.sha256(contenido).hexdigest(),
                  construido_utc=origen['dataset_construido_utc'], filas_observaciones=len(gold['observaciones']))
    compra, extras = preparar_aplicacion(tablas, corte)
    tablas.update(compra)
    manifiesto = exportar(tablas, analisis, Path(salida), fuente, corte, extras_json=extras)
    return gold, tablas, analisis, manifiesto


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paquete', type=Path, required=True)
    parser.add_argument('--seleccion', type=Path, default=Path('config/preciometro_diarios.csv'))
    parser.add_argument('--salida', type=Path, default=Path('data/analitica'))
    parser.add_argument('--solo-seleccion', action='store_true', help='Limitar la consulta a la lista diaria original')
    argumentos = parser.parse_args(argv)
    _, _, analisis, manifiesto = ejecutar(argumentos.paquete, argumentos.seleccion, argumentos.salida, ampliar_catalogo=not argumentos.solo_seleccion)
    print(json.dumps(dict(tablas=manifiesto['tablas'], modelo=analisis['tarjeta']), ensure_ascii=False))


if __name__ == '__main__':
    main()
