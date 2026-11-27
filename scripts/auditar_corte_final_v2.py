"""Auditoría del corte final de datos de Sconto (sólo lectura).

Lee las copias congeladas del corte y produce un informe Markdown y un JSON con
conteos, rangos de fechas, cobertura por ventana del Buen Fin y comprobaciones de
integridad. No modifica las entradas: los SQLite se abren en modo de sólo lectura.

Uso:
    python scripts/auditar_corte_final_v2.py --corte data/operacion/v2/corte_final_20261126 --fecha 2026-11-26
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
from sconto.esquema import CLAVE  # noqa: E402

VENTANAS = ('base', 'previo', 'evento', 'posterior')


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def leer_sqlite(ruta: Path) -> sqlite3.Connection:
    return sqlite3.connect(f'file:{ruta.as_posix()}?mode=ro&immutable=1', uri=True)


def ventana(fecha: pd.Series, ev: pd.Series) -> pd.Series:
    """Asigna cada fecha a base, previo, evento o posterior según el evento dado."""
    salida = pd.Series(pd.NA, index=fecha.index, dtype='object')
    for v in VENTANAS:
        dentro = fecha.between(ev[f'{v}_inicio'] if v != 'evento' else ev['evento_inicio'],
                               ev[f'{v}_fin'] if v != 'evento' else ev['evento_fin'])
        salida = salida.mask(dentro & salida.isna(), v)
    return salida


# ---------------------------------------------------------------- paquete histórico

def auditar_paquete(ruta: Path) -> dict:
    z = zipfile.ZipFile(ruta)
    meta = json.loads(z.read('paquete.json'))
    leer = lambda n: pd.read_parquet(io.BytesIO(z.read(n)))  # noqa: E731
    huellas = {}
    for nombre, t in meta['tablas'].items():
        datos = z.read(t['archivo'])
        huellas[nombre] = hashlib.sha256(datos).hexdigest() == t['sha256']
    obs = leer('observaciones.parquet')
    excl = leer('exclusiones.parquet')
    eventos = leer('eventos.parquet')
    se = leer('series_evento.parquet')
    mm = leer('matriz_modelo.parquet')
    productos = leer('productos.parquet')

    fecha = pd.to_datetime(obs.fecha_precio, errors='coerce')
    obs = obs.assign(_fecha=fecha, _anio=fecha.dt.year)

    por_fuente = []
    for f, g in obs.groupby('fuente'):
        por_fuente.append({
            'fuente': f,
            'filas': len(g),
            'productos': int(g.producto_canonico_id.nunique()),
            'series': int(g.serie_id.nunique()),
            'fecha_min': str(g._fecha.min().date()),
            'fecha_max': str(g._fecha.max().date()),
            'captura_max': str(g.fecha_captura.max())[:10],
            'canales': sorted(g.canal.dropna().unique().tolist()),
        })
    por_anio = (obs.groupby(['fuente', '_anio']).size().unstack(fill_value=0)
                .astype(int).to_dict(orient='index'))

    integridad = {
        'duplicados_por_clave': int(obs.duplicated(CLAVE).sum()),
        'precio_no_positivo': int((obs.precio <= 0).sum()),
        'fecha_no_valida': int(fecha.isna().sum()),
        'pct_descuento_fuera_de_rango': int((~obs.pct_descuento_anunciado.dropna().between(-100, 100)).sum()),
        'series_con_canal_mezclado': int(obs.groupby('serie_id').canal.nunique().gt(1).sum()),
        'filas_revisar_captura': int(obs.revisar_captura.sum()),
        'filas_precio_revisado_por_fuente': int(obs.precio_revisado_por_fuente.sum()),
        'exclusiones': len(excl),
        'huellas_paquete_ok': huellas,
    }

    cobertura_eventos = {}
    for _, ev in eventos.iterrows():
        ev = ev.copy()
        for c in ev.index:
            if c.endswith(('_inicio', '_fin')):
                ev[c] = pd.Timestamp(ev[c])
        v = ventana(obs._fecha, ev)
        tabla = (obs.assign(_v=v).dropna(subset=['_v']).groupby(['fuente', '_v']).size()
                 .unstack(fill_value=0).reindex(columns=list(VENTANAS), fill_value=0).astype(int))
        cobertura_eventos[ev.evento_id] = tabla.to_dict(orient='index')

    series = (se.groupby(['evento_id', 'plataforma_serie'])
              .agg(series=('serie_id', 'size'), cobertura_ahorro=('cobertura_ahorro', 'sum'),
                   cobertura_alza=('cobertura_alza', 'sum'))
              .astype(int).reset_index().to_dict(orient='records'))

    qqp25 = obs.loc[obs.fuente.eq('qqp_cdmx') & obs.fecha_precio.str.startswith('2025')]
    bf25 = se.loc[se.evento_id.eq('BF2025') & se.plataforma_serie.eq('qqp_cdmx')]
    reproduccion = {
        'qqp_2025_filas': len(qqp25), 'esperado_filas': 39363,
        'bf2025_ahorro': int(bf25.cobertura_ahorro.sum()), 'esperado_ahorro': 298,
        'bf2025_alza': int(bf25.cobertura_alza.sum()), 'esperado_alza': 93,
    }
    reproduccion['ok'] = (reproduccion['qqp_2025_filas'] == 39363 and reproduccion['bf2025_ahorro'] == 298
                          and reproduccion['bf2025_alza'] == 93)

    return {
        'archivo': ruta.name, 'sha256': sha256(ruta), 'exportado_utc': meta.get('exportado_utc'),
        'filas': len(obs), 'productos_catalogo': len(productos), 'por_fuente': por_fuente,
        'por_anio': {k: {str(int(a)): n for a, n in v.items() if pd.notna(a)} for k, v in por_anio.items()},
        'integridad': integridad, 'cobertura_eventos': cobertura_eventos, 'series_evento': series,
        'matriz_modelo': {'filas': len(mm), 'variables': mm.columns.tolist()},
        'reproduccion_avance1': reproduccion,
    }


# ---------------------------------------------------------------- piloto PROFECO

def auditar_piloto(ruta: Path, eventos: pd.DataFrame) -> dict:
    c = leer_sqlite(ruta)
    q = lambda s: pd.read_sql(s, c)  # noqa: E731
    tablas = {n: int(c.execute(f'select count(*) from "{n}"').fetchone()[0])
              for (n,) in c.execute("select name from sqlite_master where type='table'")}
    capt = q('select fuente, resultado, fetched_at_utc from capturas')
    capt['dia_cdmx'] = (pd.to_datetime(capt.fetched_at_utc, utc=True)
                        .dt.tz_convert('America/Mexico_City').dt.strftime('%Y-%m-%d'))
    errores = int(c.execute('select count(*) from intentos where ultimo_error is not null').fetchone()[0])
    ofertas = q('select offer_id, fuente, producto_id, anuncio_id, plataforma, vendedor from ofertas')
    diarias = q('select d.capture_id, d.offer_id, d.fecha_precio, d.precio, d.moneda, d.condiciones_json, '
                'c.fetched_at_utc from observaciones_diarias_fuente d join capturas c using(capture_id)')
    intradia = q('select i.*, o.vendedor, o.plataforma from observaciones_intradia i join ofertas o using(offer_id)')
    c.close()

    integridad = {
        'tablas': tablas,
        'claves_foraneas_ok': True,
        'intentos_con_error': errores,
        'precio_no_positivo': int((diarias.precio <= 0).sum()),
        'monedas': sorted(diarias.moneda.unique().tolist()),
    }
    integridad['claves_foraneas_ok'] = bool(diarias.offer_id.isin(ofertas.offer_id).all())

    # Cada captura vuelve a reportar la historia publicada: se deduplica por anuncio y fecha.
    diarias = diarias.sort_values('fetched_at_utc')
    pares = diarias.groupby(['offer_id', 'fecha_precio'])
    conflictos = int(pares.precio.nunique().gt(1).sum())
    unicas = pares.tail(1).copy()
    unicas = unicas.merge(ofertas[['offer_id', 'producto_id', 'vendedor']], on='offer_id', how='left')
    unicas['zona'] = unicas.condiciones_json.map(lambda s: json.loads(s).get('zona_consulta'))
    fecha = pd.to_datetime(unicas.fecha_precio)

    ev = eventos.set_index('evento_id').loc['BF2026'].copy()
    for col in ev.index:
        if col.endswith(('_inicio', '_fin')):
            ev[col] = pd.Timestamp(ev[col])
    unicas['ventana'] = ventana(fecha, ev)
    por_ventana = unicas.ventana.fillna('fuera_de_ventanas').value_counts().astype(int).to_dict()
    cubre = unicas.dropna(subset=['ventana']).groupby('offer_id').ventana.agg(set)
    series = {
        'anuncios_producto_sucursal': int(unicas.offer_id.nunique()),
        'con_precio_en_evento': int(cubre.map(lambda s: 'evento' in s).sum()),
        'con_base_previo_y_evento': int(cubre.map(lambda s: {'base', 'previo', 'evento'} <= s).sum()),
        'con_previo_evento_y_posterior': int(cubre.map(lambda s: {'previo', 'evento', 'posterior'} <= s).sum()),
    }
    por_fecha = unicas.groupby('fecha_precio').size().astype(int)
    profeco = unicas.loc[unicas.offer_id.isin(ofertas.loc[ofertas.fuente.eq('profeco_buen_fin'), 'offer_id'])]
    return {
        'archivo': ruta.name, 'sha256': sha256(ruta),
        'capturas': {
            'total': len(capt), 'por_fuente': capt.groupby(['fuente', 'resultado']).size().astype(int)
            .rename('n').reset_index().to_dict(orient='records'),
            'primera_utc': capt.fetched_at_utc.min(), 'ultima_utc': capt.fetched_at_utc.max(),
            'dias_con_captura_profeco': sorted(capt.loc[capt.fuente.eq('profeco_buen_fin'), 'dia_cdmx'].unique().tolist()),
        },
        'precios_diarios': {
            'filas_brutas': len(diarias), 'precios_unicos_anuncio_fecha': len(unicas),
            'precios_profeco_unicos': len(profeco),
            'conflictos_misma_fecha_distinto_precio': conflictos,
            'modelos': int(profeco.producto_id.nunique()), 'sucursales': int(profeco.vendedor.nunique()),
            'zonas': profeco.zona.value_counts().astype(int).to_dict(),
            'fecha_precio_min': str(fecha.min().date()), 'fecha_precio_max': str(fecha.max().date()),
            'por_ventana_bf2026': por_ventana,
            'ultimos_10_dias': {k: int(v) for k, v in por_fecha.tail(10).items()},
        },
        'series_bf2026': series,
        'online': {
            'observaciones_intradia': len(intradia),
            'con_vendedor': int(intradia.vendedor.notna().sum()),
            'con_disponibilidad': int(intradia.disponibilidad.notna().sum()),
            'plataformas': intradia.plataforma.value_counts().astype(int).to_dict(),
            'rango': [intradia.fecha_cdmx.min(), intradia.fecha_cdmx.max()] if len(intradia) else None,
            'ofertas_online_verificadas': 0 if intradia.vendedor.notna().sum() == 0 else None,
        },
        'integridad': integridad,
    }


def auditar_fly(ruta: Path) -> dict:
    c = leer_sqlite(ruta)
    tablas = {n: int(c.execute(f'select count(*) from "{n}"').fetchone()[0])
              for (n,) in c.execute("select name from sqlite_master where type='table'")}
    maximos = {}
    if 'observaciones_diarias_fuente' in tablas:
        maximos['fecha_precio_max'] = c.execute('select max(fecha_precio) from observaciones_diarias_fuente').fetchone()[0]
    if 'capturas' in tablas:
        maximos['ultima_captura_utc'] = c.execute('select max(fetched_at_utc) from capturas').fetchone()[0]
    integ = c.execute('pragma integrity_check').fetchone()[0]
    c.close()
    return {'archivo': ruta.name, 'sha256': sha256(ruta), 'tablas': tablas, **maximos, 'integridad': integ}


# ---------------------------------------------------------------- informe

def tabla_md(filas: list[dict], columnas: list[str]) -> str:
    cab = '| ' + ' | '.join(columnas) + ' |\n|' + '---|' * len(columnas) + '\n'
    return cab + ''.join('| ' + ' | '.join(f'{r.get(c, "")}' for c in columnas) + ' |\n' for r in filas)


def fmt(n) -> str:
    return f'{n:,}' if isinstance(n, int) else str(n)


def escribir_md(r: dict, ruta: Path) -> None:
    p, pi = r['paquete'], r['piloto']
    lineas = [f"# Auditoría del corte final de datos · {r['fecha_corte']}", '',
              f"Generada {r['generado_utc']} con `scripts/auditar_corte_final_v2.py`, sólo lectura sobre las copias "
              f"congeladas en `{r['carpeta_corte']}`.", '',
              '## 1. Paquete histórico multifuente', '',
              f"`{p['archivo']}` · SHA-256 `{p['sha256']}` · exportado {p['exportado_utc']}.", '',
              f"**{fmt(p['filas'])} observaciones limpias**, {fmt(p['productos_catalogo'])} productos en catálogo.", '',
              tabla_md([{**f, 'filas': fmt(f['filas']), 'canales': ', '.join(f['canales'])} for f in p['por_fuente']],
                       ['fuente', 'filas', 'productos', 'series', 'fecha_min', 'fecha_max', 'captura_max', 'canales']),
              '### Integridad', '']
    i = p['integridad']
    lineas += [f"- Duplicados por clave: {i['duplicados_por_clave']}",
               f"- Precios no positivos: {i['precio_no_positivo']} · fechas no válidas: {i['fecha_no_valida']}",
               f"- Descuentos anunciados fuera de ±100%: {i['pct_descuento_fuera_de_rango']}",
               f"- Series con canal mezclado: {i['series_con_canal_mezclado']}",
               f"- Filas marcadas para revisar captura: {fmt(i['filas_revisar_captura'])} · precio revisado por la "
               f"fuente: {fmt(i['filas_precio_revisado_por_fuente'])} · exclusiones: {i['exclusiones']}",
               f"- Huellas de tablas contra `paquete.json`: "
               f"{'todas coinciden' if all(i['huellas_paquete_ok'].values()) else i['huellas_paquete_ok']}",
               f"- Reproducción del Avance 1 (QQP 2025: 39,363 filas; BF2025: 298 ahorro / 93 alza): "
               f"{'se conserva' if p['reproduccion_avance1']['ok'] else p['reproduccion_avance1']}", '',
               '### Observaciones por ventana del Buen Fin', '']
    for ev, t in p['cobertura_eventos'].items():
        filas = [{'fuente': f, **{v: fmt(n) for v, n in w.items()}} for f, w in t.items()]
        lineas += [f'**{ev}**', '', tabla_md(filas, ['fuente', *VENTANAS]) if filas else '_Sin observaciones._\n']
    lineas += ['### Series por evento (`series_evento`)', '',
               tabla_md(p['series_evento'], ['evento_id', 'plataforma_serie', 'series', 'cobertura_ahorro', 'cobertura_alza']),
               f"Matriz del modelo: {p['matriz_modelo']['filas']} filas, variables "
               f"{', '.join(p['matriz_modelo']['variables'])}.", '',
               '## 2. Piloto PROFECO Buen Fin 2026 (precios diarios por sucursal física)', '',
               f"`{pi['archivo']}` · SHA-256 `{pi['sha256']}`.", '']
    cp, pd_ = pi['capturas'], pi['precios_diarios']
    lineas += [f"- Capturas: {cp['total']} (primera {cp['primera_utc']}, última {cp['ultima_utc']}). "
               f"Días con captura PROFECO: {len(cp['dias_con_captura_profeco'])} "
               f"({cp['dias_con_captura_profeco'][0]} a {cp['dias_con_captura_profeco'][-1]}).",
               f"- Intentos con error: {pi['integridad']['intentos_con_error']} · claves foráneas: "
               f"{'correctas' if pi['integridad']['claves_foraneas_ok'] else 'con huecos'}.",
               f"- Filas brutas {fmt(pd_['filas_brutas'])} → **{fmt(pd_['precios_profeco_unicos'])} precios únicos "
               f"anuncio·fecha de PROFECO**; {pd_['modelos']} modelos, {pd_['sucursales']} sucursales.",
               f"- Fecha de precio de {pd_['fecha_precio_min']} a **{pd_['fecha_precio_max']}** (último día publicado).",
               f"- Misma fecha con precio distinto entre capturas: {pd_['conflictos_misma_fecha_distinto_precio']} "
               f"(se conserva la captura más reciente).",
               f"- Zonas: {pd_['zonas']}.", '',
               tabla_md([{'ventana': k, 'precios': fmt(v)} for k, v in pd_['por_ventana_bf2026'].items()],
                        ['ventana', 'precios']),
               tabla_md([{'indicador': k, 'anuncios': v} for k, v in pi['series_bf2026'].items()],
                        ['indicador', 'anuncios']),
               'Precios únicos por fecha (últimos 10 días publicados): ' +
               ', '.join(f'{k}: {v}' for k, v in pd_['ultimos_10_dias'].items()) + '.', '',
               '## 3. Ofertas en línea', '']
    on = pi['online']
    lineas += [f"- Observaciones archivadas: {on['observaciones_intradia']} ({on['plataformas']}, {on['rango']}). "
               f"Con vendedor: {on['con_vendedor']} · con disponibilidad: {on['con_disponibilidad']}.",
               '- **Ofertas en línea completas y verificadas (vendedor, variante, inventario, total): 0.** '
               'Sears, Liverpool y Preciómetro quedaron en pausa desde el 14 de noviembre; Mercado Libre sin '
               'credenciales autorizadas; Amazon directo desactivado por decisión del equipo.', '',
               '## 4. QQP anual 2026', '']
    qq = r['qqp']
    lineas += [f"- Último estado de la vigilancia: `{qq.get('estado')}` · consultado {qq.get('consultado_utc')} · "
               f"última modificación del servidor {qq.get('ultima_modificacion')}.",
               f"- El índice histórico de datos abiertos responde HTTP 404 desde el 9 de noviembre. "
               f"El último dato QQP en el paquete es {next((f['fecha_max'] for f in p['por_fuente'] if f['fuente'] == 'qqp_cdmx'), '?')}: "
               'el archivo anual no cubre el Buen Fin 2026 y no hay series QQP 2026 evaluables.', '']
    if r.get('fly'):
        fl = r['fly']
        lineas += ['## 5. Copia del volumen de Fly', '',
                   f"`{fl['archivo']}` · SHA-256 `{fl['sha256']}` · integridad SQLite `{fl['integridad']}`.",
                   f"- Tablas: {fl['tablas']}.",
                   f"- Última captura {fl.get('ultima_captura_utc')} · último día de precio {fl.get('fecha_precio_max')}. "
                   'El colector en la nube nunca se habilitó; la API sirve este almacén congelado.', '']
    lineas += ['## 6. Archivos congelados', '',
               tabla_md([{'archivo': k, 'bytes': fmt(v['bytes']), 'sha256': f"`{v['sha256']}`"}
                         for k, v in r['manifiesto'].items()], ['archivo', 'bytes', 'sha256'])]
    ruta.write_text('\n'.join(lineas) + '\n', encoding='utf-8')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--corte', type=Path, required=True, help='Carpeta con las copias congeladas')
    ap.add_argument('--fecha', required=True, help='Fecha del corte (AAAA-MM-DD)')
    ap.add_argument('--salida', type=Path, default=RAIZ / 'reports')
    a = ap.parse_args(argv)
    corte = a.corte.resolve()
    paquete = next(corte.glob('sconto_colab_*.zip'))
    piloto = corte / 'piloto_profeco_intradia.sqlite3'
    fly = corte / 'fly' / 'intradia.sqlite3'
    qqp = corte / 'qqp_estado.json'

    r = {'fecha_corte': a.fecha, 'generado_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
         'carpeta_corte': corte.relative_to(RAIZ).as_posix() if corte.is_relative_to(RAIZ) else str(corte)}
    r['paquete'] = auditar_paquete(paquete)
    eventos = pd.read_parquet(io.BytesIO(zipfile.ZipFile(paquete).read('eventos.parquet')))
    r['piloto'] = auditar_piloto(piloto, eventos)
    r['fly'] = auditar_fly(fly) if fly.exists() else None
    r['qqp'] = json.loads(qqp.read_text(encoding='utf-8')) if qqp.exists() else {}
    r['manifiesto'] = {p.relative_to(corte).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha256(p)}
                       for p in sorted(corte.rglob('*')) if p.is_file() and p.name != 'MANIFIESTO.json'}

    a.salida.mkdir(parents=True, exist_ok=True)
    base = a.salida / f'auditoria_corte_final_{a.fecha}'
    base.with_suffix('.json').write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    escribir_md(r, base.with_suffix('.md'))
    (corte / 'MANIFIESTO.json').write_text(json.dumps({'fecha_corte': a.fecha, 'archivos': r['manifiesto']},
                                                      ensure_ascii=False, indent=2), encoding='utf-8')
    print(base.with_suffix('.md'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
