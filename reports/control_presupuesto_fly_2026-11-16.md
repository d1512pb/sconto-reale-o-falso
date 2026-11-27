# Control de gasto de Sconto en Fly

El límite solicitado es US$4 mensuales. La única máquina existente de Ashburn se redujo a 256 MB y conservó el volumen de 1 GB. Con precios de Ashburn, 31 días de cómputo, el volumen y 5 GB de salida se estiman en US$2.52 antes de otros cargos. [Precios de Fly](https://docs.fly.io/about/pricing)

Fly no ofrece un tope de factura ni alertas de facturación. La aplicación aplica un corte preventivo al llegar a 5 GB de salida medidos por la máquina en el mes UTC. El cálculo conservador reserva US$2.80 para cómputo, almacenamiento y margen, y US$0.60 para transferencia, con un umbral estimado de US$3.40. La medición no puede detectar cargos ajenos a la máquina ni sustituir la factura. El almacenamiento puede seguir facturando al apagarla. [Gestión de costos](https://docs.fly.io/about/cost-management)

El contador se guarda en el volumen y persiste entre reinicios. El corte realiza una salida normal del servicio, con política de reinicio sólo por error y arranque por tráfico desactivado. Una vez activado, el corte se conserva durante el resto del mes UTC. El arranque del mes siguiente requiere una acción de operador.

Se verificó el corte con un contador simulado en un contenedor limitado a 256 MB. La API y el colector local de ensayo sirvieron 2,803 observaciones físicas archivadas y produjeron una copia cifrada. El pico medido fue 113.41 MiB. Pasaron trece pruebas focalizadas. Este ensayo no usó el bucket externo.

En Fly se confirmó una sola máquina de 256 MB, un volumen y el contador activo. La política de reinicio es `on-failure` y el arranque por tráfico está desactivado. La API pública responde con la revisión `presupuesto-256-20261116`. [Versión de la API](https://sconto-v2-api.fly.dev/v1/version)
