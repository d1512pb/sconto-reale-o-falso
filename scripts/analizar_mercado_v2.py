"""Publica tablas agregadas del corte, sin publicar crudos ni direcciones de sucursal."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from sconto.colab import cargar_paquete
from sconto.v2_mercado import analizar_mercado, analizar_profeco_bf, resumen_cambios


def escribir(paquete, salida, oficial=None):
    datos = cargar_paquete(paquete)
    with ZipFile(paquete) as z:
        origen = json.loads(z.read('paquete.json'))
    corte = pd.to_datetime(origen['dataset_construido_utc'], utc=True).tz_convert(ZoneInfo('America/Mexico_City')).date().isoformat()
    evento = datos['eventos'].set_index('evento_id', drop=False).loc['BF2026']
    analisis = analizar_mercado(datos['observaciones'], datos['series_evento'], evento, corte)
    cambios = resumen_cambios(analisis['cambios'])
    tablas = dict(cobertura_buen_fin_v2=analisis['inventario'], cambios_buen_fin_v2=cambios,
                  hipotesis=analisis['hipotesis'], hallazgos=analisis['hallazgos'])
    hallazgos = tablas['hallazgos']
    if oficial is not None:
        datos_profeco = pd.read_csv(oficial, dtype={'producto_profeco_id': str, 'cp_sucursal': str})
        reporte = analizar_profeco_bf(datos_profeco, evento)
        tablas.update(cobertura_profeco_bf2026=reporte['inventario'],
                      comparabilidad_profeco_bf2026=reporte['resumen'])
        validas = reporte['panel'].loc[reporte['panel'].cobertura_alza]
        if len(validas):
            hallazgos.loc[hallazgos.id.eq('H1'), ['estado', 'n_casos_validos', 'n_con_patron', 'limite']] = [
                'patron_descriptivo_preliminar', len(validas), int(validas.patron_alza_y_rebaja.sum()),
                'Consulta especial PROFECO, producto × sucursal, plaza metropolitana. La muestra es dirigida.',
            ]
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, tabla in tablas.items():
        tabla.to_csv(salida / (nombre + '.csv'), index=False)

    etiquetas = {'preciometro': 'Mínimo multitienda', 'preciometro_ofertas': 'Anuncios del agregador',
                 'tiendas': 'Ficha de Liverpool'}
    if len(cambios):
        grafica = cambios.assign(fuente=cambios.fuente.map(etiquetas).fillna(cambios.fuente))
        ax = grafica.set_index('fuente')[['bajaron', 'quedaron_igual', 'subieron']].plot.barh(
            stacked=True, color=['#26715b', '#c4cdc6', '#a65824'], figsize=(8.8, 3.2))
        ax.set(xlabel='Series observadas en dos fechas (conteo)', ylabel='',
               title='Cambio del precio registrado durante el Buen Fin 2026')
        ax.legend(['Bajó', 'Igual', 'Subió'], loc='lower right')
        ax.figure.tight_layout()
        ax.figure.savefig(salida / 'cambios_buen_fin_v2.png', dpi=160)
        plt.close(ax.figure)

    inv = analisis['inventario'].groupby('fuente').filas.sum()
    resumen = [f'# Buen Fin 2026 · avance de mercado al {corte}', '',
               'El corte cubre sólo los primeros días del evento. Los conteos describen la muestra observada.', '',
               '## Observaciones del snapshot público', '']
    for fuente, cantidad in inv.items():
        resumen.append(f'- {etiquetas.get(fuente, fuente)}. {cantidad:,} registros de precio en la ventana observada.')
    resumen.extend(['', '### Cambios entre el primer y último día disponible por serie', ''])
    for r in cambios.itertuples(index=False):
        resumen.append(f'- {etiquetas.get(r.fuente, r.fuente)}. {r.series_comparables_por_id} series observadas en dos o más fechas, '
                       f'con {r.bajaron} bajas, {r.quedaron_igual} sin cambio y {r.subieron} alzas.')
    minimos = analisis['referencias'].loc[analisis['referencias'].fuente.eq('preciometro')]
    elegibles = minimos.loc[minimos.cobertura_alza]
    if len(elegibles):
        resumen.extend(['', f'En {int(elegibles.alza_y_rebaja_observadas.sum())} de {len(elegibles)} series '
                        'con cobertura, el mínimo multitienda subió en el periodo previo respecto a la base y cayó durante '
                        'el evento respecto al previo. La tienda con el menor precio puede cambiar en cada fecha.'])
    if oficial is not None:
        n_evento = int(reporte['inventario'].loc[reporte['inventario'].fecha_precio.between(
            pd.Timestamp(evento.evento_inicio), pd.Timestamp(evento.evento_fin)), 'observaciones'].sum())
        resumen.extend(['', '## Consulta oficial de PROFECO por sucursal', '',
                        f'{len(datos_profeco):,} registros fechados limpios para {datos_profeco.producto_profeco_id.nunique()} productos. '
                        f'{n_evento:,} registros día-sucursal en la ventana del evento tras deduplicar. '
                        f'La verificación posterior detectó {reporte["conflictos"]} conflictos adicionales tras la limpieza.', ''])
        for r in reporte['resumen'].itertuples(index=False):
            resumen.append(f'- {r.zona_sucursal}. {r.series} series producto × sucursal, {r.con_evento} con precio del evento, '
                           f'{r.con_base_previo_evento} con base, previo y evento. {r.alza_y_rebaja} cumplen el patrón de alza y rebaja.')
        resumen.extend(['', 'La plaza incluye establecimientos de Ciudad de México y su área metropolitana. '
                        'La clasificación geográfica usa el código postal publicado. Los precios de esta consulta especial '
                        'se analizan fuera del archivo anual QQP y de las ofertas online. [Consulta oficial](https://elbuenfin.profeco.gob.mx/)'])
    resumen.extend(['', '## Límites', '',
                    'Los anuncios del agregador registran la consulta. La fecha efectiva de actualización del vendedor queda desconocida. '
                    'Los datos diarios no permiten calcular duración intradía. En los dos días observados la ficha archivada de Liverpool '
                    'mantuvo el mismo precio publicado y tachado. El envío, vendedor e inventario quedaron sin confirmar.', '',
                    'La evidencia y los requisitos de cada hipótesis están en `hipotesis.csv` y `hallazgos.csv`. '
                    'La muestra prioriza tecnología y no permite estimar la frecuencia de ofertas en México. '
                    'Se requiere cerrar la ventana y verificar SKU, vendedor, cargos y disponibilidad para evaluar conveniencia.', '',
                    f'Paquete público `{paquete.name}` · SHA-256 `{hashlib.sha256(paquete.read_bytes()).hexdigest()}`.'])
    (salida / 'informe_mercado.md').write_text('\n'.join(resumen) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paquete', type=Path, required=True)
    parser.add_argument('--profeco', type=Path)
    parser.add_argument('--salida', type=Path, default=Path('reports'))
    args = parser.parse_args()
    escribir(args.paquete, args.salida, args.profeco)
