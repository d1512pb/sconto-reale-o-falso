"""Normalización de texto y extracción de códigos de modelo (QQP, Preciómetro, ML, Amazon).

Se conserva siempre el texto original; lo normalizado sólo sirve para comparar.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

import pandas as pd

ESTADOS_CDMX = {'CIUDAD DE MEXICO', 'DISTRITO FEDERAL', 'CDMX'}


def normalizar(value) -> str:
    """Idéntica a la del Avance 1: mayúsculas, sin acentos, espacios colapsados."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ''
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(value).upper()) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', value).strip()


def id_estable(values) -> str:
    """Idéntica a la del Avance 1 (producto_id, sucursal_id, serie_id)."""
    return hashlib.sha256(json.dumps(list(values), ensure_ascii=True).encode()).hexdigest()[:20]


def compacto(texto) -> str:
    """'Hw-t420' → 'HWT420'; '65 Ur 7800 Psb' → '65UR7800PSB'; 'Tab A9+' → 'TABA9PLUS' (el + es otro modelo)."""
    return re.sub(r'[^A-Z0-9]', '', normalizar(texto).replace('+', 'PLUS'))


# Tokens que no son modelo aunque mezclen letras y números
_UNIDADES = re.compile(r'^(\d+(\.\d+)?)(GB|TB|MB|MP|W|WRMS|H|HZ|MM|MAH|K|G|PLGS?|PULGADAS|V|IN)$')
_NO_CODIGO = {'USB', 'BLUETOOTH', 'SMART', 'TV', 'LED', 'QLED', 'OLED', 'ULED', 'QNED', 'CRYSTAL', 'MINILED',
              'ANDROID', 'WINDOWS', 'LAPTOP', 'COLOR', 'SONIDO', 'POTENCIA', 'PUERTO', 'MEMORIA', 'INTERNA', 'RAM',
              'DURACION', 'MEGAPIXELES', 'MEGA', 'LENTE', 'ZOOM', 'FORMATO', 'CAMARA', 'DISCO', 'CDS', 'MP3'}


def segmentos_qqp(presentacion: str) -> list[str]:
    """Divide la presentación de QQP en segmentos ('. ' o un punto pegado a una letra)."""
    texto = str(presentacion or '').strip()
    return [s.strip() for s in re.split(r'\.\s+|\.(?=[A-Za-z])', texto) if s.strip()]


def es_codigo(token: str) -> bool:
    palabras = normalizar(token).split()
    if palabras and palabras[0] in _NO_CODIGO:
        return False
    t = compacto(token)
    if len(t) < 4 or t in _NO_CODIGO or _UNIDADES.match(t):
        return False
    return bool(re.search(r'[A-Z]', t) and re.search(r'\d', t))


def modelo_qqp(presentacion: str) -> dict:
    """Extrae el nombre/modelo principal y códigos alternos de una presentación QQP.

    Ej.: 'Galaxy Tab A9. Sm-x110. 8.7 Plgs...' → principal 'Galaxy Tab A9', códigos ['SMX110'].
         'Express 4k o Rok3940mx' → principal 'Express 4k', alternos ['ROK3940MX'].
    """
    segs = segmentos_qqp(presentacion)
    if not segs:
        return dict(modelo_texto='', modelo_normalizado='', codigos=[])
    principal_txt, *resto = segs
    alternativas = [a.strip() for a in re.split(r'\s+o\s+', principal_txt, flags=re.I) if a.strip()]
    principal = alternativas[0]
    codigos = []
    for a in alternativas[1:]:
        codigos.append(compacto(a))
    for s in resto[:3]:  # los códigos van al inicio; después vienen características
        for a in re.split(r'\s+o\s+', s, flags=re.I):
            if es_codigo(a) and len(a.split()) <= 2:
                codigos.append(compacto(a))
    # Un código pegado al nombre: 'Ideapad Slim 3 15ian8' → también '15IAN8'
    for tok in principal.split():
        if es_codigo(tok) and compacto(tok) != compacto(principal):
            codigos.append(compacto(tok))
    vistos, unicos = set(), []
    for c in codigos:
        if c and c not in vistos and c != compacto(principal):
            vistos.add(c)
            unicos.append(c)
    return dict(modelo_texto=principal, modelo_normalizado=compacto(principal), codigos=unicos)


_RE_GB = re.compile(r'(\d{2,4})\s*-?\s*(GB|TB)\b')
_RE_RAM = re.compile(r'(?:RAM\s*(?:DE\s*)?(\d{1,2})\s*-?\s*GB|(\d{1,2})\s*-?\s*GB\s*(?:DE\s*)?RAM)')


def capacidades(texto: str) -> dict:
    """Almacenamiento y RAM en GB a partir de un texto libre (QQP o nombre de tienda)."""
    t = normalizar(texto).replace('-', ' ')
    ram = None
    m = _RE_RAM.search(t)
    if m:
        ram = int(m.group(1) or m.group(2))
    almac = []
    for n, u in _RE_GB.findall(t):
        gb = int(n) * (1024 if u == 'TB' else 1)
        if ram is not None and gb == ram:
            continue
        almac.append(gb)
    # 'Micro Sd Hasta 1 Tb' no es la memoria del equipo
    if 'HASTA' in t:
        hasta = {int(n) * (1024 if u == 'TB' else 1) for n, u in re.findall(r'HASTA\s*(\d+)\s*(GB|TB)', t)}
        almac = [a for a in almac if a not in hasta]
    return dict(almacenamiento_gb=max(almac) if almac else None, ram_gb=ram)


def tokens_slug(slug: str) -> list[str]:
    return [compacto(t) for t in re.split(r'[-_\s/]+', slug) if compacto(t)]


def aparece_en_tokens(clave: str, tokens: list[str], max_union=4) -> bool:
    """¿`clave` compacta es la unión de tokens consecutivos? Evita que 'MOTOG15' empate con 'MOTOG15POWER' y que
    'GALAXYTABA9' empate con 'galaxy-tab-a9-plus' (el token siguiente es un modificador de modelo)."""
    if not clave:
        return False
    for i in range(len(tokens)):
        acum = ''
        for j in range(i, min(i + max_union, len(tokens))):
            acum += tokens[j]
            if acum == clave:
                siguiente = tokens[j + 1] if j + 1 < len(tokens) else ''
                if siguiente in MODIFICADORES:
                    break
                return True
            if len(acum) >= len(clave):
                break
    return False


# Sufijos que cambian el modelo: 'Galaxy Tab A9' ≠ 'Galaxy Tab A9+' ≠ 'Redmi Note 14 Pro+'
MODIFICADORES = {'PLUS', 'PRO', 'MAX', 'ULTRA', 'LITE', 'MINI', 'FE', 'NEO', 'POWER', 'PRIME', 'EDGE', 'AIR', 'SE',
                 'XL', 'STYLUS', 'PLAY', 'FUSION'}
