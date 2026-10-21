"""Fase 1: lista de productos objetivo (la llave para cruzar fuentes).

Una fila por producto canónico:
- prioridad 1–3: referencia QQP del Avance 1 (1 = modelo de las 93 series, 2 = de las 298, 3 = resto, ordenado por
  observaciones). QQP a veces agrupa colores ("Color Blanca o Negra"); se respeta su agrupación y cada ficha externa
  conserva su propio id, así que el análisis puede separarlas. Capacidad o RAM distintas → `descartado`, nunca se unen.
- prioridad 4: ficha de tecnología de Preciómetro sin equivalente QQP (serie sólo en línea para el BF2026).

Confianza del emparejamiento QQP ↔ ficha externa:
- exacto: código de fabricante y marca coinciden, sin variantes pendientes ni ids externos en conflicto.
- probable: nombre comercial, evidencia sólo en slug/keywords o variante sin confirmar → revisión manual, sin autoasignar.
- descartado: capacidad/RAM distinta u otra variante incompatible (se guarda para auditoría, no se usa).
"""
from __future__ import annotations

import re

import pandas as pd

from sconto.almacen import leer_bronze
from sconto.normalizar import (MODIFICADORES, aparece_en_tokens, capacidades, compacto, es_codigo, modelo_qqp,
                              normalizar, tokens_slug, variantes)
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


def _texto(valor) -> str:
    return '' if valor is None or pd.isna(valor) else str(valor)


def _codigos(texto: str) -> set[str]:
    texto = normalizar(texto)
    texto = re.sub(r'\b([A-Z]{1,3})\s+([A-Z]+\d{3,}[A-Z0-9]*)\b', r'\1-\2', texto)
    return {compacto(token) for token in re.findall(r'[A-Z0-9]+(?:[-/][A-Z0-9]+)*', texto)
            if len(compacto(token)) >= 5 and es_codigo(token)}


def _sufijos_modelo(modelo: str, texto: str) -> set[str]:
    base = modelo
    patron = '|'.join(sorted(MODIFICADORES, key=len, reverse=True))
    while re.search(rf'(?:{patron})$', base):
        base = re.sub(rf'(?:{patron})$', '', base)
    tokens = tokens_slug(texto)
    sufijos = set()
    for inicio in range(len(tokens)):
        for fin in range(inicio + 1, min(inicio + 6, len(tokens)) + 1):
            union = ''.join(tokens[inicio:fin])
            if union.startswith(base) and re.fullmatch(rf'(?:{patron})*', union[len(base):]):
                siguiente = fin
                while siguiente < len(tokens) and tokens[siguiente] in MODIFICADORES:
                    siguiente += 1
                sufijos.add(union[len(base):] + ''.join(tokens[fin:siguiente]))
    return sufijos


def _comparar_variantes(qqp: dict, externa: dict) -> tuple[bool, bool]:
    distinta, ambigua = False, False
    for campo, valores in qqp.items():
        otros = externa[campo]
        if len(valores) > 1 or len(otros) > 1:
            ambigua = True
        elif valores and otros and valores != otros:
            distinta = True
        elif bool(valores) != bool(otros):
            ambigua = True
    return distinta, ambigua


