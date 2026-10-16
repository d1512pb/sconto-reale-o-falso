"""Fase 1: lista de productos objetivo (la llave para cruzar fuentes).

Una fila por producto canónico:
- prioridad 1–3: referencia QQP del Avance 1 (1 = modelo de las 93 series, 2 = de las 298, 3 = resto, ordenado por
  observaciones). QQP a veces agrupa colores ("Color Blanca o Negra"); se respeta su agrupación y cada ficha externa
  conserva su propio id, así que el análisis puede separarlas. Capacidad o RAM distintas → `descartado`, nunca se unen.
- prioridad 4: ficha de tecnología de Preciómetro sin equivalente QQP (serie sólo en línea para el BF2026).

Confianza del emparejamiento QQP ↔ ficha externa:
- exacto: coincide un código de modelo (letras+dígitos, ≥5 caracteres) en el nombre/slug, la marca y la capacidad.
- probable: coincide sólo un nombre comercial ("Moto G15", "Echo Pop") o falta confirmar capacidad → revisión manual.
- descartado: capacidad/RAM distinta u otra variante incompatible (se guarda para auditoría, no se usa).
"""
from __future__ import annotations

import re

import pandas as pd

from sconto.almacen import leer_bronze
from sconto.normalizar import aparece_en_tokens, capacidades, compacto, modelo_qqp, normalizar, tokens_slug
from sconto.rutas import AVANCE1, CONFIG, REPORTS

# Familias de producto QQP ↔ Preciómetro, para no emparejar una bocina con una funda del mismo modelo
FAMILIA_QQP = {
    'PANTALLAS': 'pantalla', 'CELULARES': 'celular', 'TABLET': 'tablet', 'COMPUTADORAS PORTATILES': 'laptop',
    'BARRA DE SONIDO': 'audio', 'BOCINAS PORTATILES': 'audio', 'MINIBOCINAS PORTATILES BLUETOOTH': 'audio',
    'COMPONENTES DE AUDIO': 'audio', 'ASISTENTES DE VOZ': 'asistente', 'REPRODUCTORES STREAMING': 'streaming',
    'CAMARAS DIGITALES': 'camara', 'VIDEOCAMARAS': 'camara',
}


def familia_preciometro(path: str, nombre: str) -> str:
    p, n = str(path or ''), normalizar(nombre)
    if 'televisores' in p:
        return 'streaming' if re.search(r'STREAMING|FIRE TV|ROKU|CHROMECAST', n) else 'pantalla'
    for clave, fam in (('smartphones', 'celular'), ('tablets', 'tablet'), ('laptops', 'laptop'), ('audio', 'audio'),
                       ('asistentes-voz', 'asistente'), ('camaras-digitales', 'camara')):
        if clave in p:
            return fam
    if 'hogar-inteligente' in p and re.search(r'ECHO|ALEXA|NEST', n):
        return 'asistente'
    return 'otra'


def referencias_qqp() -> pd.DataFrame:
    limpios = pd.read_parquet(AVANCE1 / '05_observaciones_limpias.parquet',
                              columns=['producto_id', 'producto', 'marca', 'presentacion', 'n_producto', 'serie_id',
                                       'sucursal_id'])
    series = pd.read_csv(AVANCE1 / '06_variables_por_serie.csv', usecols=['producto_id', 'cobertura_ahorro'])
    p93 = set(pd.read_csv(AVANCE1 / '08_metadatos_modelo.csv', usecols=['producto_id']).producto_id)
    p298 = set(series.loc[series.cobertura_ahorro, 'producto_id'])
    g = limpios.groupby('producto_id').agg(producto=('producto', 'first'), marca=('marca', 'first'),
                                           presentacion=('presentacion', 'first'), n_producto=('n_producto', 'first'),
                                           observaciones_qqp_2025=('producto', 'size'),
                                           series_qqp_2025=('serie_id', 'nunique'),
                                           sucursales_qqp_2025=('sucursal_id', 'nunique'))
    g['prioridad'] = [1 if i in p93 else 2 if i in p298 else 3 for i in g.index]
    m = g.presentacion.map(modelo_qqp)
    g['modelo_texto'] = m.map(lambda x: x['modelo_texto'])
    g['modelo_normalizado'] = m.map(lambda x: x['modelo_normalizado'])
    g['codigos_alternos'] = m.map(lambda x: ';'.join(x['codigos']))
    cap = g.presentacion.map(capacidades)
    g['almacenamiento_gb'] = cap.map(lambda x: x['almacenamiento_gb'])
    g['ram_gb'] = cap.map(lambda x: x['ram_gb'])
    g['marca_norm'] = g.marca.map(lambda x: compacto(str(x).split('.')[0]))
    g['familia'] = g.n_producto.map(FAMILIA_QQP).fillna('otra')
    return g.reset_index().sort_values(['prioridad', 'observaciones_qqp_2025'], ascending=[True, False])


