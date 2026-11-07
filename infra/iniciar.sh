#!/usr/bin/env bash
# Arranca el agente con el secreto compartido de panel/.env
set -euo pipefail
cd "$(dirname "$0")"
[ -f ../panel/.env ] || { echo "Falta panel/.env"; exit 1; }
AGENTE_SECRETO="$(grep -E '^AGENTE_SECRETO=' ../panel/.env | cut -d= -f2-)"
export AGENTE_SECRETO
mkdir -p ../panel/run
exec python3 agente.py
