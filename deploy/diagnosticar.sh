#!/usr/bin/env bash
# Diagnóstico de SOLO LECTURA de un cliente que muestra "Servicio no disponible". No cambia nada.
# Desde tu PC:   ssh root@IP 'bash -s -- <dev|pre|pro> <cliente>' < deploy/diagnosticar.sh
# Ej.:           ssh root@45.13.235.240 'bash -s -- dev demobasic' < deploy/diagnosticar.sh
set -uo pipefail
ENTORNO="${1:?Uso: bash -s -- <dev|pre|pro> <cliente>}"; SUB="${2:?Falta el cliente}"
PREF="restify-$ENTORNO-$SUB"; RED="$PREF-edge"; PROXY=restify-proxy-caddy-1; PANEL="restify-$ENTORNO-panel-1"
ok() { echo "  ✅ $*"; }; mal() { echo "  ❌ $*"; }; titulo() { echo; echo "== $*"; }

titulo "1. Contenedores del cliente ($PREF-*)"
docker ps -a --filter "name=^${PREF}-" --format '  {{.Names}}  {{.Status}}' | sort
for s in db redis api front; do
  est="$(docker inspect -f '{{.State.Status}}' "$PREF-$s-1" 2>/dev/null || echo "no existe")"
  [ "$est" = running ] && ok "$s: running" || mal "$s: $est"
done

titulo "2. Red propia del cliente ($RED)"
if docker network inspect "$RED" >/dev/null 2>&1; then
  ok "la red existe. Contenedores conectados:"
  docker network inspect "$RED" -f '{{range .Containers}}    - {{.Name}}{{"\n"}}{{end}}'
  for c in "$PROXY" "$PANEL"; do
    docker network inspect "$RED" -f '{{range .Containers}}{{.Name}} {{end}}' | grep -qw "$c" && ok "$c está conectado" || mal "$c NO está conectado (esto causa 'Servicio no disponible')"
  done
else
  mal "la red no existe: el cliente aún usa la configuración anterior (sin aislamiento) o no se actualizó"
  echo "  Redes del cliente en Docker:"; docker network ls --format '    {{.Name}}' | grep "$PREF" || echo "    (ninguna)"
fi

titulo "3. ¿Caddy llega al front y a la API del cliente?"
for destino in "$PREF-front-1:3000" "$PREF-api-1:8000/health"; do
  if docker exec "$PROXY" wget -q -T 4 -O /dev/null "http://$destino" 2>/dev/null; then ok "responde http://$destino"; else mal "NO responde http://$destino"; fi
done

titulo "4. Últimos errores de Caddy sobre este cliente"
docker logs --tail 300 "$PROXY" 2>&1 | grep -i "$SUB" | grep -i -E 'error|dial|lookup|no such host' | tail -4 | cut -c1-230 || true

titulo "5. Agente de $ENTORNO (últimas líneas)"
journalctl -u "restify-agente@$ENTORNO" -n 12 --no-pager 2>/dev/null | cut -c1-200

titulo "6. Cómo arreglarlo según lo que salió"
cat <<EOF
  • Si el cliente está detenido o pausado: desde el panel, "Reanudar".
  • Si Caddy/el panel NO están conectados a la red: reconecta con
      runuser -u restify -- bash -c 'set -a; . /srv/restify/$ENTORNO/agente.env; set +a; cd /srv/restify/$ENTORNO/app/infra; python3 agente.py reconectar --sub $SUB'
  • Si la red no existe: despliega de nuevo ese ambiente (migra el cliente a su red propia al actualizarlo).
  • Si un contenedor está "exited" o "restarting": mira sus logs con  docker logs --tail 50 $PREF-api-1
EOF
