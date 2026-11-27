# Comprobación de la vista pública de Sconto v2

## Android y frontend público

El APK experimental 2.0.0 descargado de GitHub conserva el SHA-256 `a9c15efee6553f1de196424d1c9853859393acddfcebfafbfd326b0f2eb78ec0`. El DEX contiene `https://d1512pb.github.io/sconto-reale-o-falso/` como inicio del WebView. `NavigationPolicy` admite la raíz del proyecto o su `index.html` en ese dominio. [APK experimental](https://github.com/d1512pb/sconto-reale-o-falso/releases/tag/android-v2.0.0)

A las 00:33 CDMX del 16 de noviembre la raíz y su `app.mjs` devolvían HTTP 200. El HTML carecía de la configuración `sconto-api` y el módulo JavaScript carecía de la importación `api.mjs` y del comparador actual. El cliente Android necesita que la versión pública de la página principal contenga esas funciones. ADB ejecutado el mismo día no enumeró dispositivos. [Frontend público](https://d1512pb.github.io/sconto-reale-o-falso/)

## Paridad local con datos publicables

Se verificó la integridad SQLite de las dos entradas de `data/operacion/v2/fly_preparacion_20261116/solo_datos_publicables`.

- `catalogo.sqlite` contiene 1493 entradas con identificador, nombre y categoría y tres ventanas de evento. SHA-256 `30be5a4e137ec8ea3b73ee1373c7f9e3cfb3fabcf9dc78b17ed4e33cde349ee4`.
- `intradia.sqlite3` contiene el esquema operativo con cero filas en sus seis tablas. SHA-256 `f4db8dde68f64830b16e000196c672a52ffae2f15de3250361eb8148f28be9ef`.

Un kernel local limpio ejecutó ambas celdas de código del notebook 05. El producto `P4-1960`, la visibilidad pública y la hora `2026-11-16T06:33:00+00:00` se fijaron también en la API local. Las rutas de ofertas, decisión y comparación devolvieron HTTP 200. Se comprobaron la igualdad de las listas de ofertas y de la comparación, los conjuntos vacíos de decisiones y la coincidencia de hora y versión `precio-v2-provisional`. La comparación devolvió `evidencia_insuficiente` por `menos_de_dos_ofertas_actuales_comparables`, con cero ofertas visibles, evaluables o con historia suficiente.

El código embebido del notebook tenía SHA-256 `639e4147bbd3e978089d2b16629927b3f1dafb76f5c73d9c5fbd5de40170e032`. Se comparó con los seis módulos de trabajo tras normalizar finales de línea. La evidencia local está en `data/operacion/v2/prueba_colab05_publicable_kernel_20261116/`. La prueba técnica confirma la respuesta con inventario vacío. La validación de una oferta online requiere una muestra real autorizada.

## Intento de Colab alojado

Se abrió la revisión pública `5c8d1176d82b5371c42a6adeeb0a21e4b7b6110e` y se conectó un entorno nuevo en Google Compute Engine con Python 3. La extensión de Chrome bloqueó el selector de los dos SQLite porque exige acceso a las URL de archivos locales. El entorno quedó sin archivos transferidos y sin celdas ejecutadas. La prueba con la API pública queda pendiente de su despliegue. [Notebook 05 fijado por commit](https://colab.research.google.com/github/d1512pb/sconto-reale-o-falso/blob/5c8d1176d82b5371c42a6adeeb0a21e4b7b6110e/notebooks/05_Sconto_Operativo_v2.ipynb)
