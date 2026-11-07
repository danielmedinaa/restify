#!/usr/bin/env bash
# Despliega UN ambiente de RESTIFY en el servidor. Se corre como root (o con sudo), desde el código ya subido:
#   /srv/restify/<entorno>/app/deploy/desplegar.sh <dev|pre|pro> [opciones]
#
# Opciones:
#   --imagen-api REF --imagen-front REF   imágenes de los clientes (las manda GitHub Actions, desde ghcr.io).
#                                         Sin ellas se construyen en el servidor (primer arranque o emergencia).
#   --ghcr-usuario USUARIO                inicia sesión en ghcr.io; el token llega por la entrada estándar
#   --proxy                               reinstala y reinicia el proxy compartido (Caddy). Solo lo hace pro.
# Es idempotente: no cambia secretos existentes.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Corre esto como root (sudo)"; exit 1; }

ENTORNO="${1:-}"; shift || true
case "$ENTORNO" in dev|pre|pro) ;; *) echo "Uso: desplegar.sh <dev|pre|pro> [opciones]"; exit 1;; esac

IMAGEN_API=""; IMAGEN_FRONT=""; GHCR_USUARIO=""; FORZAR_PROXY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --imagen-api) IMAGEN_API="${2:?}"; shift 2;;
    --imagen-front) IMAGEN_FRONT="${2:?}"; shift 2;;
    --ghcr-usuario) GHCR_USUARIO="${2:?}"; shift 2;;
    --proxy) FORZAR_PROXY=1; shift;;
    *) echo "Opción desconocida: $1"; exit 1;;
  esac
done
# Las referencias llegan de fuera: solo caracteres válidos de una imagen
re='^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,200}$'
for r in "$IMAGEN_API" "$IMAGEN_FRONT"; do
  [ -z "$r" ] || [[ "$r" =~ $re ]] || { echo "Referencia de imagen no válida"; exit 1; }
done

BASE=/srv/restify
RAIZ="$BASE/$ENTORNO/app"
[ -f "$RAIZ/deploy/docker-compose.yml" ] || { echo "No hay código en $RAIZ (sube con deploy/subir.sh)"; exit 1; }
cd "$RAIZ"

[ -f "$BASE/config.env" ] || { echo "Falta $BASE/config.env (cp deploy/config.env.example y complétalo)"; exit 1; }
set -a; . "$BASE/config.env"; set +a
for v in DOMINIO ACME_EMAIL CLOUDFLARE_API_TOKEN; do
  [ -n "${!v:-}" ] || { echo "Define $v en $BASE/config.env"; exit 1; }
done

# pro vive en el dominio raíz; pre y dev en un subdominio propio
if [ "$ENTORNO" = pro ]; then BASE_DOMINIO="$DOMINIO"; else BASE_DOMINIO="$ENTORNO.$DOMINIO"; fi
PREFIJO="restify-$ENTORNO"
RED="restify-$ENTORNO-net"

secreto() { python3 -c "import secrets,sys; print(secrets.token_hex(int(sys.argv[1])//2))" "${1:-48}"; }

# ---------------------------------------------------------------- secretos y .env (solo si no existen)
if [ ! -f panel/.env ]; then
  PG="$(secreto 32)"
  cat > panel/.env <<EOF
PANEL_ENV=production
POSTGRES_DB=panel
POSTGRES_USER=panel
POSTGRES_PASSWORD=$PG
DATABASE_URL=postgresql+psycopg://panel:$PG@panel-db:5432/panel
SECRET_KEY=$(secreto 64)
CLAVE_CIFRADO=$(secreto 64)
DOMINIO_BASE=$BASE_DOMINIO
INSTANCIA_ESQUEMA=https
INSTANCIA_PUERTO=
PROXY_SALTOS=1
FORWARDED_ALLOW_IPS=*
SESION_INACTIVIDAD_MIN=20
SESION_MAXIMA_HORAS=8
AGENTE_SECRETO=$(secreto 56)
AGENTE_SOCKET=/run/agente/agente.sock
PANEL_URL=https://panel.$BASE_DOMINIO
PANEL_URL_INTERNA=http://panel:8000
ZONA_HORARIA_INSTANCIAS=${ZONA_HORARIA_INSTANCIAS:-America/Caracas}
APROVISIONADOR=agente
EOF
  chmod 600 panel/.env
  echo "[ok] panel/.env generado"
fi

if [ ! -f landing/.env ]; then
  cat > landing/.env <<EOF
