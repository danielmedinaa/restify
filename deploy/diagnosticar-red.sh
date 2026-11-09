#!/usr/bin/env bash
# Diagnóstico de red del servidor cuando Docker falla al descargar imágenes ("cannot assign requested address",
# "i/o timeout", IPv6). Casi todo es de solo lectura; solo descarga la imagen mínima hello-world (unos KB).
# Desde la carpeta del proyecto en tu PC:   ssh root@IP 'bash -s' < deploy/diagnosticar-red.sh
set -uo pipefail
ok() { echo "  ✅ $*"; }; mal() { echo "  ❌ $*"; }; titulo() { echo; echo "== $*"; }

titulo "1. IPv6 en el sistema (debe estar desactivado: 1)"
for k in all default lo eth0; do echo "  net.ipv6.conf.$k.disable_ipv6 = $(sysctl -n net.ipv6.conf.$k.disable_ipv6 2>/dev/null || echo '?')"; done
echo "  direcciones IPv6 activas: $(ip -6 addr show scope global 2>/dev/null | grep -c inet6)  (debe ser 0)"
[ -f /etc/sysctl.d/97-restify-sin-ipv6.conf ] && ok "existe /etc/sysctl.d/97-restify-sin-ipv6.conf (se aplica al arrancar)" || mal "NO existe /etc/sysctl.d/97-restify-sin-ipv6.conf"

titulo "2. ¿Cuándo arrancó Docker y cuándo se desactivó IPv6?"
echo "  Docker arrancó:        $(systemctl show docker -p ActiveEnterTimestamp --value)"
echo "  Servidor encendido:    $(uptime -s)"
echo "  Archivo de IPv6 creado: $(stat -c %y /etc/sysctl.d/97-restify-sin-ipv6.conf 2>/dev/null | cut -c1-19)"
echo "  Docker: $(docker info --format 'live-restore={{.LiveRestoreEnabled}}' 2>/dev/null)"

titulo "3. ¿Qué direcciones devuelve el DNS?"
for h in auth.docker.io registry-1.docker.io ghcr.io pkg-containers.githubusercontent.com; do
  echo "  $h -> $(getent ahosts "$h" | awk '{print $1}' | sort -u | tr '\n' ' ' | cut -c1-120)"
done

titulo "4. ¿Funciona la salida por IPv4? (curl -4)"
for h in auth.docker.io registry-1.docker.io ghcr.io; do
  c="$(curl -4 -s -o /dev/null -m 10 -w '%{http_code}' "https://$h/" || true)"
  case "$c" in 000|"") mal "IPv4 a $h: SIN respuesta" ;; *) ok "IPv4 a $h: HTTP $c" ;; esac
done

titulo "5. Descarga real con Docker (hello-world)"
if timeout 60 docker pull -q hello-world >/dev/null 2>&1; then ok "docker pull funciona"; else mal "docker pull FALLA. Detalle:"; timeout 60 docker pull hello-world 2>&1 | tail -3 | cut -c1-230; fi

titulo "6. ¿Con qué constructor construye Docker?"
docker buildx ls 2>/dev/null | head -5

titulo "Qué significa"
cat <<'EOF'
  • Sección 4 en ✅ y sección 5 en ❌  -> el problema es el propio Docker (sigue intentando IPv6): hay que reiniciar el servidor.
  • Sección 4 en ❌                    -> la salida por IPv4 falla: es un problema de red del proveedor (Contabo), no de Docker.
  • Sección 1 con valores distintos de 1 -> IPv6 no quedó desactivado: se vuelve a aplicar la configuración.
EOF
