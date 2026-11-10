# Revisión de Sconto

Sconto reúne precios de tecnología y su historia para apoyar una compra. La app permite buscar, filtrar tiendas y leer la evidencia de cada señal. No requiere cuentas ni publicaciones. Separa precios físicos y en línea, vendedores y variantes; no interpreta una anomalía como fraude.

## Recorrido para la revisión académica

1. Abrir [el notebook CRISP-DM en Colab](https://colab.research.google.com/github/d1512pb/sconto-reale-o-falso/blob/main/notebooks/03_Sconto_CRISP_DM_ETL_web.ipynb). Documenta las seis fases, limpieza, minería, evaluación y exportación. La demo escolar se realiza allí.
2. Consultar los [paquetes de datos](https://github.com/d1512pb/sconto-reale-o-falso/releases/tag/datos). El notebook fija un corte del 7 de noviembre y comprueba sus huellas; el paquete diario cambia con la recolección.
3. Abrir [la app web](https://d1512pb.github.io/sconto-reale-o-falso/) o [descargar Sconto para Android](https://github.com/d1512pb/sconto-reale-o-falso/releases/tag/android-v1.0.1).
4. Buscar AirPods o Lenovo IdeaPad, seleccionar la variante y revisar tienda, fecha, historial y explicación. Los precios antiguos o no comparables se muestran como evidencia insuficiente.

## Dónde está cada parte

| Parte | Código o documentación |
|---|---|
| Notebook y metodología | [notebooks/03_Sconto_CRISP_DM_ETL_web.ipynb](notebooks/03_Sconto_CRISP_DM_ETL_web.ipynb) |
| Extracción y limpieza | [src/sconto/fuentes/](src/sconto/fuentes/), [dataset.py](src/sconto/dataset.py) |
| Modelado y búsqueda | [mineria.py](src/sconto/mineria.py), [compra.py](src/sconto/compra.py) |
| Salida para la app | [mart.py](src/sconto/mart.py), [CONTRATO_APP.md](CONTRATO_APP.md) |
| Interfaz web instalable | [web/](web/), [publicar_web.py](src/sconto/publicar_web.py) |
| Proyecto Android completo | [android/](android/), [compilación e instalación](android/README.md) |
| Diccionario | [DICCIONARIO.md](DICCIONARIO.md) |
| Pruebas y ejecución diaria | [tests/](tests/), [.github/workflows/](.github/workflows/), [reports/](reports/) |

## Qué demuestra y qué sigue pendiente

El notebook reconstruye 683,942 observaciones y reproduce las cifras del primer avance. Isolation Forest se entrena con 2024 y se evalúa retrospectivamente con 2025. El puntaje ordena anomalías; no es probabilidad de fraude. Las señales de compra de la app usan reglas de precio, antigüedad y cobertura, explicadas por separado.

La app amplió la consulta a 1,493 productos; la lista de seguimiento diario conserva 200. Tener un producto en el catálogo no garantiza precio actual, inventario ni identidad comercial verificada. La comprobación de variantes, condiciones y utilidad durante una compra real continúa.

Se conserva evidencia de pruebas de navegador y del teléfono Android. El notebook se ejecutó completo localmente y la copia con resultados se guardó en Drive; no se presenta esa ejecución como realizada en la nube de Colab. Los reportes distinguen resultados locales, pruebas físicas y ejecuciones de GitHub Actions.

El repositorio contiene el código necesario para reconstruir la solución. Los datos voluminosos y los instaladores están en Releases. Las claves privadas de firma, credenciales y crudos de tiendas permanecen fuera del repositorio público.
