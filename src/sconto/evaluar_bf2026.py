"""Comprueba y, con cobertura suficiente, evalúa de forma retrospectiva BF2026."""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import file_digest
import json
from pathlib import Path
import sqlite3
from contextlib import closing

import numpy as np
import pandas as pd

from sconto import v2_history as historia
from sconto.colab import cargar_paquete
from sconto.dataset import MIN_AMPLITUD, MIN_BASE, MIN_EVENTO, MIN_PREVIO
from sconto.eventos import cargar_eventos
from sconto.rutas import REPORTS


def _huella(ruta: Path) -> str:
    with ruta.open('rb') as archivo:
        return file_digest(archivo, 'sha256').hexdigest()


def revisar_cobertura(observaciones, eventos, corte):
    """Devuelve preparación y cobertura del dominio publicado para el modelo."""
    corte = pd.Timestamp(corte).normalize()
    eventos = eventos.loc[eventos.evento_id.eq('BF2026')]
    evento = eventos.iloc[0]
    dominio = observaciones.loc[observaciones[['fuente', 'canal', 'moneda']].eq(historia.DOMINIO).all(axis=1)]
    dominio = dominio.loc[pd.to_datetime(dominio.fecha_precio).le(corte)]
    serie = historia.preparar_series(dominio, eventos, corte)
    if not serie.empty:
        serie = serie.loc[serie.minimos_previos & np.isfinite(serie[historia.VARIABLES].astype(float)).all(axis=1)]
    con_resultado = serie.loc[serie.resultado_observado] if not serie.empty else serie
    clases = (con_resultado.etiqueta_bajo.value_counts().to_dict() if len(con_resultado) else {})
    ultimo = pd.to_datetime(dominio.fecha_precio).max()
    faltantes = []
    if corte <= evento.evento_fin:
        faltantes.append('evento_abierto')
    if pd.isna(ultimo) or ultimo < evento.evento_fin:
        faltantes.append('publicacion_qqp_aun_no_cubre_fin_del_evento')
    if len(con_resultado) == 0:
        faltantes.append('sin_resultados_comparables')
    elif len(clases) < 2:
        faltantes.append('falta_una_clase_para_exactitud_balanceada')
    marcas = ('base_inicio', 'base_fin', 'previo_inicio', 'previo_fin', 'evento_inicio', 'evento_fin',
              'posterior_inicio', 'posterior_fin')
    estado = dict(
        evento='BF2026', fecha_corte=corte.date().isoformat(), poblacion=historia.DOMINIO,
        ventanas={marca: evento[marca].date().isoformat() for marca in marcas},
        protocolo=dict(min_dias_base=MIN_BASE, amplitud_base_dias=MIN_AMPLITUD,
                       min_dias_previos=MIN_PREVIO, min_dias_evento=MIN_EVENTO),
        ultimo_precio_QQP=None if pd.isna(ultimo) else ultimo.date().isoformat(),
        series_con_variables=len(serie), series_con_resultado=len(con_resultado),
        clases_con_resultado={str(k): v for k, v in clases.items()},
        productos_con_resultado=con_resultado.id_externo.nunique() if len(con_resultado) else 0,
        estado='pendiente' if faltantes else 'preparado_para_evaluacion_retrospectiva',
        motivos=faltantes, diagnostico_posterior_cerrado=corte > evento.posterior_fin,
        evaluacion_prospectiva=False,
    )
    return estado, serie


def describir_piloto(ruta: Path, corte: date) -> dict:
    """Desglosa el piloto físico. Su universo no habilita el modelo de QQP."""
    sql = '''
        SELECT fecha_precio, COUNT(precio), COUNT(DISTINCT producto_id), COUNT(*) - COUNT(precio)
        FROM precios_diarios_fuente JOIN ofertas USING (offer_id)
        WHERE fuente='profeco_buen_fin' AND fecha_precio <= ?
        GROUP BY fecha_precio ORDER BY fecha_precio
    '''
    with closing(sqlite3.connect(ruta.resolve().as_uri() + '?mode=ro', uri=True)) as base:
        fechas = base.execute(sql, (corte.isoformat(),)).fetchall()
    return dict(precios_diarios=sum(n for _, n, _, _ in fechas), ultima_fecha=fechas[-1][0] if fechas else None,
                periodo_buen_fin={dia: dict(precios=n, modelos=p, conflictos=c) for dia, n, p, c in fechas
                                  if '2026-11-13' <= dia <= '2026-11-17'})