LANDING_ENV=production
SECRET_KEY=$(secreto 64)
WHATSAPP_NUMERO=${WHATSAPP_NUMERO:-}
CONTACTO_EMAIL=${CONTACTO_EMAIL:-}
INSTAGRAM=${INSTAGRAM:-}
DEMO_URL=
PROXY_SALTOS=1
FORWARDED_ALLOW_IPS=*
LEADS_MAX_POR_IP=3
LEADS_VENTANA_MIN=30
TAWK_PROPERTY_ID=
TAWK_WIDGET_ID=
EOF
  chmod 600 landing/.env
  echo "[ok] landing/.env generado"
fi

# Banner fijo en dev y pre (landing, panel y front de los clientes). En producción queda vacío.
case "$ENTORNO" in dev) BANNER="DESARROLLO";; pre) BANNER="PRE PRODUCCION";; *) BANNER="";; esac
fijar() {  # fijar <archivo> <CLAVE> <valor>: agrega o actualiza una línea del .env
  if grep -q "^$2=" "$1"; then sed -i "s|^$2=.*|$2=$3|" "$1"; else printf '%s=%s\n' "$2" "$3" >> "$1"; fi
}
fijar panel/.env BANNER_ENTORNO "$BANNER"
fijar landing/.env BANNER_ENTORNO "$BANNER"

# Landing: "proximamente" (por defecto) muestra una página de espera en vez de la landing y bloquea el formulario.
# Para abrirla: LANDING_MODO=abierta en /srv/restify/config.env y volver a desplegar.
fijar landing/.env LANDING_MODO "${LANDING_MODO:-proximamente}"
# Datos de contacto: se sincronizan en cada despliegue (cambia config.env y despliega; no hace falta editar a mano)
[ -z "${WHATSAPP_NUMERO:-}" ] || fijar landing/.env WHATSAPP_NUMERO "$WHATSAPP_NUMERO"
[ -z "${CONTACTO_EMAIL:-}" ] || fijar landing/.env CONTACTO_EMAIL "$CONTACTO_EMAIL"
[ -z "${INSTAGRAM:-}" ] || fijar landing/.env INSTAGRAM "$INSTAGRAM"

# Variables del compose de este ambiente (ENTORNO decide el nombre de la red)
printf 'ENTORNO=%s\n' "$ENTORNO" > deploy/.env

# ---------------------------------------------------------------- imágenes de los clientes
install -d -o restify -g restify -m 755 panel/run
install -d -o restify -g restify -m 700 "$BASE/$ENTORNO/instancias" "$BASE/$ENTORNO/respaldos"
for e in dev pre pro; do docker network inspect "restify-$e-net" >/dev/null 2>&1 || docker network create "restify-$e-net"; done

PULL=0
if [ -n "$IMAGEN_API" ] && [ -n "$IMAGEN_FRONT" ]; then
  PULL=1
  if [ -n "$GHCR_USUARIO" ]; then
    # El agente corre como "restify": la sesión de ghcr.io debe ser de ese usuario
    IFS= read -r GHCR_TOKEN
    printf '%s' "$GHCR_TOKEN" | runuser -u restify -- docker login ghcr.io -u "$GHCR_USUARIO" --password-stdin
    unset GHCR_TOKEN
  fi
  runuser -u restify -- docker pull "$IMAGEN_API"
  runuser -u restify -- docker pull "$IMAGEN_FRONT"
else
  # Sin registro: se construyen aquí con una etiqueta propia del ambiente (no pisan a los otros)
  IMAGEN_API="restify-api:$ENTORNO"; IMAGEN_FRONT="restify-front:$ENTORNO"
  docker build -t "$IMAGEN_API" backend
  docker build -t "$IMAGEN_FRONT" --build-arg NEXT_PUBLIC_WS_URL= front
fi

# ---------------------------------------------------------------- agente de este ambiente
AG="$(grep -E '^AGENTE_SECRETO=' panel/.env | cut -d= -f2-)"
cat > "$BASE/$ENTORNO/agente.env" <<EOF
AGENTE_SECRETO=$AG
AGENTE_SOCKET=$RAIZ/panel/run/agente.sock
AGENTE_INSTANCIAS=$BASE/$ENTORNO/instancias
AGENTE_RESPALDOS=$BASE/$ENTORNO/respaldos
AGENTE_PREFIJO=$PREFIJO
AGENTE_RED=$RED
AGENTE_PROXY=restify-proxy-caddy-1
AGENTE_PANEL=$PREFIJO-panel-1
AGENTE_PULL=$PULL
AGENTE_BANNER=$BANNER
IMAGEN_API=$IMAGEN_API
IMAGEN_FRONT=$IMAGEN_FRONT
EOF
chown restify:restify "$BASE/$ENTORNO/agente.env"; chmod 600 "$BASE/$ENTORNO/agente.env"

