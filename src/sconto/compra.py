"""Búsqueda de candidatos y reglas explicables de precio para la futura app."""
from __future__ import annotations

import json
import re
from difflib import get_close_matches

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sconto.normalizar import normalizar


def atributos(texto):
    texto = normalizar(texto)
    texto = re.sub(r'AIRPODS\s*([234])\s*PRO', r'AIRPODS PRO \1', texto)
    texto = re.sub(r'AIRPODS\s*PRO\s*\(?\s*([234])(?:RA|DA|A|ER)\.?', r'AIRPODS PRO \1 ', texto)
    resultado = {}
    patrones = {
        'ram': r'\b(\d+)\s*GB\s*(?:DE\s*)?RAM\b',
        'disco': r'\b(\d+)\s*(GB|TB)\s*(?:DE\s*)?(?:SSD|HDD|EMMC)\b',
        'cpu': r'\b(I[3579](?:-\d{4,5}[A-Z]*)?|RYZEN\s*[3579])\b',
        'airpods': r'\bAIRPODS\s*(PRO\s*)?([234])\b',
        'color': r'\b(AZUL|NEGRO|BLANCO|GRIS|PLATA|ROSA)\b',
        'iphone': r'\bIPHONE\s*(\d{1,2}|SE)\s*(PRO\s*MAX|PRO|PLUS|MINI|AIR|E)?\b',
        'galaxy': r'\bGALAXY\s*(TAB\s*)?([ASM]\d{1,3})\s*(ULTRA|PLUS|FE\+?|LITE|\+)?',
        'ipad_tipo': r'\bIPAD\s+(AIR|PRO|MINI)\b',
    }
    for clave, patron in patrones.items():
        hallazgo = re.search(patron, texto)
        if hallazgo:
            if clave == 'disco':
                resultado[clave] = str(int(hallazgo[1]) * (1024 if hallazgo[2] == 'TB' else 1))
            elif clave == 'airpods':
                resultado[clave] = ('PRO' if hallazgo[1] else 'NORMAL') + hallazgo[2]
            elif clave == 'iphone':
                resultado[clave] = hallazgo[1] + (hallazgo[2] or '').replace(' ', '')
            elif clave == 'galaxy':
                resultado[clave] = ('TAB' if hallazgo[1] else '') + hallazgo[2] + (hallazgo[3] or '').replace('+', 'PLUS')
            else:
                resultado[clave] = hallazgo[1].replace(' ', '')
    resultado['paquete'] = bool(re.search(r'\b(?:PAQUETE|COMBO|HERVIDOR|CAFETERA)\b', texto))
    if 'disco' not in resultado:
        sin_ram = re.sub(patrones['ram'], '', texto)
        capacidades = [(int(n) * (1024 if unidad == 'TB' else 1)) for n, unidad in re.findall(r'\b(\d+)\s*(GB|TB)\b', sin_ram)]
        capacidades = [n for n in capacidades if n >= 32]
        if len(capacidades) == 1:
            resultado['disco'] = str(capacidades[0])
    return resultado


def contradicciones(a, b):
    conflictos = []
    for campo in a.keys() & b.keys():
        izquierda, derecha = a[campo], b[campo]
        if campo == 'cpu' and (izquierda.startswith(derecha) or derecha.startswith(izquierda)):
            continue
        if izquierda != derecha:
            conflictos.append(campo)
    return sorted(conflictos)


def identidad_oferta(nombre, titulo):
    a, b = atributos(nombre), atributos(titulo)
    conflictos = contradicciones(a, b)
    if conflictos:
        return 'conflicto', ', '.join(conflictos)
    if a['paquete'] or b['paquete']:
        return 'pendiente', 'Paquete: verificar todos los componentes'
    if normalizar(nombre) == normalizar(titulo):
        return 'compatible_texto', 'Título idéntico; falta comprobación independiente de SKU y condiciones'
    campos = set(a) - {'paquete', 'color'}
    if campos and campos <= set(b):
        palabras = set(normalizar(nombre).split()) & set(normalizar(titulo).split())
        familias = set(re.findall(r'\b(?:LENOVO|HP|DELL|ACER|ASUS|APPLE|IDEAPAD|SLIM|VIVOBOOK|PAVILION|INSPIRON|MACBOOK|CHROMEBOOK)\b', normalizar(nombre)))
        presentes = set(re.findall(r'[A-Z0-9]+', normalizar(titulo)))
        # La regla de atributos parcial sólo se validó para computadoras y AirPods.
        dominio = bool(re.search(r'\b(LAPTOP|PORTATIL|COMPUTADORA|IDEAPAD|MACBOOK|CHROMEBOOK|AIRPODS)\b', normalizar(nombre)))
        if len(palabras) >= 3 and familias <= presentes and dominio:
            return 'compatible_texto', 'Atributos explícitos compatibles; confirmar SKU antes de comprar'
    return 'pendiente', 'Descripción insuficiente para confirmar variante'


