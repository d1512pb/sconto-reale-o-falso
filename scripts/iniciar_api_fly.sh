#!/bin/sh
set -eu
test -n "${SCONTO_API_DATOS:-}"
# La cuenta de servicio recibe el almacén completo, incluso tras restaurar una copia.
mkdir -p "$SCONTO_API_DATOS"
test ! -L "$SCONTO_API_DATOS"
chown -hR sconto:sconto "$SCONTO_API_DATOS"
if [ -n "${SCONTO_API_CATALOGO:-}" ] && [ ! -f "$SCONTO_API_CATALOGO" ]; then
    unset SCONTO_API_CATALOGO
fi
exec python /app/supervisar_fly_v2.py