install -m 644 deploy/restify-agente@.service deploy/restify-respaldos@.service deploy/restify-respaldos@.timer /etc/systemd/system/
systemctl daemon-reload
chown -R restify:restify "$RAIZ"
systemctl enable "restify-agente@$ENTORNO.service" >/dev/null
systemctl restart "restify-agente@$ENTORNO.service"
# Los respaldos automáticos solo corren en producción
[ "$ENTORNO" != pro ] || systemctl enable --now "restify-respaldos@$ENTORNO.timer" >/dev/null

# ---------------------------------------------------------------- panel y landing
docker compose -p "$PREFIJO" -f deploy/docker-compose.yml --env-file deploy/.env up -d --build --remove-orphans

# ---------------------------------------------------------------- proxy compartido
if [ "$FORZAR_PROXY" -eq 1 ] || ! docker ps -a --format '{{.Names}}' | grep -qx 'restify-proxy-caddy-1'; then
  install -d -m 755 "$BASE/proxy"
  cp deploy/proxy/Caddyfile deploy/proxy/Dockerfile deploy/proxy/docker-compose.yml "$BASE/proxy/"
  ( umask 077
    printf 'DOMINIO=%s\nACME_EMAIL=%s\nCLOUDFLARE_API_TOKEN=%s\n' "$DOMINIO" "$ACME_EMAIL" "$CLOUDFLARE_API_TOKEN" > "$BASE/proxy/.env"
    # Opcional: solo estas IPs/rangos (separados por espacio) pueden abrir el panel. Vacío = sin restricción.
    [ -z "${PANEL_IPS_PERMITIDAS:-}" ] || printf 'PANEL_IPS_PERMITIDAS=%s\n' "$PANEL_IPS_PERMITIDAS" >> "$BASE/proxy/.env" )
  docker compose -f "$BASE/proxy/docker-compose.yml" up -d --build
fi

# ---------------------------------------------------------------- nuevas versiones de los clientes
# Respalda, cambia de versión una instancia por vez y vuelve atrás si una falla. Las instancias nuevas ya nacen con esta versión.
if [ "$PULL" -eq 1 ]; then
  runuser -u restify -- bash -c 'set -a; . "$1"; set +a; cd "$2/infra"; exec python3 agente.py actualizar --api "$3" --front "$4"' _ \
    "$BASE/$ENTORNO/agente.env" "$RAIZ" "$IMAGEN_API" "$IMAGEN_FRONT"
fi

# El panel y el proxy pueden haberse recreado y pierden las redes de las instancias: se vuelven a unir (idempotente)
runuser -u restify -- bash -c 'set -a; . "$1"; set +a; cd "$2/infra"; exec python3 agente.py reconectar' _ \
  "$BASE/$ENTORNO/agente.env" "$RAIZ" || echo "AVISO: alguna instancia no pudo reconectarse (¿es anterior al aislamiento? se corrige al actualizarla)"

# Vigilancia: revisa cada 5 min y avisa por Telegram si se configuró (deploy/vigilar.sh)
install -m 755 deploy/vigilar.sh /usr/local/bin/restify-vigilar
install -m 644 deploy/restify-vigilar.service deploy/restify-vigilar.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now restify-vigilar.timer >/dev/null

# El token de ghcr.io caduca al terminar el workflow: no lo dejamos guardado en disco
[ -z "$GHCR_USUARIO" ] || runuser -u restify -- docker logout ghcr.io >/dev/null 2>&1 || true

echo
docker compose -p "$PREFIJO" -f deploy/docker-compose.yml --env-file deploy/.env ps
cat <<EOF

Listo ($ENTORNO):
  https://$BASE_DOMINIO         (landing)
  https://panel.$BASE_DOMINIO   (panel)

Primer despliegue de este ambiente: crea tu usuario del panel
  docker compose -p $PREFIJO -f $RAIZ/deploy/docker-compose.yml --env-file $RAIZ/deploy/.env exec panel flask --app wsgi crear-superadmin
EOF
