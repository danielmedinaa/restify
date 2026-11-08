#!/usr/bin/env bash
# Carga una demostración COMPLETA en un cliente ya creado desde el panel: proveedores, compras con stock y costos,
# menú con recetas, mesas con QR, roles y usuarios. Se puede repetir sin duplicar nada.
#
# Desde tu PC:   ./deploy/demo.sh <dev|pre|pro> <cliente> [correo-del-administrador]
# Ej.:           ./deploy/demo.sh dev demobasic admin@demo.turestify.com
#
# Pide una contraseña (la misma para el administrador y los 3 usuarios demo) y la envía por la entrada estándar:
# no queda en el historial ni en la lista de procesos. Variables opcionales: VPS (usuario@ip), TASA_BCV, TOKEN.
set -euo pipefail
ENTORNO="${1:-}"; SUB="${2:-}"; CORREO="${3:-admin@demo.turestify.com}"
case "$ENTORNO" in dev|pre|pro) ;; *) echo "Uso: $0 <dev|pre|pro> <cliente> [correo-admin]"; exit 1;; esac
[ -n "$SUB" ] || { echo "Uso: $0 <dev|pre|pro> <cliente> [correo-admin]"; exit 1; }
VPS="${VPS:-root@45.13.235.240}"
TASA_BCV="${TASA_BCV:-36.50}"
[[ "$SUB" =~ ^[a-z0-9-]+$ && "$TASA_BCV" =~ ^[0-9.]+$ && "$CORREO" =~ ^[A-Za-z0-9._@+-]+$ ]] || { echo "Valores no válidos"; exit 1; }

read -r -s -p "Contraseña para el administrador y los usuarios demo (12+ caracteres, mayúsculas, minúsculas y números): " CLAVE; echo
[ "${#CLAVE}" -ge 12 ] || { echo "Muy corta"; exit 1; }

COMPOSE="/srv/restify/$ENTORNO/instancias/$SUB/docker-compose.yml"
EXTRA=""; [ -z "${TOKEN:-}" ] || EXTRA="--token '$TOKEN'"
printf '%s\n' "$CLAVE" | ssh "$VPS" \
  "docker compose -p restify-$ENTORNO-$SUB -f $COMPOSE exec -T api python -m app.cli preparar-demo --email '$CORREO' --password-stdin --tasa-bcv '$TASA_BCV' $EXTRA"
unset CLAVE
echo
echo "Listo. Abre https://$SUB.$([ "$ENTORNO" = pro ] && echo "" || echo "$ENTORNO.")turestify.com"
