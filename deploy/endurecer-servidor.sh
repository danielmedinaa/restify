#!/usr/bin/env bash
# Endurece el servidor. Idempotente: se puede repetir. Como root, desde tu PC:
#   ssh root@IP 'bash -s' < deploy/endurecer-servidor.sh
#
# 1) SSH: solo con llave (sin contraseña), root solo con llave, menos intentos, sin reenvíos innecesarios.
#    ⚠️  Antes de correrlo comprueba que entras con tu llave. Mantén ESTA sesión abierta y abre otra para probar.
# 2) fail2ban: bloquea IPs que fallan el SSH.
# 3) Red del sistema: protecciones básicas contra SYN flood, redirecciones y rutas de origen.
# 4) Docker: logs con tope, miles de redes disponibles (una por cliente) y live-restore.
#    Reiniciar Docker corta los contenedores unos segundos SOLO la primera vez que cambia esta configuración.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Corre esto como root"; exit 1; }

# ---------------------------------------------------------------- 1) SSH
if ! [ -s /root/.ssh/authorized_keys ]; then
  echo "ABORTO: /root/.ssh/authorized_keys está vacío. Sin una llave autorizada te quedarías fuera del servidor."
  exit 1
fi
install -d -m 755 /etc/ssh/sshd_config.d
# Prefijo 00-: sshd usa el PRIMER valor que lee, y archivos como 50-cloud-init.conf activan PasswordAuthentication
cat > /etc/ssh/sshd_config.d/00-restify.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
EOF
sshd -t
systemctl reload ssh || systemctl reload sshd
efectivo="$(sshd -T | awk '/^passwordauthentication /{print $2}')"
[ "$efectivo" = "no" ] || { echo "AVISO: PasswordAuthentication sigue en '$efectivo'; revisa /etc/ssh/sshd_config.d/"; }
echo "[ok] SSH: passwordauthentication=$efectivo"

# ---------------------------------------------------------------- 2) fail2ban
cat > /etc/fail2ban/jail.d/restify-sshd.local <<'EOF'
[sshd]
enabled  = true
maxretry = 4
findtime = 10m
bantime  = 1h
EOF
systemctl enable --now fail2ban >/dev/null
systemctl restart fail2ban
echo "[ok] fail2ban: sshd 4 intentos / 10 min => 1 h"

# ---------------------------------------------------------------- 3) red del sistema
cat > /etc/sysctl.d/98-restify-red.conf <<'EOF'
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
EOF
sysctl -q -p /etc/sysctl.d/98-restify-red.conf
echo "[ok] sysctl de red"

# Este servidor solo usa IPv4 (el DNS tiene registros A). Con IPv6 activo pero sin ruta, Docker y Caddy se quedan
# esperando ("i/o timeout" / "network is unreachable") al descargar imágenes o pedir certificados.
# Los programas en Go (Docker incluido) detectan si hay IPv6 UNA vez, al arrancar: si se desactiva con Docker ya corriendo,
# hay que reiniciarlo para que deje de intentar esa ruta (se hace más abajo).
[ -f /etc/sysctl.d/97-restify-sin-ipv6.conf ] && ipv6_nuevo=0 || ipv6_nuevo=1
printf 'net.ipv6.conf.all.disable_ipv6 = 1\nnet.ipv6.conf.default.disable_ipv6 = 1\n' > /etc/sysctl.d/97-restify-sin-ipv6.conf
sysctl -q -p /etc/sysctl.d/97-restify-sin-ipv6.conf
echo "[ok] IPv6 desactivado (solo IPv4)"

# ---------------------------------------------------------------- 4) Docker
# default-address-pools: por defecto Docker solo alcanza para ~30 redes en total y cada cliente usa 2.
# Con esta reserva caben miles (10.64.0.0/12 en bloques /24). Las redes ya existentes no cambian.
codigo=0
python3 - <<'EOF' || codigo=$?
import json, os, shutil, sys
ruta = os.environ.get("DAEMON_JSON", "/etc/docker/daemon.json")
actual = {}
if os.path.exists(ruta):
    with open(ruta) as f:
        actual = json.load(f)
deseado = {
    "log-driver": "json-file",
    "log-opts": {"max-size": "10m", "max-file": "3"},
    "default-address-pools": [{"base": "10.64.0.0/12", "size": 24}],
    "live-restore": True,
}
nuevo = {**actual, **deseado}
if nuevo == actual:
    print("[ok] docker: daemon.json ya estaba al día")
    sys.exit(10)
if os.path.exists(ruta):
    shutil.copy(ruta, ruta + ".bak")
with open(ruta, "w") as f:
    json.dump(nuevo, f, indent=2)
    f.write("\n")
print("[ok] docker: daemon.json actualizado (copia en daemon.json.bak)")
EOF
if [ "$codigo" -eq 0 ]; then
  echo "Reiniciando Docker: los contenedores se detienen unos segundos y arrancan solos..."
  systemctl restart docker
  sleep 5
  docker ps --format 'table {{.Names}}\t{{.Status}}' | head -20
elif [ "$codigo" -eq 10 ] && [ "$ipv6_nuevo" -eq 1 ]; then
  echo "IPv6 recién desactivado: reiniciando Docker para que lo note (live-restore mantiene los contenedores)..."
  systemctl restart docker
  sleep 5
  docker ps --format 'table {{.Names}}\t{{.Status}}' | head -20
elif [ "$codigo" -ne 10 ]; then
  echo "ERROR: no se pudo actualizar /etc/docker/daemon.json (¿JSON inválido?). Docker no se tocó."
  exit 1
fi
echo
echo "Listo. Ahora, en OTRA terminal, comprueba que sigues entrando:  ssh root@IP"
