import pandas as pd
import pytest

from sconto.catalogo import ampliar_seleccion, categoria_app
from sconto.compra import atributos, identidad_oferta


@pytest.mark.parametrize('nombre,familia,categoria,esperada', [
    ('Galaxy Tab A9', 'tablet', 'Samsung', 'tablet'),
    ('iPhone 16', 'celular', 'Apple', 'celular'),
    ('Roku TV 55 pulgadas', 'streaming', 'Otros', 'pantalla'),
    ('Fire TV Stick 4K', 'streaming', 'Otros', 'streaming'),
    ('Sony lente para cámara', 'camara', 'Otros', 'camara'),
    ('Foco compatible con Alexa', 'asistente', 'Bombillas Inteligentes', 'hogar'),
    ('Hisense Laser TV', 'pantalla', 'Proyectores Láser', 'proyector'),
    ('JBL audífonos', 'audio', 'Otros', 'audifonos'),
    ('JBL bocina portátil', 'audio', 'Bocinas Bluetooth', 'audio'),
])
def test_categoria_no_confunde_sistema_operativo_con_aparato(nombre, familia, categoria, esperada):
    assert categoria_app(nombre, familia, categoria) == esperada


def test_amplia_solo_ids_con_evidencia_online_y_conserva_prioridad():
    productos = pd.DataFrame({'producto_canonico_id':['A','B','C','D'], 'origen':['preciometro','preciometro','qqp','preciometro']})
    obs = pd.DataFrame({'producto_canonico_id':['A','B','C'], 'precio':[1,2,3], 'canal':['en_linea','en_linea','tienda_fisica']})
    original = pd.DataFrame({'producto_canonico_id':['B']})
    assert ampliar_seleccion(productos, obs, original) == ['B','A']


@pytest.mark.parametrize('a,b', [
    ('Apple iPhone 16 128GB', 'Apple iPhone 16 Pro 128GB'),
    ('Samsung Galaxy Tab A9 64GB', 'Samsung Galaxy Tab A9+ 64GB'),
    ('Galaxy S24 256GB', 'Galaxy S25 256GB'),
    ('Apple iPad Air 256GB', 'Apple iPad Pro 256GB'),
])
def test_variantes_moviles_contradictorias(a, b):
    assert identidad_oferta(a, b)[0] == 'conflicto'


def test_no_certifica_telefonos_distintos_por_compartir_capacidad():
    assert identidad_oferta('Motorola Moto G15 256GB Negro', 'Motorola Moto G35 256GB Negro')[0] == 'pendiente'
    assert atributos('iPhone 16 Pro Max 256GB')['iphone'] == '16PROMAX'
