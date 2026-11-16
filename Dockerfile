FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src SCONTO_API_DATOS=/data/intradia
COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt && useradd --system --uid 10001 sconto && test -x /usr/sbin/runuser
COPY src/sconto/__init__.py src/sconto/api_v2.py src/sconto/consulta_v2.py src/sconto/decisiones_v2.py src/sconto/intraday.py src/sconto/rutas.py src/sconto/respaldo_v2.py src/sconto/sincronizar_publico_v2.py /app/src/sconto/
COPY scripts/iniciar_api_fly.sh /app/iniciar_api_fly.sh
ENV SCONTO_API_CATALOGO=/data/catalogo.sqlite
EXPOSE 8080
CMD ["sh", "/app/iniciar_api_fly.sh"]