MARCAS_EQUIVALENTES = {'ALEXA': {'AMAZON', 'ALEXA', 'ECHO'}, 'GOPRO': {'GOPRO'}, 'FUJIFILM': {'FUJIFILM', 'INSTAX'},
                       'SONY': {'SONY'}, 'GO': {'GOPRO'}}


def _marca_coincide(marca_qqp: str, texto_tokens: list[str], marca_pm: str) -> bool:
    opciones = MARCAS_EQUIVALENTES.get(marca_qqp, {marca_qqp})
    pm = compacto(marca_pm)
    return any(o == pm or o in texto_tokens for o in opciones)


def candidatos(refs: pd.DataFrame, pm: pd.DataFrame) -> pd.DataFrame:
    """Todas las parejas (referencia QQP, ficha Preciómetro) con alguna clave de modelo en común."""
    pm = pm.copy()
    pm['tokens'] = [tokens_slug(f"{r.url.rsplit('/', 1)[-1]} {r.nombre or ''} {r.palabras_claves or ''}")
                    for r in pm.itertuples()]
    pm['familia'] = [familia_preciometro(p, n) for p, n in zip(pm.categoria_path, pm.nombre)]
    filas = []
    for r in refs.itertuples():
        claves = [k for k in [r.modelo_normalizado, *str(r.codigos_alternos).split(';')] if k and len(k) >= 3]
        for p in pm.itertuples():
            hits = [k for k in claves if aparece_en_tokens(k, p.tokens)]
            if not hits:
                continue
            marca_ok = _marca_coincide(r.marca_norm, p.tokens, p.marca or '')
            cap = capacidades(f'{p.nombre} {p.capacidad or ""}')
            alm_ok = None if r.almacenamiento_gb is None or pd.isna(r.almacenamiento_gb) or cap['almacenamiento_gb'] is None \
                else int(r.almacenamiento_gb) == int(cap['almacenamiento_gb'])
            ram_ok = None if r.ram_gb is None or pd.isna(r.ram_gb) or cap['ram_gb'] is None \
                else int(r.ram_gb) == int(cap['ram_gb'])
            codigo = any(re.search(r'[A-Z]', k) and re.search(r'\d', k) and len(k) >= 5 for k in hits)
            familia_ok = r.familia == 'otra' or p.familia in ('otra', r.familia)
            if alm_ok is False or ram_ok is False:
                conf, motivo = 'descartado', 'capacidad/RAM distinta'
            elif not familia_ok:
                conf, motivo = 'descartado', f'familia distinta ({r.familia} vs {p.familia})'
            elif not marca_ok:
                conf, motivo = 'descartado', 'marca no coincide'
            elif codigo and alm_ok is not False and (r.almacenamiento_gb is None or pd.isna(r.almacenamiento_gb) or alm_ok):
                conf, motivo = 'exacto', 'código de modelo + marca' + (' + capacidad' if alm_ok else '')
            else:
                conf, motivo = 'probable', 'nombre comercial' if not codigo else 'código sin confirmar capacidad'
            filas.append(dict(qqp_producto_id=r.producto_id, prioridad=r.prioridad, marca_qqp=r.marca,
                              descripcion_qqp=f'{r.producto} | {r.marca} | {r.presentacion}',
                              preciometro_id=p.preciometro_id, preciometro_nombre=p.nombre, preciometro_url=p.url,
                              categoria_preciometro=p.categoria_path, claves=';'.join(hits),
                              almacenamiento_qqp=r.almacenamiento_gb, almacenamiento_pm=cap['almacenamiento_gb'],
                              ram_qqp=r.ram_gb, ram_pm=cap['ram_gb'], confianza_match=conf, motivo=motivo,
                              asins=p.asins, mlm_ids=p.mlm_ids))
    return pd.DataFrame(filas)


