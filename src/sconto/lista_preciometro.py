"""Lista fija de fichas de Preciómetro a seguir (se congela una vez; no se rastrea el catálogo completo).

Prioridad (igual que productos_objetivo): 1 = modelo de las 93 series, 2 = de las 298, 3 = otro modelo QQP,
4 = ficha de tecnología del sitio en las mismas familias de producto que QQP (pantallas, celulares, audio,
laptops, tablets, asistentes, streaming, cámaras), sin equivalente QQP: sirve para series en línea del BF2026.

Fuente de la lista: productos_sitemap.xml publicado por el propio sitio (sin peticiones adicionales).
Después del backfill se descartan las fichas cuya categoría real no es `tecnologia/*`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

from sconto.normalizar import aparece_en_tokens, compacto, modelo_qqp, normalizar, tokens_slug
from sconto.rutas import AVANCE1, CONFIG

TECNOLOGIA = re.compile(
    r'(pantalla|smart-tv|television|televisor|\btv\b|qled|oled|uhd|celular|smartphone|iphone|galaxy|moto-|motorola|'
    r'redmi|xiaomi|oppo|honor|huawei|zte|realme|vivo|tablet|ipad|tab-|laptop|notebook|macbook|chromebook|ideapad|'
    r'vivobook|bocina|altavoz|parlante|speaker|xboom|partybox|barra-de-sonido|soundbar|home-theater|minicomponente|'
    r'audifono|earbuds|airpods|buds|echo-|alexa|nest|google-home|roku|fire-tv|chromecast|streaming|camara|instax|'
    r'gopro|go-pro|eos|mirrorless|smartwatch|reloj-inteligente|apple-watch|galaxy-watch|jbl|sony|bose|lg-|samsung|'
    r'hisense|tcl|lenovo|hp-|asus|acer|dell)')
ACCESORIO = re.compile(
    r'(funda|case|protector|mica|cargador|cable|soporte|adaptador|refrigerador|lavadora|secadora|estufa|horno|'
    r'microondas|aspiradora|licuadora|cafetera|perfume|tequila|cartucho|toner|tinta|correa|estuche|mouse|teclado|'
    r'memoria-usb|micro-sd|lente-de-camara|tripie|bateria-para)')


def claves_qqp() -> pd.DataFrame:
    """Claves de modelo (compactas) por referencia QQP, con su prioridad."""
    limpios = pd.read_parquet(AVANCE1 / '05_observaciones_limpias.parquet',
                              columns=['producto_id', 'producto', 'marca', 'presentacion'])
    series = pd.read_csv(AVANCE1 / '06_variables_por_serie.csv', usecols=['producto_id', 'cobertura_ahorro'])
    meta93 = pd.read_csv(AVANCE1 / '08_metadatos_modelo.csv', usecols=['producto_id'])
    refs = limpios.drop_duplicates('producto_id').set_index('producto_id')
    p298 = set(series.loc[series.cobertura_ahorro, 'producto_id'])
    p93 = set(meta93.producto_id)
    filas = []
    for pid, r in refs.iterrows():
        m = modelo_qqp(r.presentacion)
        marca = compacto(str(r.marca).split('.')[0])
        prioridad = 1 if pid in p93 else 2 if pid in p298 else 3
        for clave in [m['modelo_normalizado'], *m['codigos']]:
            if len(clave) >= 4:
                filas.append(dict(qqp_producto_id=pid, marca_qqp=marca, clave=clave, prioridad=prioridad))
    return pd.DataFrame(filas)


def construir(sitemap_xml: Path, destino: Path = CONFIG / 'preciometro_lista.csv') -> pd.DataFrame:
    texto = sitemap_xml.read_text(encoding='utf-8')
    urls = re.findall(r'<loc>([^<]+/productos/[^<]+)</loc>', texto)
    claves = claves_qqp()
    filas = []
    for url in urls:
        slug = url.rsplit('/productos/', 1)[1]
        if not TECNOLOGIA.search(slug) or ACCESORIO.search(slug):
            continue
        toks = tokens_slug(slug)
        hits = claves.loc[[aparece_en_tokens(c, toks) for c in claves.clave]]
        prioridad = int(hits.prioridad.min()) if len(hits) else 4
        filas.append(dict(preciometro_id=str(int(slug.rsplit('-', 1)[1])), url=url, slug=slug, prioridad=prioridad,
                          qqp_candidatos=';'.join(sorted(set(hits.qqp_producto_id))),
                          claves_coincidentes=';'.join(sorted(set(hits.clave)))))
    df = pd.DataFrame(filas).sort_values(['prioridad', 'preciometro_id']).reset_index(drop=True)
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False, encoding='utf-8')
    return df


if __name__ == '__main__':
    df = construir(Path(sys.argv[1]))
    print(df.prioridad.value_counts().sort_index().to_string())
