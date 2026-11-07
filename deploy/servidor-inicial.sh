#!/usr/bin/env bash
# Prepara un VPS NUEVO (Ubuntu 24.04). Se corre UNA vez, como root, en el servidor:
#   ssh root@IP 'bash -s' < deploy/servidor-inicial.sh
# Instala Docker, crea el usuario "restify" y las carpetas de dev/pre/pro, swap, firewall y fail2ban.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Corre esto como root"; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl rsync ufw fail2ban unattended-upgrades python3 openssl sudo

# Docker (script oficial de Docker)
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

# Usuario sin contraseña que es dueño del código y corre los agentes. Se entra con tu misma llave SSH.
id restify >/dev/null 2>&1 || useradd --create-home --shell /bin/bash restify
usermod -aG docker restify
for e in dev pre pro; do
  install -d -o restify -g restify -m 755 "/srv/restify/$e" "/srv/restify/$e/app"
done
if [ -f /root/.ssh/authorized_keys ]; then
  install -d -o restify -g restify -m 700 /home/restify/.ssh
  install -o restify -g restify -m 600 /root/.ssh/authorized_keys /home/restify/.ssh/authorized_keys
fi

# GitHub Actions entra como "restify" y solo puede ejecutar el script de despliegue de cada ambiente como root.
# (Ojo: quien pertenece al grupo docker ya equivale a root; esto solo evita dar una shell root a la llave de CI.)
cat > /etc/sudoers.d/restify <<'EOF'
restify ALL=(root) NOPASSWD: /srv/restify/dev/app/deploy/desplegar.sh, /srv/restify/pre/app/deploy/desplegar.sh, /srv/restify/pro/app/deploy/desplegar.sh
EOF
chmod 440 /etc/sudoers.d/restify
visudo -cf /etc/sudoers.d/restify

# Una red por ambiente: dev, pre y pro no se ven entre sí
for e in dev pre pro; do docker network inspect "restify-$e-net" >/dev/null 2>&1 || docker network create "restify-$e-net"; done

# Swap de 2 GB: evita que el servidor se quede sin memoria al compilar o en picos de uso
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo 'vm.swappiness=10' > /etc/sysctl.d/99-restify.conf
  sysctl -p /etc/sysctl.d/99-restify.conf
fi

# Firewall: solo SSH, HTTP y HTTPS (los puertos de las bases de datos, paneles, etc. nunca se publican)
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

systemctl enable --now fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades || true

cat <<'EOF'

Servidor listo. Siguiente (ver deploy/README.md):
  1) Crea /srv/restify/config.env  (copia deploy/config.env.example y complétalo)
  2) Endurece el servidor:  ssh root@IP 'bash -s' < deploy/endurecer-servidor.sh
  3) El primer despliegue de cada ambiente lo hace GitHub Actions (o a mano: deploy/subir.sh + desplegar.sh)
EOF