def evaluar_retrospectiva(paquete_historico, serie_2026, eventos):
    """Reconstruye el árbol fijado con el mismo paquete que generó la tarjeta publicada."""
    procedencia = json.loads((REPORTS / 'procedencia_historica_v2.json').read_text(encoding='utf-8'))
    protocolo = json.loads((REPORTS / 'protocolo_modelo_v2.json').read_text(encoding='utf-8'))
    esperado = procedencia['fuentes']['sconto_colab_2026-11-14.zip']['sha256']
    if (_huella(paquete_historico) != esperado or _huella(Path(historia.__file__)) != procedencia['archivo_codigo_sha256']
            or pd.__version__ != procedencia['pandas_version']
            or historia.sklearn.__version__ != procedencia['sklearn_version']):
        raise ValueError('El código, los datos históricos o las dependencias difieren de la revisión fijada.')
    datos = cargar_paquete(paquete_historico)['observaciones']
    serie_historica = historia.preparar_series(datos, eventos.loc[eventos.evento_id.isin(['BF2024', 'BF2025'])],
                                               pd.Timestamp(procedencia['fecha_corte']))
    reconstruccion = historia.modelo_supervisado(pd.concat([serie_historica, serie_2026], ignore_index=True))
    tarjeta = reconstruccion['protocolo']
    campos = ('modelo_elegido_en_2024', 'n_entrenamiento', 'n_prueba', 'umbral_probabilidad', 'variables', 'semilla')
    if any(tarjeta.get(campo) != protocolo.get(campo) for campo in campos):
        raise ValueError('La reconstrucción difiere del protocolo publicado.')
    evaluables = reconstruccion['predicciones'].loc[lambda filas:
        filas.evento_id.eq('BF2026') & filas.etiqueta_bajo.notna()]
    y = evaluables.etiqueta_bajo.to_numpy(dtype=int)
    pred = evaluables.prediccion.to_numpy(dtype=int)
    prob = evaluables.probabilidad_bajada.to_numpy(dtype=float)
    recuento = historia._metricas_recuento(y, pred, prob)
    return dict(tipo='reconstruccion_retrospectiva', modelo=tarjeta['modelo_elegido_en_2024'],
                **{campo: float(valor) if np.isfinite(valor) else None for campo, valor in recuento.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paquete', required=True, type=Path, help='Paquete conciliado con QQP anual')
    parser.add_argument('--corte', required=True, type=date.fromisoformat, help='Fecha de corte en CDMX')
    parser.add_argument('--piloto-sqlite', type=Path)
    parser.add_argument('--entrenamiento-fijado', type=Path, help='Solicita evaluar usando el ZIP histórico fijado')
    args = parser.parse_args(argv)
    eventos = cargar_eventos()
    datos = cargar_paquete(args.paquete)
    resultado, serie = revisar_cobertura(datos['observaciones'], eventos, args.corte)
    resultado['entrada_sha256'] = _huella(args.paquete)
    if args.piloto_sqlite:
        resultado['piloto_fisico'] = describir_piloto(args.piloto_sqlite, args.corte)
    if args.entrenamiento_fijado and not resultado['motivos']:
        resultado['metricas'] = evaluar_retrospectiva(args.entrenamiento_fijado, serie, eventos)
        resultado['estado'] = 'evaluado_retrospectivamente'
    print(json.dumps(resultado, ensure_ascii=True, allow_nan=False))


if __name__ == '__main__':
    main()
