"""El mismo contrato de consulta del notebook para cada actualización diaria."""
from sconto.compra import preparar_compra
from sconto.mart import registros


def preparar_aplicacion(tablas, fecha_corte):
    eventos = tablas['eventos']
    actuales = eventos.loc[eventos.d0.astype(str).str.startswith(str(fecha_corte)[:4])]
    evento_id = actuales.evento_id.iloc[0] if len(actuales) else eventos.sort_values('d0').evento_id.iloc[-1]
    compra, buscador = preparar_compra(tablas, fecha_corte, evento_id=evento_id)
    productos = compra['catalogo_consulta']
    series = tablas['series'].loc[tablas['series'].producto_canonico_id.isin(productos.producto_canonico_id)]
    feed = dict(version='sconto-app-v1', fecha_corte=str(fecha_corte), evento_actual=evento_id,
                vigencia_maxima_dias=1, requiere_confirmacion_sku=True, precio_total_verificado=False,
                reglas={'ventaja_minima_pct': 5, 'cuantil_favorable': .25, 'cuantil_alto': .75},
                productos=registros(productos), ofertas=registros(compra['ofertas_evaluadas']),
                series=registros(series), referencias=registros(tablas['referencias_base'].loc[
                    tablas['referencias_base'].serie_id.isin(series.serie_id)]),
                historial=registros(tablas['precios_diarios'].loc[tablas['precios_diarios'].serie_id.isin(series.serie_id)]),
                ventanas=registros(eventos), contrato='CONTRATO_APP.md')
    return compra, {'app_feed.json': feed, 'indice_busqueda.json': buscador.indice()}
