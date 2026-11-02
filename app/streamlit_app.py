"""Prototipo de consulta pública sobre el SQLite exportado por Colab/ETL."""
from pathlib import Path
import json
import os
import sys

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
from sconto.consulta import evaluar_oferta
from sconto.web import descargar, leer, verificar

st.set_page_config(page_title='Sconto · Antes de comprar', page_icon='🏷️', layout='wide')
st.title('Sconto · Antes de comprar')
st.write('Consulta cómo se compara un precio de tecnología con la historia que hemos observado.')
CARPETA = Path(os.environ.get('SCONTO_WEB_DATOS', str(RAIZ / 'data' / 'analitica')))


@st.cache_data(ttl=600)
def actualizar_remoto(url, carpeta):
    return descargar(url, carpeta)


try:
    remoto = os.environ.get('SCONTO_WEB_URL')
    if remoto:
        actualizar_remoto(remoto, str(CARPETA))
    manifest = verificar(CARPETA)
except (OSError, ValueError, KeyError) as error:
    st.error(f'La exportación del análisis no está lista: {error}')
    st.info('Ejecuta el ETL indicado en README.md o configura SCONTO_WEB_URL con el ZIP publicado.')
    st.stop()

corte = pd.Timestamp(manifest['fecha_corte'])
st.caption(f'Datos con corte {corte.date()} · Uso académico · Precios en MXN · Revisa variante, vendedor y condiciones.')
edad = (pd.Timestamp.now(tz='America/Mexico_City').tz_localize(None).normalize() - corte).days
if edad > 1:
    st.warning(f'Este snapshot tiene {edad} días. Los precios publicados pueden haber cambiado.')

consulta, historicos, calidad = st.tabs(['Consultar un precio', 'Análisis de Buen Fin', 'Datos y límites'])
with consulta:
    productos = leer(CARPETA, 'productos')
    ampliar = st.checkbox('Mostrar los 200 productos monitoreados')
    catalogo = productos.loc[productos.en_catalogo_web.eq(1) if ampliar else productos.en_piloto.eq(1)].sort_values('orden_web')
    nombres = catalogo.set_index('producto_canonico_id').nombre.to_dict()
    elegido = st.selectbox('Producto', catalogo.producto_canonico_id.tolist(), format_func=lambda clave: nombres[clave])
    st.caption('La identidad de esta ficha pertenece a su fuente. Los cruces de variantes entre fuentes requieren revisión manual.')
    series = leer(CARPETA, 'series')
    opciones = series.loc[series.producto_canonico_id.eq(elegido)]
    if opciones.empty:
        st.info('Todavía no hay historia para este producto.')
    else:
        etiquetas = {fila.serie_id: f'{fila.fuente} · {fila.vendedor_serie} · {fila.canal}' for fila in opciones.itertuples()}
        sid = st.selectbox('Referencia histórica', opciones.serie_id.tolist(), format_func=lambda clave: etiquetas[clave])
        serie = opciones.set_index('serie_id').loc[sid]
        eventos = leer(CARPETA, 'eventos')
        actuales = eventos.loc[pd.to_datetime(eventos.d0).dt.year.eq(corte.year)]
        eid = actuales.evento_id.iloc[0] if len(actuales) else eventos.evento_id.iloc[-1]
        refs = leer(CARPETA, 'referencias_base', sid)
        ref = refs.loc[refs.evento_id.eq(eid)].iloc[0].to_dict()
        if ref['contexto'] == 'minimo_multitienda':
            st.info('Esta historia contiene el mínimo diario entre varias tiendas. Sirve como referencia de mercado; no mide el ahorro de un vendedor concreto.')
        st.write(f"Base {eid}: {ref['base_inicio']} a {ref['base_fin']} · {int(ref['n_fechas_base'])} fechas observadas.")
        if ref['cobertura_base'] and ref['base_cerrada']:
            st.metric('Mediana de la base', f"${ref['mediana_base']:,.2f}")
        else:
            st.warning('Historia insuficiente o ventana aún abierta. La consulta no emitirá una comparación histórica.')
        diario = leer(CARPETA, 'precios_diarios', sid)
        diario['fecha_precio'] = pd.to_datetime(diario.fecha_precio)
        st.scatter_chart(diario, x='fecha_precio', y='precio_mediano', x_label='Fecha observada', y_label='MXN')
        st.caption('Cada punto representa un día observado. Los días sin captura quedan ausentes.')
        ofertas = leer(CARPETA, 'ofertas')
        ofertas = ofertas.loc[ofertas.producto_canonico_id.eq(elegido)]
        if len(ofertas):
            st.write('Últimas ofertas observadas (la fecha indica su vigencia en el dataset):')
            st.dataframe(ofertas[['plataforma', 'vendedor_o_cadena', 'precio', 'fecha_precio', 'edad_dias', 'url']], hide_index=True)
        with st.form('comparar'):
            precio = st.number_input('Precio que estás viendo (MXN)', min_value=0.01, value=1000.0, step=100.0)
            tachado = st.number_input('Precio tachado, si aparece (0 = sin dato)', min_value=0.0, value=0.0)
            con_pct = st.checkbox('La oferta muestra un porcentaje de descuento')
            pct = st.number_input('Porcentaje que muestra la oferta', min_value=-100.0, max_value=100.0, value=0.0)
            misma = st.checkbox('Confirmo que coincide el modelo, la variante, el vendedor y el canal de esta serie') if ref['contexto'] == 'serie_vendedor' else False
            enviar = st.form_submit_button('Comparar con la referencia')
        if enviar:
            resultado = evaluar_oferta(ref, precio, tachado or None, pct if con_pct else None,
                                       sid if misma else None, canal=serie.canal, moneda=serie.moneda)
            st.write(resultado['mensaje'])
            if resultado['estado'] != 'evidencia_insuficiente':
                textos = {'debajo_del_rango': 'Debajo del rango central observado', 'dentro_del_rango': 'Dentro del rango central observado', 'encima_del_rango': 'Encima del rango central observado'}
                st.subheader(textos[resultado['estado']])
                st.metric('Diferencia frente a la mediana de referencia', f"{resultado['diferencia_frente_referencia_pct']:.1f}%")
                st.caption(resultado['nota_rango'])
            if resultado['descuento_implicito_tachado_pct'] is not None:
                st.write(f"Rebaja implícita frente al tachado: {resultado['descuento_implicito_tachado_pct']:.1f}%. Es aritmética del anuncio, no ahorro histórico verificado.")
            if resultado['brecha_consulta_pp'] is not None:
                st.write(f"Brecha de esta consulta: {resultado['brecha_consulta_pp']:.1f} puntos porcentuales.")
                st.caption(resultado['nota_brecha'])
            st.caption(resultado['advertencia'])

