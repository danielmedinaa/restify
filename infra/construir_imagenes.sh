#!/usr/bin/env bash
# Construye UNA vez las imágenes que usan todas las instancias. Repite cuando cambies el código.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t restify-api:latest backend
# NEXT_PUBLIC_WS_URL vacío: el front arma la URL del WebSocket con el dominio de la página (sirve para cualquier instancia)
docker build -t restify-front:latest --build-arg NEXT_PUBLIC_WS_URL= front
echo "Listo: restify-api:latest y restify-front:latest"