class Buscador:
    def __init__(self, productos):
        self.productos = productos.sort_values('producto_canonico_id').reset_index(drop=True).copy()
        self.vectorizador = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), lowercase=False)
        textos = self.productos.nombre.map(normalizar)
        self.matriz = self.vectorizador.fit_transform(textos)

    def buscar(self, consulta, limite=5):
        texto = normalizar(consulta)
        columnas = list(self.productos.columns) + ['similitud']
        if len(texto) < 3:
            return pd.DataFrame(columns=columnas)
        puntajes = cosine_similarity(self.vectorizador.transform([texto]), self.matriz)[0]
        datos = self.productos.assign(similitud=puntajes)
        solicitados = atributos(texto)
        def cumple_modelo(nombre):
            candidato = atributos(nombre)
            return not contradicciones(solicitados, candidato) and all(
                clave not in solicitados or candidato.get(clave) == solicitados[clave]
                for clave in ('iphone', 'galaxy', 'ipad_tipo'))
        datos = datos.loc[datos.nombre.map(cumple_modelo)]
        palabras = {p for p in re.findall(r'[A-Z0-9]+', texto) if len(p) >= 3}
        def ancla(nombre):
            tokens = re.findall(r'[A-Z0-9]+', normalizar(nombre))
            return bool(palabras & set(tokens)) or any(get_close_matches(p, tokens, n=1, cutoff=.85) for p in palabras if len(p) >= 4)
        datos = datos.loc[datos.nombre.map(ancla)]
        return datos.loc[datos.similitud.ge(.15)].sort_values(
            ['similitud', 'producto_canonico_id'], ascending=[False, True]).head(limite).copy()

    def indice(self):
        matriz = self.matriz.tocsr()
        return dict(version='sconto-busqueda-v1', normalizacion='Mayúsculas sin acentos, espacios compactados',
                    algoritmo='TF-IDF char_wb 3..5, l2, coseno >=0.15; ancla léxica exacta >=3 caracteres o difflib >=0.85 con >=4; sin contradicciones; modelo móvil explícito obligatorio',
                    ids=self.productos.producto_canonico_id.tolist(),
                    vocabulario={k: int(v) for k, v in self.vectorizador.vocabulary_.items()}, idf=self.vectorizador.idf_.tolist(),
                    matriz_csr=dict(data=matriz.data.tolist(), indices=matriz.indices.tolist(),
                                    indptr=matriz.indptr.tolist(), shape=list(matriz.shape)))


def evaluar_precio(oferta, referencia, fecha_consulta, umbral=5, max_edad=1):
    motivos = []
    fecha = pd.to_datetime(oferta.get('fecha_precio'), errors='coerce')
    edad = (pd.Timestamp(fecha_consulta).normalize() - fecha).days if pd.notna(fecha) else None
    precio = oferta.get('precio')
    if precio is None or not np.isfinite(precio) or precio <= 0:
        motivos.append('precio_invalido')
    if edad is None or not 0 <= edad <= max_edad:
        motivos.append('captura_fuera_de_vigencia')
    if oferta.get('identidad_oferta') != 'compatible_texto':
        motivos.append('variante_no_comparable')
    if referencia is None:
        motivos.append('sin_historia_comparable')
    else:
        if not referencia.get('cobertura_base') or not referencia.get('base_cerrada'):
            motivos.append('base_insuficiente_o_abierta')
        if referencia.get('moneda') != oferta.get('moneda') or referencia.get('canal') != 'en_linea':
            motivos.append('moneda_o_canal_distintos')
        if referencia.get('contexto') == 'serie_vendedor' and referencia.get('serie_id') != oferta.get('serie_id'):
            motivos.append('vendedor_distinto')
        if any(pd.isna(referencia.get(k)) or referencia[k] <= 0 for k in ('mediana_base', 'p25_base', 'p75_base')):
            motivos.append('estadisticas_invalidas')
    resultado = dict(indicador='evidencia_insuficiente', ahorro_referencia_pct=None, brecha_pp=None,
                     contexto_referencia=None if referencia is None else referencia['contexto'],
                     motivos=json.dumps(motivos, ensure_ascii=False), edad_consulta_dias=edad,
                     regla_version='precio-v1', umbral_pct=umbral)
    if motivos:
        return resultado
    ahorro = 100 * (1 - precio / referencia['mediana_base'])
    resultado['ahorro_referencia_pct'] = ahorro
    resultado['indicador'] = 'sin_senal_clara'
    if round(ahorro, 10) >= umbral and precio <= referencia['p25_base']:
        resultado['indicador'] = 'precio_favorable'
    elif round(ahorro, 10) <= -umbral and precio >= referencia['p75_base']:
        resultado['indicador'] = 'precio_alto'
    anuncio = oferta.get('pct_descuento_anunciado')
    if referencia['contexto'] == 'serie_vendedor' and anuncio is not None and pd.notna(anuncio):
        resultado['brecha_pp'] = float(anuncio) - ahorro
    return resultado


