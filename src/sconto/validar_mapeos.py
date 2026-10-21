"""Aplica decisiones humanas explícitas, sin promover automáticamente candidatos de variantes."""
from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

COLUMNAS_IDS = {'asin': 'asins', 'mlm': 'mlm_ids', 'mlm_item': 'mlm_item_ids', 'preciometro': 'preciometro_ids'}
PATRONES = {'asin': r'[A-Z0-9]{10}', 'mlm': r'MLM\d+', 'mlm_item': r'MLM\d+', 'preciometro': r'\d+'}


def aplicar_validaciones(productos: pd.DataFrame, ruta: Path) -> pd.DataFrame:
    if not ruta.exists():
        return productos
    revisiones = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    if revisiones.empty:
        return productos
    resultado = productos.copy()
    revisiones = revisiones.loc[revisiones.validado.str.lower().isin(['1', 'true', 'si', 'sí'])]
    propietarios = {}
    for revision in revisiones.to_dict('records'):
        tipo = revision['tipo_id_externo']
        identificador = revision['id_externo'].strip().upper().replace('MLM-', 'MLM')
        pid = revision['producto_canonico_id']
        if tipo not in PATRONES or not re.fullmatch(PATRONES[tipo], identificador):
            raise ValueError(f'Mapeo manual inválido: {tipo}/{identificador}')
        seleccion = resultado.producto_canonico_id.eq(pid)
        if int(seleccion.sum()) != 1:
            raise ValueError(f'Producto canónico inexistente o repetido: {pid}')
        pd.to_datetime(revision['fecha_validacion'], format='%Y-%m-%d', errors='raise')
        clave = (tipo, identificador)
        if clave in propietarios and propietarios[clave] != pid:
            raise ValueError(f'ID manual asignado a dos productos: {identificador}')
        propietarios[clave] = pid
        columna = COLUMNAS_IDS[tipo]
        if columna not in resultado:
            resultado[columna] = ''
        actuales = set(str(resultado.loc[seleccion, columna].iloc[0] or '').split(';')) - {''}
        actuales.add(identificador)
        resultado.loc[seleccion, columna] = ';'.join(sorted(actuales))
        resultado.loc[seleccion, 'confianza_match'] = 'exacto'
        resultado.loc[seleccion, 'notas'] = resultado.loc[seleccion, 'notas'].fillna('') + 'Validación manual explícita. '
    for tipo, columna in COLUMNAS_IDS.items():
        if columna not in resultado:
            continue
        propietarios = {}
        for fila in resultado.loc[resultado.confianza_match.eq('exacto')].to_dict('records'):
            for identificador in str(fila.get(columna) or '').split(';'):
                if not identificador:
                    continue
                if identificador in propietarios and propietarios[identificador] != fila['producto_canonico_id']:
                    raise ValueError(f'ID externo compartido después de validar: {tipo}/{identificador}')
                propietarios[identificador] = fila['producto_canonico_id']
    return resultado
