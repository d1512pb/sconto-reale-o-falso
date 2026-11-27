FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src SCONTO_API_DATOS=/data/intradia
COPY requirements-api.txt requirements-respaldo.txt requirements-colector.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends age libarchive-tools \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements-api.txt -r requirements-colector.txt -r requirements-respaldo.txt \
    && useradd --system --user-group --uid 10001 sconto \
    && test -x /usr/sbin/runuser
COPY src/sconto/__init__.py src/sconto/api_v2.py src/sconto/consulta_v2.py src/sconto/decisiones_v2.py src/sconto/intraday.py src/sconto/rutas.py src/sconto/respaldo_v2.py src/sconto/sincronizar_publico_v2.py /app/src/sconto/
COPY src/sconto/cliente.py src/sconto/colector_nube_v2.py src/sconto/operacion_profeco_bf_v2.py src/sconto/importar_profeco_bf_v2.py src/sconto/respaldo_nube_v2.py /app/src/sconto/
COPY src/sconto/presupuesto_fly_v2.py /app/src/sconto/
# v3 · modelo final y app servida desde el mismo origen (corte del 26 de noviembre de 2026)
COPY src/sconto/api_modelo.py src/sconto/prediccion_ligera.py /app/src/sconto/
COPY data/operacion/v2/app_v3/site /app/sitio
COPY data/operacion/v2/app_v3/modelo /app/modelo
ENV SCONTO_API_SITIO=/app/sitio SCONTO_API_MODELO=/app/modelo SCONTO_API_DOCS=1
COPY src/sconto/fuentes/__init__.py src/sconto/fuentes/profeco_buenfin.py src/sconto/fuentes/qqp_archivo.py src/sconto/fuentes/qqp_vigilar.py /app/src/sconto/fuentes/
COPY scripts/iniciar_api_fly.sh scripts/supervisar_fly_v2.py /app/
ENV SCONTO_API_CATALOGO=/data/catalogo.sqlite
EXPOSE 8080
CMD ["sh", "/app/iniciar_api_fly.sh"]