def candidatos(refs: pd.DataFrame, pm: pd.DataFrame) -> pd.DataFrame:
    """Todas las parejas (referencia QQP, ficha Preciómetro) con alguna clave de modelo en común."""
    pm = pm.copy()
    pm['familia'] = [familia_preciometro(p, n) for p, n in zip(pm.categoria_path, pm.nombre)]
    indice_claves = []
    for producto in pm.itertuples():
        campos = [_texto(producto.nombre), _texto(getattr(producto, 'modelo', '')),
                  _texto(producto.url).rsplit('/', 1)[-1], _texto(producto.palabras_claves)]
        claves_producto = set()
        for campo in campos:
            tokens = tokens_slug(campo)
            for inicio in range(len(tokens)):
                for fin in range(inicio + 1, min(inicio + 4, len(tokens)) + 1):
                    if fin == len(tokens) or tokens[fin] not in MODIFICADORES:
                        claves_producto.add(''.join(tokens[inicio:fin]))
        indice_claves.append(claves_producto)
    pm['claves_busqueda'] = indice_claves
    filas = []
    for r in refs.itertuples():
        claves = [k for k in [r.modelo_normalizado, *_texto(r.codigos_alternos).split(';')] if k and len(k) >= 3]
        codigos = {clave for clave in claves[1:] if es_codigo(clave) and len(clave) >= 5}
        if es_codigo(r.modelo_texto):
            codigos.update(_codigos(r.modelo_texto))
        variante_qqp = variantes(r.presentacion)
        for campo in ('almacenamiento_gb', 'ram_gb'):
            valor = getattr(r, campo)
            if not variante_qqp[campo] and pd.notna(valor):
                variante_qqp[campo].add(int(valor))
        for p in pm.itertuples():
            campos = [_texto(p.nombre), _texto(getattr(p, 'modelo', '')),
                      _texto(p.url).rsplit('/', 1)[-1], _texto(p.palabras_claves)]
            hits = [clave for clave in claves if clave in p.claves_busqueda]
            if not hits:
                continue
            texto = ' '.join(campos[:2] + [_texto(getattr(p, campo, ''))
                                           for campo in ('capacidad', 'color', 'variante')])
            marca_ok = _marca_coincide(r.marca_norm, tokens_slug(texto), _texto(p.marca))
            cap = capacidades(texto)
            variante_pm = variantes(texto)
            distinta, ambigua = _comparar_variantes(variante_qqp, variante_pm)
            if r.familia in ('tablet', 'celular', 'laptop'):
                ambigua |= any(not variante_qqp[campo] or not variante_pm[campo]
                               for campo in ('almacenamiento_gb', 'ram_gb'))
            externos = _codigos(campos[1])
            prefijos = {re.match(r'[A-Z]*', codigo).group() for codigo in codigos}
            externos.update(codigo for codigo in _codigos(campos[0])
                            if re.match(r'[A-Z]*', codigo).group() in prefijos)
            codigo_ok = bool(codigos & externos)
            modelo_distinto = bool(externos and codigos and not codigo_ok)
            sufijo_qqp = _sufijos_modelo(r.modelo_normalizado, r.modelo_texto)
            sufijo_pm = _sufijos_modelo(r.modelo_normalizado, ' '.join(campos[:2]))
            sufijo_distinto = bool(sufijo_qqp and sufijo_pm and sufijo_qqp != sufijo_pm)
            familia_ok = r.familia == 'otra' or p.familia in ('otra', r.familia)
            if distinta:
                conf, motivo = 'descartado', 'capacidad/RAM/color/generación distinta'
            elif not familia_ok:
                conf, motivo = 'descartado', f'familia distinta ({r.familia} vs {p.familia})'
            elif not marca_ok:
                conf, motivo = 'descartado', 'marca no coincide'
            elif modelo_distinto or (sufijo_distinto and not codigo_ok):
                conf, motivo = 'descartado', 'modelo/código de fabricante distinto'
            elif ambigua or sufijo_distinto or len(externos) > 1:
                conf, motivo = 'probable', 'variante ambigua o sin confirmar'
            elif codigo_ok:
                conf, motivo = 'exacto', 'código de fabricante + marca + variantes confirmadas'
            else:
                conf, motivo = 'probable', 'nombre comercial o código sólo en slug/keywords'
            filas.append(dict(qqp_producto_id=r.producto_id, prioridad=r.prioridad, marca_qqp=r.marca,
                              descripcion_qqp=f'{r.producto} | {r.marca} | {r.presentacion}',
                              preciometro_id=p.preciometro_id, preciometro_nombre=p.nombre, preciometro_url=p.url,
                              categoria_preciometro=p.categoria_path, claves=';'.join(hits),
                              almacenamiento_qqp=r.almacenamiento_gb, almacenamiento_pm=cap['almacenamiento_gb'],
                              ram_qqp=r.ram_gb, ram_pm=cap['ram_gb'], confianza_match=conf, motivo=motivo,
                              asins=p.asins, mlm_ids=p.mlm_ids))
    resultado = pd.DataFrame(filas)
    if len(resultado):
        identidad = ['marca', 'familia', 'modelo_normalizado', 'codigos_alternos', 'almacenamiento_gb', 'ram_gb']
        aceptados = resultado.loc[resultado.confianza_match.ne('descartado')].join(
            refs.set_index('producto_id')[identidad], on='qqp_producto_id')
        conflictos = _conflictos_ids(aceptados, ('preciometro_id', 'asins', 'mlm_ids'))
        if conflictos:
            resultado.loc[sorted(conflictos), 'confianza_match'] = 'probable'
            resultado.loc[sorted(conflictos), 'motivo'] += '; id externo compartido incompatible o sin confirmar'
    return resultado


def _unir_ids(serie) -> str:
    ids = sorted({x.strip() for v in serie.dropna() for x in str(v).split(';') if x.strip()})
    return ';'.join(ids)


def _identidad_compatible(primera, segunda) -> bool:
    if primera.marca != segunda.marca or primera.familia != segunda.familia:
        return False
    if not primera.modelo_normalizado or primera.modelo_normalizado != segunda.modelo_normalizado:
        return False
    codigos_primera = set(_texto(primera.codigos_alternos).split(';')) - {''}
    codigos_segunda = set(_texto(segunda.codigos_alternos).split(';')) - {''}
    if codigos_primera != codigos_segunda and not codigos_primera & codigos_segunda:
        return False
    for campo in ('almacenamiento_gb', 'ram_gb'):
        if _texto(getattr(primera, campo)) != _texto(getattr(segunda, campo)):
            return False
    return variantes(_texto(primera.descripcion_qqp) or _texto(getattr(primera, 'descripcion_externa', ''))) == variantes(
        _texto(segunda.descripcion_qqp) or _texto(getattr(segunda, 'descripcion_externa', '')))