def preparar_compra(tablas, fecha_consulta, evento_id='BF2026', umbral=5):
    productos = tablas['productos'].loc[tablas['productos'].en_catalogo_web].copy()
    productos['foco_compra'] = productos.nombre.str.contains(r'laptop|computadora|airpods|aud[ií]fonos|headset', case=False, regex=True)
    productos['es_paquete'] = productos.nombre.map(lambda x: atributos(x)['paquete'])
    productos['atributos_json'] = productos.nombre.map(lambda x: json.dumps(atributos(x), ensure_ascii=False))
    ultimas = tablas['precios_diarios'].merge(tablas['series'][['serie_id', 'producto_canonico_id']], on='serie_id').groupby('producto_canonico_id').fecha_precio.max()
    productos['ultima_fecha_observada'] = productos.producto_canonico_id.map(ultimas)
    buscador = Buscador(productos)
    series = tablas['series'].set_index('serie_id')
    referencias = tablas['referencias_base'].loc[tablas['referencias_base'].evento_id.eq(evento_id)].set_index('serie_id')
    mercado = series.loc[series.contexto.eq('minimo_multitienda')].reset_index().groupby('producto_canonico_id').serie_id.agg(list)
    nombres = productos.set_index('producto_canonico_id').nombre
    filas = []
    for oferta in tablas['ofertas'].to_dict('records'):
        pid = oferta['producto_canonico_id']
        if pid not in nombres.index:
            continue
        sid = oferta['serie_id']
        titulo = series.loc[sid, 'descripcion_original']
        estado, razon = identidad_oferta(nombres[pid], titulo)
        oferta.update(identidad_oferta=estado, motivo_identidad=razon, titulo_oferta=titulo)
        candidata = referencias.loc[sid].to_dict() if sid in referencias.index else None
        referencia_id = sid
        if candidata is None or not candidata.get('cobertura_base'):
            ids = [x for x in mercado.get(pid, []) if x in referencias.index]
            # Una referencia ambigua no se elige arbitrariamente.
            candidata = referencias.loc[ids[0]].to_dict() if len(ids) == 1 else None
            referencia_id = ids[0] if len(ids) == 1 else None
        if candidata is not None:
            candidata['serie_id'] = referencia_id
        oferta.update(evaluar_precio(oferta, candidata, fecha_consulta, umbral))
        condiciones = json.loads(oferta['condiciones']) if isinstance(oferta['condiciones'], str) and oferta['condiciones'].startswith('{') else {}
        bandera = condiciones.get('marketplace')
        oferta['tipo_vendedor'] = 'tercero' if bandera == 1 else 'tienda' if bandera == 0 else 'sin_confirmar'
        oferta['referencia_serie_id'] = referencia_id
        oferta['precio_total_verificado'] = None
        oferta['condiciones_pendientes'] = 'Confirmar inventario, envío, membresía y variante en la tienda'
        referencia_texto = 'el historial de mínimos multitienda' if oferta['contexto_referencia'] == 'minimo_multitienda' else 'el historial del vendedor'
        diferencia = oferta['ahorro_referencia_pct']
        comparacion = 'Historia o identidad insuficiente.' if diferencia is None else f"{abs(diferencia):.1f}% {'por debajo' if diferencia >= 0 else 'por encima'} de la mediana de {referencia_texto}."
        oferta['resumen'] = (f"{oferta['plataforma']} · vendedor {oferta['vendedor_o_cadena']}: "
                            f"${oferta['precio']:,.2f} {oferta['moneda']}, observado {oferta['fecha_precio']}. "
                            f"{comparacion} Precio publicado; total e inventario pendientes. {razon}.")
        filas.append(oferta)
    ofertas = pd.DataFrame(filas)
    revision = ofertas.loc[ofertas.identidad_oferta.ne('compatible_texto'),
                          ['obs_id', 'producto_canonico_id', 'titulo_oferta', 'identidad_oferta', 'motivo_identidad', 'url']].copy()
    return dict(catalogo_consulta=productos, ofertas_evaluadas=ofertas, revision_identidades=revision), buscador


def consultar(producto_id, tablas_compra, fecha_consulta):
    ofertas = tablas_compra['ofertas_evaluadas']
    fecha = pd.to_datetime(ofertas.fecha_precio)
    edad = (pd.Timestamp(fecha_consulta) - fecha).dt.days
    salida = ofertas.loc[ofertas.producto_canonico_id.eq(producto_id)].copy()
    obsoletas = ~edad.loc[salida.index].between(0, 1)
    salida.loc[obsoletas, 'indicador'] = 'evidencia_insuficiente'
    salida.loc[obsoletas, 'motivos'] = '["captura_fuera_de_vigencia"]'
    salida['edad_consulta_dias'] = edad.loc[salida.index]
    return salida.sort_values(['precio', 'plataforma'])