with historicos:
    tarjeta = json.loads((CARPETA / 'modelo.json').read_text(encoding='utf-8'))
    st.subheader('Casos para revisar con evidencia')
    st.write(f"Isolation Forest · entrenamiento BF2024: {tarjeta['n_entrenamiento']} series · evaluación BF2025: {tarjeta['n_validacion']} series.")
    st.info('Un puntaje alto indica un comportamiento poco común. No es probabilidad de fraude. La revisión humana está pendiente.')
    resultados = leer(CARPETA, 'resultados_modelo')
    if len(resultados):
        evento = st.selectbox('Evento terminado', resultados.evento_id.unique().tolist())
        ranking = resultados.loc[resultados.evento_id.eq(evento)].sort_values('puntaje_anomalia', ascending=False)
        st.dataframe(ranking[['descripcion_original', 'vendedor_serie', 'ahorro_historico_pct', 'alza_previa_pct', 'puntaje_anomalia', 'revision_humana']].head(20), hide_index=True)
        caso = st.selectbox('Serie para inspeccionar', ranking.serie_id.tolist())
        puntos = leer(CARPETA, 'precios_diarios', caso)
        puntos['fecha_precio'] = pd.to_datetime(puntos.fecha_precio)
        st.scatter_chart(puntos, x='fecha_precio', y='precio_mediano')
    st.caption('Dominio del modelo: QQP CDMX, tiendas físicas. No se extrapola a Amazon, Mercado Libre ni al evento 2026 todavía incompleto.')
with calidad:
    st.dataframe(leer(CARPETA, 'calidad_fuentes'), hide_index=True)
    st.write('La cobertura global incluye fuentes que no participan en el catálogo de consulta. Ninguna fila de mercado se une a una sucursal física como si fuera la misma serie.')
    for aviso in manifest['advertencias']:
        st.write('• ' + aviso)
    st.write('Las ofertas no certifican stock, envío, cupones ni beneficios bancarios. Amazon directo está desactivado; las observaciones indirectas conservan su fuente.')
    st.download_button('Descargar manifiesto del análisis', json.dumps(manifest, ensure_ascii=False, indent=2), 'manifest.json', 'application/json')