def _conflictos_ids(filas: pd.DataFrame, columnas) -> set:
    conflictos = set()
    for columna in columnas:
        propietarios = {}
        for fila in filas.itertuples():
            for externo in _texto(getattr(fila, columna)).split(';'):
                externo = externo.strip().upper().replace('MLM-', 'MLM')
                if not externo:
                    continue
                for anterior in propietarios.get(externo, []):
                    origenes = {getattr(anterior, 'origen', ''), getattr(fila, 'origen', '')}
                    if origenes == {'qqp', 'preciometro'} and set(_texto(anterior.preciometro_ids).split(';')) & set(
                            _texto(fila.preciometro_ids).split(';')):
                        continue
                    if not _identidad_compatible(anterior, fila):
                        conflictos.update((anterior.Index, fila.Index))
                propietarios.setdefault(externo, []).append(fila)
    return conflictos


def _revisar_ids(prod: pd.DataFrame, cand: pd.DataFrame) -> None:
    """Retiene propuestas auditables; sólo publica enlaces inequívocos para el cruce automático."""
    if prod.empty:
        return
    columnas = ('preciometro_ids', 'asins', 'mlm_ids')
    for columna in columnas:
        prod[f'{columna}_candidatos'] = prod[columna]
    conflictos = _conflictos_ids(prod, columnas)
    if conflictos:
        indices = sorted(conflictos)
        prod.loc[indices, 'confianza_match'] = 'probable'
        prod.loc[indices, 'notas'] += 'Id externo compartido entre identidades incompatibles o sin confirmar. '
        if len(cand):
            afectados = cand.qqp_producto_id.isin(prod.loc[indices, 'qqp_producto_id'])
            afectados |= cand.preciometro_id.isin(
                prod.loc[indices, 'preciometro_ids_candidatos'].str.split(';').explode())
            afectados &= cand.confianza_match.ne('descartado')
            cand.loc[afectados, 'confianza_match'] = 'probable'
            cand.loc[afectados, 'motivo'] += '; id externo compartido incompatible o sin confirmar'
    pendientes = prod.confianza_match.ne('exacto')
    prod.loc[pendientes, ['asins', 'mlm_ids']] = ''
    prod.loc[pendientes & prod.origen.eq('qqp'), ['preciometro_ids', 'preciometro_url']] = ''


def construir(guardar=True) -> tuple[pd.DataFrame, pd.DataFrame]:
    refs = referencias_qqp()
    pm = leer_bronze('preciometro_productos')
    if len(pm):
        pm = pm.sort_values('fecha_captura').drop_duplicates('preciometro_id', keep='last')
        pm = pm.loc[pm.es_tecnologia.astype(bool)]
    cand = candidatos(refs, pm) if len(pm) else pd.DataFrame()
    filas = []
    for r in refs.itertuples():
        c = cand.loc[cand.qqp_producto_id.eq(r.producto_id)] if len(cand) else pd.DataFrame()
        buenos = c.loc[c.confianza_match.isin(['exacto', 'probable'])] if len(c) else c
        conf = 'exacto' if len(buenos) and buenos.confianza_match.eq('exacto').any() else \
            'probable' if len(buenos) else ('descartado' if len(c) else 'sin_candidato')
        usar = buenos.loc[buenos.confianza_match.eq(conf)] if conf in ('exacto', 'probable') else buenos
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
        fam = familia_preciometro(p.categoria_path, p.nombre)
        if fam == 'otra':
            continue
        filas.append(dict(
            producto_canonico_id=f'P4-{p.preciometro_id}', origen='preciometro',
            marca=normalizar(p.marca), modelo_normalizado=compacto(_texto(p.modelo) or p.nombre),
            codigos_alternos=';'.join(sorted(_codigos(_texto(p.modelo)))),
            descripcion_qqp='', descripcion_externa=p.nombre, categoria=p.categoria,
            familia=fam, prioridad=4, qqp_producto_id='', observaciones_qqp_2025=0, series_qqp_2025=0,
            preciometro_ids=p.preciometro_id, preciometro_url=p.url,
            mlm_ids=_texto(p.mlm_ids), asins=_texto(p.asins),
            confianza_match='probable',
            notas='Ficha de Preciómetro sin equivalente QQP confirmado; variante e ids externos pendientes.'))
    prod = pd.DataFrame(filas)
    _revisar_ids(prod, cand)
    if guardar:
        from sconto.validar_mapeos import aplicar_validaciones
        prod = aplicar_validaciones(prod, CONFIG / 'mapeos_validados.csv')
    if len(prod):
        usados = set(_unir_ids(prod.loc[prod.origen.eq('qqp') & prod.confianza_match.eq('exacto'),
                                       'preciometro_ids']).split(';')) - {''}
        prod = prod.loc[~(prod.origen.eq('preciometro') & prod.preciometro_ids.isin(usados))].reset_index(drop=True)
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
