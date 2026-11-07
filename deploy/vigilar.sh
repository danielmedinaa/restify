#!/usr/bin/env bash
# Vigilancia del servidor: corre cada 5 minutos (restify-vigilar.timer). Revisa disco, memoria, contenedores,
# que las páginas respondan y que los certificados no estén por vencer. Avisa SOLO cuando algo cambia
# (aparece un problema o se resuelve). Sin Telegram configurado, deja el aviso en el log (journalctl -u restify-vigilar).
set -uo pipefail
[ -f /srv/restify/config.env ] && { set -a; . /srv/restify/config.env; set +a; }
DOMINIO="${DOMINIO:-}"
ESTADO="${ESTADO_VIGILAR:-/var/lib/restify-vigilar.estado}"
problemas=()

# --- disco y memoria
uso_disco="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
[ "${uso_disco:-0}" -lt 85 ] || problemas+=("Disco al ${uso_disco}%")
mem_libre="$(awk '/MemAvailable/ {d=$2} /MemTotal/ {t=$2} END {printf "%d", d*100/t}' /proc/meminfo)"
[ "${mem_libre:-100}" -gt 10 ] || problemas+=("Memoria disponible: ${mem_libre}%")

# --- contenedores de la plataforma (caddy, panel, base del panel y landing de cada ambiente)
for c in $(docker ps -a --format '{{.Names}}' | grep -E '^restify-(proxy-caddy|(dev|pre|pro)-(panel|panel-db|landing))-1$'); do
  [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = true ] || problemas+=("Caído: $c")
done
# ...y cualquier contenedor reportado como "unhealthy" o en reinicio continuo (las instancias pausadas a propósito no cuentan)
while read -r nombre estado; do
  case "$estado" in *unhealthy*|*Restarting*) problemas+=("Con fallas: $nombre");; esac
done < <(docker ps -a --filter 'name=restify-' --format '{{.Names}} {{.Status}}')

# --- páginas y certificados
if [ -n "$DOMINIO" ]; then
  for host in "$DOMINIO" "panel.$DOMINIO"; do
    codigo="$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$host/" || true)"
    case "$codigo" in 2*|3*|401|403) ;; *) problemas+=("https://$host respondió ${codigo:-sin respuesta}");; esac
  done
  fin="$(echo | timeout 10 openssl s_client -connect "$DOMINIO:443" -servername "$DOMINIO" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
  if [ -n "$fin" ]; then
    dias=$(( ($(date -d "$fin" +%s) - $(date +%s)) / 86400 ))
    [ "$dias" -gt 14 ] || problemas+=("El certificado de $DOMINIO vence en ${dias} días")
  else
    problemas+=("No se pudo leer el certificado de $DOMINIO")
  fi
fi

# --- avisar solo si cambió algo
actual="$(printf '%s\n' "${problemas[@]:-}" | sed '/^$/d' | sort)"
anterior="$(cat "$ESTADO" 2>/dev/null || true)"
[ "$actual" = "$anterior" ] && exit 0
printf '%s\n' "$actual" > "$ESTADO"

if [ -n "$actual" ]; then mensaje="⚠️ RESTIFY ($(hostname))"$'\n'"$actual"; else mensaje="✅ RESTIFY ($(hostname)): todo volvió a la normalidad"; fi
echo "$mensaje"
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  curl -s -m 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${mensaje}" >/dev/null || true
fi
