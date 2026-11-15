#!/bin/sh
set -eu
test -n "${SCONTO_API_DATOS:-}"
# Fly monta un volumen vacío como root. Entregar sólo el directorio SQLite a la cuenta de servicio.
mkdir -p "$SCONTO_API_DATOS"
chown sconto "$SCONTO_API_DATOS"
if [ -f "$SCONTO_API_DATOS/intradia.sqlite3" ]; then
    chown sconto "$SCONTO_API_DATOS/intradia.sqlite3"
fi
if [ -n "${SCONTO_API_CATALOGO:-}" ] && [ ! -f "$SCONTO_API_CATALOGO" ]; then
    unset SCONTO_API_CATALOGO
fi
export SCONTO_API_REVISION_PRIVADA=0
exec su -s /bin/sh sconto -c 'exec python -m uvicorn sconto.api_v2:app --factory --host 0.0.0.0 --port 8080 --workers 1 --no-proxy-headers --no-server-header --limit-concurrency 32 --timeout-keep-alive 5'
