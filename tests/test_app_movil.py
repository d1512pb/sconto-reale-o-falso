import json
from pathlib import Path
import shutil
import subprocess

import pandas as pd
import pytest

from sconto.compra import Buscador


@pytest.mark.skipif(not shutil.which('node'), reason='Node necesario para el motor móvil')
def test_busqueda_javascript_equivale_a_notebook():
    catalogo = pd.DataFrame({'producto_canonico_id': ['P1','P2','P3','P4','P5','P6','P7','P8','P9','P10','P11','P12'], 'nombre': [
        'Apple AirPods Pro 3 Blanco', 'Apple AirPods 3', 'Apple AirPods Pro 2',
        'Laptop Lenovo IdeaPad Slim 3 i3 8GB RAM 512GB SSD Azul',
        'Laptop Lenovo IdeaPad Slim 3 i5 24GB RAM 1TB SSD Gris',
        'Lenovo IdeaPad Slim 3 i3 8GB RAM 128GB Chromebook', 'Apple iPhone 16 Pro 128GB', 'Apple iPhone 16 128GB',
        'Samsung Galaxy Tab A9 64GB', 'Samsung Galaxy Tab A9+ 64GB', 'iPad Air 256GB', 'iPad Pro 256GB']})
    buscador = Buscador(catalogo)
    consultas = ['airpods pro 3', 'AirPods 3 Pro', 'AIRPODS', 'audífonos', 'Lenobo IdeaPad Slim 3 i3 8GB RAM 512GB SSD',
                 'Lenovo i5 24GB RAM 1TB SSD', '512GB', '128GB Chromebook', 'zzzzqqq producto inexistente', 'a', 'airpds pro 3',
                 'iPhone 16 128GB', 'iPhone 16 Pro', 'Galaxy Tab A9+', 'iPad Air']
    modulo = (Path('web')/'motor.mjs').resolve().as_uri()
    codigo = 'import {buscar} from '+json.dumps(modulo)+";let s='';for await(const b of process.stdin)s+=b;const d=JSON.parse(s);console.log(JSON.stringify(d.consultas.map(q=>buscar(q,d.productos,d.indice,5).map(p=>[p.producto_canonico_id,p.similitud]))));"
    resultado = subprocess.run(['node','--input-type=module','-e',codigo],input=json.dumps(dict(
        consultas=consultas,productos=catalogo.to_dict('records'),indice=buscador.indice())),text=True,capture_output=True,check=True)
    for q, filas in zip(consultas,json.loads(resultado.stdout),strict=True):
        esperado = buscador.buscar(q)
        assert [f[0] for f in filas] == esperado.producto_canonico_id.tolist(), q
        assert [f[1] for f in filas] == pytest.approx(esperado.similitud.tolist()), q


@pytest.mark.skipif(not shutil.which('node'), reason='Node necesario para pruebas de funcionamiento sin red')
def test_vigencia_enlaces_y_copia_verificada():
    subprocess.run(['node','--test','tests/app_motor.test.mjs','tests/app_datos.test.mjs'],check=True)
