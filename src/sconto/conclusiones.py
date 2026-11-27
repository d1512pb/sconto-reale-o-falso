"""Patrones de precio para las conclusiones: ofertas reales, rebajas aparentes y precios señuelo.

Preguntas:
1. ¿Cuántos precios del Buen Fin no muestran una señal clara (menos de 5 % frente a su historia)?
2. ¿Pasa el truco de "subir antes y bajar en el evento"? ¿Terminas pagando lo mismo o más?
3. ¿Qué tanto engaña comparar contra la tienda más cara (precio señuelo)?
4. ¿La regla de la app distingue una rebaja real de una aparente?

Las ventanas y mínimos son los mismos del modelo final (`modelo_final`). Cada patrón se compara contra
semanas normales (placebo) para no confundir el comportamiento del evento con la variación de siempre.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sconto import modelo_final as M
from sconto import v2_history as H

UMBRAL = 5.0


def series_2026(obs: pd.DataFrame, piloto: pd.DataFrame | None, corte) -> pd.DataFrame:
    """Series del Buen Fin 2026 con base, previo y evento (Preciómetro relajado en identidad y PROFECO estricto)."""
    columnas = ['fuente', 'serie_id', 'fecha_precio', 'precio', *H.METADATOS]
    base = obs.loc[obs.fuente.eq('preciometro')].assign(moneda=lambda d: d.moneda.fillna('MXN'))[columnas]
    entrada = [base] + ([piloto[columnas]] if piloto is not None else [])
    s = H.preparar_series(pd.concat(entrada, ignore_index=True), M.eventos_buen_fin([2026]), pd.Timestamp(corte))
    precio_min = (s.fuente.eq('preciometro') & s.evento_cerrado & s.amplitud_base_dias.ge(H.MIN_AMPLITUD)
                  & s.n_base.ge(H.MIN_BASE) & s.n_previo.ge(H.MIN_PREVIO) & s.n_evento.ge(H.MIN_EVENTO))
    profeco = s.fuente.eq('profeco_bf2026') & s.resultado_observado
    return s.loc[precio_min | profeco].copy()


def clasificar(v: pd.DataFrame) -> pd.DataFrame:
    """Veredicto de la app y patrón de cada ventana (base, previo y evento de una misma serie)."""
    d = v.copy()
    d['ahorro_real_pct'] = 100 * (1 - d.mediana_evento / d.mediana_base)        # frente a la historia
    d['rebaja_vs_previo_pct'] = 100 * (1 - d.mediana_evento / d.mediana_previo)  # frente a las 2 semanas previas
    d['alza_previa_pct'] = 100 * (d.mediana_previo / d.mediana_base - 1)
    d['veredicto_app'] = np.select(
        [d.ahorro_real_pct.ge(UMBRAL) & d.mediana_evento.le(d.p25_base),
         d.ahorro_real_pct.le(-UMBRAL) & d.mediana_evento.ge(d.p75_base)],
        ['favorable', 'alto'], 'sin_senal_clara')
    d['parece_oferta'] = d.rebaja_vs_previo_pct.ge(UMBRAL)            # lo que ve quien compara con el precio reciente
    d['rebaja_real'] = d.ahorro_real_pct.ge(UMBRAL)
    d['subir_y_bajar'] = d.alza_previa_pct.ge(UMBRAL) & d.parece_oferta
    d['patron'] = np.select(
        [d.rebaja_real, d.parece_oferta & ~d.rebaja_real, d.ahorro_real_pct.le(-UMBRAL)],
        ['rebaja_real', 'rebaja_aparente', 'subio'], 'sin_cambio_relevante')
    return d


def resumen_poblaciones(grupos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    filas = []
    for nombre, d in grupos.items():
        n = len(d)
        sub = d.loc[d.subir_y_bajar]
        aparente = d.loc[d.parece_oferta]
        filas.append(dict(
            poblacion=nombre, ventanas=n,
            pct_favorable=100 * d.veredicto_app.eq('favorable').mean(),
            pct_sin_senal=100 * d.veredicto_app.eq('sin_senal_clara').mean(),
            pct_alto=100 * d.veredicto_app.eq('alto').mean(),
            pct_rebaja_real=100 * d.patron.eq('rebaja_real').mean(),
            pct_rebaja_aparente=100 * d.patron.eq('rebaja_aparente').mean(),
            pct_sin_cambio=100 * d.patron.eq('sin_cambio_relevante').mean(),
            pct_subio=100 * d.patron.eq('subio').mean(),
            mediana_ahorro_real_pct=d.ahorro_real_pct.median(),
            pct_subir_y_bajar=100 * d.subir_y_bajar.mean(),
            pct_subir_y_bajar_sin_ahorro_real=100 * (~sub.rebaja_real).mean() if len(sub) else np.nan,
            pct_subir_y_bajar_paga_igual_o_mas=100 * sub.ahorro_real_pct.le(0).mean() if len(sub) else np.nan,
            pct_ofertas_aparentes_sin_ahorro_real=100 * (~aparente.rebaja_real).mean() if len(aparente) else np.nan,
            pct_ofertas_aparentes_marcadas_favorables=100 * aparente.loc[~aparente.rebaja_real].veredicto_app.eq('favorable').mean()
            if (~aparente.rebaja_real).any() else np.nan,
        ))
    return pd.DataFrame(filas)


def dispersion_tiendas(obs: pd.DataFrame) -> pd.DataFrame:
    """Mismo producto y mismo día en 3 o más tiendas: cuánto más caro está el más caro (posible señuelo)."""
    piezas = []
    for fuente, clave_tienda, clave_producto in (('preciometro_ofertas', 'plataforma', 'producto_canonico_id'),
                                                 ('qqp_cdmx', 'vendedor_o_cadena', 'id_externo')):
        d = obs.loc[obs.fuente.eq(fuente) & obs.precio.gt(0), [clave_producto, 'fecha_precio', clave_tienda, 'precio']].dropna()
        d = d.groupby([clave_producto, 'fecha_precio', clave_tienda]).precio.median().reset_index()
        g = d.groupby([clave_producto, 'fecha_precio']).precio
        t = pd.DataFrame(dict(tiendas=g.size(), minimo=g.min(), mediana=g.median(), maximo=g.max())).reset_index()
        t = t.loc[t.tiendas.ge(3)]
        # Precios a menos de la mitad de la mediana suelen ser otro producto: se descartan del mínimo.
        t = t.loc[t.minimo.ge(M_ATIPICO * t.mediana)]
        t['fuente'] = fuente
        t['mas_cara_sobre_mediana_pct'] = 100 * (t.maximo / t.mediana - 1)
        t['descuento_aparente_vs_mas_cara_pct'] = 100 * (1 - t.mediana / t.maximo)
        t['brecha_extremos_pct'] = 100 * (t.maximo / t.minimo - 1)
        piezas.append(t)
    return pd.concat(piezas, ignore_index=True)


M_ATIPICO = 0.5


def resumen_dispersion(t: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for fuente, d in t.groupby('fuente'):
        filas.append(dict(
            fuente={'preciometro_ofertas': 'Preciómetro · tiendas en línea 2026', 'qqp_cdmx': 'QQP · sucursales físicas 2018–2026'}[fuente],
            producto_dia=len(d), tiendas_mediana=d.tiendas.median(),
            mas_cara_sobre_mediana_mediana_pct=d.mas_cara_sobre_mediana_pct.median(),
            pct_mas_cara_20_o_mas=100 * d.mas_cara_sobre_mediana_pct.ge(20).mean(),
            pct_mas_cara_30_o_mas=100 * d.mas_cara_sobre_mediana_pct.ge(30).mean(),
            pct_mas_cara_50_o_mas=100 * d.mas_cara_sobre_mediana_pct.ge(50).mean(),
            descuento_aparente_vs_mas_cara_mediana_pct=d.descuento_aparente_vs_mas_cara_pct.median(),
            brecha_extremos_mediana_pct=d.brecha_extremos_pct.median()))
    return pd.DataFrame(filas)


def figuras(salida: Path, resumen: pd.DataFrame, disp: pd.DataFrame) -> list[Path]:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rutas = []
    colores = {'Rebaja real (≥5 % bajo su historia)': '#2f7d4f', 'Rebaja aparente (sólo frente a las 2 semanas previas)': '#e0a526',
               'Sin cambio relevante': '#b8c2b5', 'Subió (≥5 % sobre su historia)': '#b5543a'}
    columnas = ['pct_rebaja_real', 'pct_rebaja_aparente', 'pct_sin_cambio', 'pct_subio']
    fig, ax = plt.subplots(figsize=(10, 4.4))
    izquierda = np.zeros(len(resumen))
    for (etiqueta, color), col in zip(colores.items(), columnas):
        valores = resumen[col].to_numpy()
        ax.barh(resumen.poblacion, valores, left=izquierda, color=color, label=etiqueta)
        for y, (x0, v) in enumerate(zip(izquierda, valores)):
            if v >= 6:
                ax.text(x0 + v / 2, y, f'{v:.0f} %', ha='center', va='center', fontsize=8, color='white' if col != 'pct_sin_cambio' else '#182d28')
        izquierda += valores
    ax.set_xlim(0, 100); ax.invert_yaxis(); ax.set_xlabel('% de series (producto × tienda)')
    ax.set_title('¿Qué pasó con el precio durante el evento frente a su historia?', fontsize=11)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.18), ncol=2, frameon=False, fontsize=8)
    fig.tight_layout(); rutas.append(salida / 'fig_patrones_precio.png'); fig.savefig(rutas[-1], dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.8))
    for fuente, color in (('preciometro_ofertas', '#2563eb'), ('qqp_cdmx', '#9ca3af')):
        d = disp.loc[disp.fuente.eq(fuente), 'mas_cara_sobre_mediana_pct'].clip(upper=100)
        ax.hist(d, bins=50, alpha=.6, color=color, density=True,
                label={'preciometro_ofertas': 'Tiendas en línea (Preciómetro 2026)', 'qqp_cdmx': 'Sucursales físicas (QQP)'}[fuente])
    ax.axvline(30, ls='--', color='#ea580c'); ax.set_xlabel('Tienda más cara frente a la mediana del mismo producto y día (%)')
    ax.set_ylabel('Densidad'); ax.set_title('El precio señuelo: cuánto más cara está la tienda más cara', fontsize=11)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); rutas.append(salida / 'fig_precio_senuelo.png'); fig.savefig(rutas[-1], dpi=150); plt.close(fig)
    return rutas


def ejecutar(paquete: Path, piloto: Path | None, salida: Path, corte='2026-11-26') -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    obs = M.cargar_paquete(paquete)
    v = clasificar(M.ventanas_comparables(obs, corte))
    obs_piloto = M.observaciones_piloto(piloto) if piloto and Path(piloto).exists() else None
    s26 = clasificar(series_2026(obs, obs_piloto, corte))
    grupos = {
        'QQP sucursales · Buen Fin 2018–2025': v.loc[v.real],
        'QQP sucursales · semanas normales': v.loc[~v.real],
        'PROFECO sucursales · Buen Fin 2026': s26.loc[s26.fuente.eq('profeco_bf2026')],
        'Preciómetro en línea · Buen Fin 2026': s26.loc[s26.fuente.eq('preciometro')],
    }
    resumen = resumen_poblaciones(grupos)
    disp = dispersion_tiendas(obs)
    rdisp = resumen_dispersion(disp)
    resumen.to_csv(salida / 'patrones_por_poblacion.csv', index=False)
    rdisp.to_csv(salida / 'precio_senuelo_dispersion.csv', index=False)
    pd.concat([d.assign(poblacion=k) for k, d in grupos.items()])[[
        'poblacion', 'evento_id', 'fuente', 'serie_id', 'mediana_base', 'mediana_previo', 'mediana_evento', 'p25_base', 'p75_base',
        'ahorro_real_pct', 'rebaja_vs_previo_pct', 'alza_previa_pct', 'veredicto_app', 'patron', 'subir_y_bajar']].to_csv(
        salida / 'patrones_por_serie.csv', index=False)
    rutas = figuras(salida, resumen, disp)
    limpio = lambda t: t.round(2).astype(object).where(t.notna(), None).to_dict(orient='records')  # noqa: E731
    r = dict(resumen=limpio(resumen), dispersion=limpio(rdisp),
             figuras=[p.name for p in rutas])
    (salida / 'conclusiones.json').write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return dict(resumen=resumen, dispersion=rdisp, ventanas=v, s26=s26, disp=disp)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--paquete', type=Path, required=True)
    ap.add_argument('--piloto', type=Path)
    ap.add_argument('--salida', type=Path, required=True)
    a = ap.parse_args(argv)
    r = ejecutar(a.paquete, a.piloto, a.salida)
    pd.set_option('display.width', 220); pd.set_option('display.max_columns', 30)
    print(r['resumen'].round(1).T.to_string())
    print(r['dispersion'].round(1).T.to_string())


if __name__ == '__main__':
    main()


def busqueda_umbral(v: pd.DataFrame, umbrales=None, repeticiones=500, semilla=42) -> pd.DataFrame:
    """Búsqueda fina del umbral de la regla (ahorro >= t y precio <= P25) con IC95 por remuestreo de series.

    Para cada t: % de ventanas del Buen Fin que cumplen, % de semanas normales que cumplen y J de Youden.
    Se marca qué umbrales no se distinguen estadísticamente del mejor (su IC de la diferencia incluye 0).
    """
    umbrales = np.round(np.arange(0.5, 15.01, 0.5), 2) if umbrales is None else np.asarray(umbrales)
    ahorro = (100 * (1 - v.mediana_evento / v.mediana_base)).to_numpy()
    p25 = v.mediana_evento.le(v.p25_base).to_numpy()
    real = v.real.to_numpy()
    cumple = (ahorro[:, None] >= umbrales[None, :]) & p25[:, None]          # ventanas × umbrales
    _, grupo = np.unique(v.serie_id.astype(str).to_numpy(), return_inverse=True)
    rng = np.random.default_rng(semilla)
    n_grupos = grupo.max() + 1

    def j(pesos):
        wr, wn = pesos * real, pesos * ~real
        return 100 * ((wr @ cumple) / wr.sum() - (wn @ cumple) / wn.sum())

    base = j(np.ones(len(v)))
    muestras = np.empty((repeticiones, len(umbrales)))
    for r in range(repeticiones):
        conteo = np.bincount(rng.integers(0, n_grupos, n_grupos), minlength=n_grupos)
        muestras[r] = j(conteo[grupo].astype(float))
    mejor = int(np.argmax(base))
    diferencia = muestras[:, [mejor]] - muestras
    tabla = pd.DataFrame(dict(
        umbral_pct=umbrales, youden_j=base,
        j_ic95_inf=np.quantile(muestras, .025, axis=0), j_ic95_sup=np.quantile(muestras, .975, axis=0),
        pct_buen_fin=100 * cumple[real].mean(axis=0), pct_semanas_normales=100 * cumple[~real].mean(axis=0),
        equivalente_al_mejor=np.quantile(diferencia, .025, axis=0) <= 0))
    tabla['lift'] = tabla.pct_buen_fin / tabla.pct_semanas_normales
    return tabla
