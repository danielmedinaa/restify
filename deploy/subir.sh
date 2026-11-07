#!/usr/bin/env bash
# Sube el código al ambiente del servidor, SIN secretos, dependencias ni datos locales.
# Uso (desde la raíz del proyecto):  ./deploy/subir.sh <dev|pre|pro> restify@IP
set -euo pipefail
ENTORNO="${1:-}"; DESTINO="${2:-}"
case "$ENTORNO" in dev|pre|pro) ;; *) echo "Uso: ./deploy/subir.sh <dev|pre|pro> restify@IP"; exit 1;; esac
[ -n "$DESTINO" ] || { echo "Uso: ./deploy/subir.sh <dev|pre|pro> restify@IP"; exit 1; }
cd "$(dirname "$0")/.."

# Lo que ya vive en el servidor (los .env, el socket, los datos) no se toca ni se borra
rsync -az --delete --human-readable --info=stats1 \
  --include='.env.example' --exclude='.env' --exclude='.env.*' \
  --exclude='node_modules/' --exclude='.next/' --exclude='.next-verify/' \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='.pytest_cache/' --exclude='.venv/' \
  --exclude='panel/data/' --exclude='panel/run/' --exclude='backend/media/' \
  --exclude='*.sqlite3' --exclude='*.tsbuildinfo' --exclude='.git/' --exclude='.github/' \
  ./ "$DESTINO:/srv/restify/$ENTORNO/app/"

echo "Código subido a $ENTORNO."
