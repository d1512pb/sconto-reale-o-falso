"""Categorías de consulta y selección de tecnología con evidencia en línea."""
import re

from sconto.normalizar import normalizar

CATEGORIAS = {
    'laptop': 'Computadoras y laptops', 'celular': 'Celulares', 'tablet': 'Tabletas',
    'audifonos': 'Audífonos', 'audio': 'Bocinas y audio', 'pantalla': 'Pantallas',
    'proyector': 'Proyectores', 'camara': 'Cámaras y lentes',
    'streaming': 'Streaming', 'hogar': 'Hogar inteligente', 'otros': 'Otra tecnología',
}


def categoria_app(nombre, familia, categoria=''):
    texto = normalizar(str(nombre))
    categoria = normalizar(str(categoria))
    if familia == 'asistente':
        return 'hogar'
    if 'PROYECTOR' in categoria or re.search(r'\b(PROYECTOR|PROJECTOR)\b', texto):
        return 'proyector'
    if familia == 'audio':
        return 'audifonos' if 'AUDIFONO' in categoria or re.search(r'\b(AUDIFONOS?|HEADPHONES?|HEADSET|EARBUDS?|AIRPODS|4GAMERS)\b', texto) else 'audio'
    if familia == 'streaming' and re.search(r'\b(TELEVISOR|PANTALLA|OLED|QLED)\b|\bTV\s+\d{2,3}', texto):
        return 'pantalla'
    return familia if familia in CATEGORIAS else 'otros'


def ampliar_seleccion(productos, observaciones, seleccion):
    """Conserva la prioridad diaria; añade sólo IDs nativos con precios públicos ya capturados."""
    online = observaciones.loc[observaciones.canal.eq('en_linea') & observaciones.precio.gt(0), 'producto_canonico_id']
    candidatos = productos.loc[productos.origen.eq('preciometro') & productos.producto_canonico_id.isin(online)]
    actuales = seleccion.producto_canonico_id.tolist()
    extra = sorted(set(candidatos.producto_canonico_id) - set(actuales))
    return actuales + extra