def _unir_ids(serie) -> str:
    ids = sorted({x for v in serie.dropna() for x in str(v).split(';') if x})
    return ';'.join(ids)


def construir(guardar=True) -> tuple[pd.DataFrame, pd.DataFrame]:
    refs = referencias_qqp()
    pm = leer_bronze('preciometro_productos')
    if len(pm):
        pm = pm.sort_values('fecha_captura').drop_duplicates('preciometro_id', keep='last')
        pm = pm.loc[pm.es_tecnologia.astype(bool)]
    cand = candidatos(refs, pm) if len(pm) else pd.DataFrame()
    filas = []
    usados = set()
    for r in refs.itertuples():
        c = cand.loc[cand.qqp_producto_id.eq(r.producto_id)] if len(cand) else pd.DataFrame()
        buenos = c.loc[c.confianza_match.isin(['exacto', 'probable'])] if len(c) else c
        conf = 'exacto' if len(buenos) and buenos.confianza_match.eq('exacto').any() else \
            'probable' if len(buenos) else ('descartado' if len(c) else 'sin_candidato')
        usar = buenos.loc[buenos.confianza_match.eq(conf)] if conf in ('exacto', 'probable') else buenos
        usados.update(usar.preciometro_id if len(usar) else [])
        marca = str(r.marca).split('.')[0].strip().upper()
        filas.append(dict(
            producto_canonico_id=f'Q{r.prioridad}-{r.marca_norm}-{r.modelo_normalizado}-{r.producto_id[:6]}',
            origen='qqp', marca=marca, modelo_normalizado=r.modelo_normalizado, codigos_alternos=r.codigos_alternos,
            descripcion_qqp=f'{r.producto} | {r.marca} | {r.presentacion}', categoria=r.producto, familia=r.familia,
            prioridad=r.prioridad, qqp_producto_id=r.producto_id, observaciones_qqp_2025=r.observaciones_qqp_2025,
            series_qqp_2025=r.series_qqp_2025, almacenamiento_gb=r.almacenamiento_gb, ram_gb=r.ram_gb,
            preciometro_ids=_unir_ids(usar.preciometro_id) if len(usar) else '',
            preciometro_url=_unir_ids(usar.preciometro_url) if len(usar) else '',
            mlm_ids=_unir_ids(usar.mlm_ids) if len(usar) else '', asins=_unir_ids(usar.asins) if len(usar) else '',
            confianza_match=conf,
            notas=('QQP agrupa colores; cada ficha externa conserva su id. ' if re.search(r'\bO\b', normalizar(r.presentacion)) else '')
                  + ('ASIN/MLM tomados de las ofertas que agrupa Preciómetro. ' if len(usar) else '')
                  + ('' if len(usar) else 'Sin ficha externa emparejada todavía.')))
    for p in pm.itertuples() if len(pm) else []:
        if p.preciometro_id in usados:
            continue
        fam = familia_preciometro(p.categoria_path, p.nombre)
        if fam == 'otra':
            continue
        filas.append(dict(
            producto_canonico_id=f'P4-{p.preciometro_id}', origen='preciometro',
            marca=str(p.marca or '').upper(), modelo_normalizado=compacto(p.modelo) if p.modelo else '',
            codigos_alternos='', descripcion_qqp='', descripcion_externa=p.nombre, categoria=p.categoria,
            familia=fam, prioridad=4, qqp_producto_id='', observaciones_qqp_2025=0, series_qqp_2025=0,
            preciometro_ids=p.preciometro_id, preciometro_url=p.url, mlm_ids=p.mlm_ids or '', asins=p.asins or '',
            confianza_match='exacto', notas='Ficha de Preciómetro sin equivalente QQP: serie sólo en línea.'))
    prod = pd.DataFrame(filas)
    if guardar:
        prod.to_csv(CONFIG / 'productos_objetivo.csv', index=False, encoding='utf-8')
        if len(cand):
            cand.to_csv(REPORTS / 'candidatos_emparejamiento.csv', index=False, encoding='utf-8')
            cand.loc[cand.confianza_match.eq('probable')].to_csv(REPORTS / 'matches_para_revisar.csv', index=False,
                                                                 encoding='utf-8')
    return prod, cand


if __name__ == '__main__':
    prod, cand = construir()
    print(prod.groupby(['prioridad', 'confianza_match']).size().unstack(fill_value=0))
    print('candidatos:', len(cand))
