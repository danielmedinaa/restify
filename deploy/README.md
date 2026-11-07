# Despliegue: un VPS, tres ambientes, GitHub Actions

```
Internet ─▶ Caddy :443 (uno solo, HTTPS con certificados comodín por Cloudflare)
   pro  turestify.com            landing · panel.turestify.com      · <cliente>.turestify.com
   pre  pre.turestify.com        landing · panel.pre.turestify.com  · <cliente>.pre.turestify.com   (banner PRE PRODUCCION)
   dev  dev.turestify.com        landing · panel.dev.turestify.com  · <cliente>.dev.turestify.com   (banner DESARROLLO)
```
Cada ambiente tiene su carpeta (`/srv/restify/<env>`), su red de Docker, su panel con su base de datos y su propio agente
(`restify-agente@<env>`). Los clientes reales solo existen en **pro**; en dev y pre crea un cliente de prueba.

| Rama / etiqueta | Ambiente | Cuándo |
|---|---|---|
| `develop` | dev | automático al hacer push |
| `main` | pre | automático al hacer push |
| etiqueta `v1.0.0` | pro | espera tu aprobación en GitHub |

Flujo: tests (panel, landing, infra, backend, front) → imágenes de api y front a `ghcr.io/danielmedinaa/` → subir código → `desplegar.sh`.
Las instancias de los clientes se actualizan una por una: respaldo, cambio de versión y vuelta atrás automática si no arranca.

## 1. DNS (Cloudflare, el dominio con sus nameservers)
Todos en **"Solo DNS" (nube gris)**, apuntando a la IP del VPS:

| Tipo | Nombre |
|---|---|
| A | `@` y `*` (pro) |
| A | `pre` y `*.pre` |
| A | `dev` y `*.dev` |

(`*.turestify.com` no cubre `x.pre.turestify.com`: por eso los comodines de pre y dev van aparte.)
Token de API: Mi perfil → Tokens de API → plantilla "Editar DNS de zona", solo para tu dominio.

## 2. Preparar el servidor (una vez)
```bash
ssh root@IP 'bash -s' < deploy/servidor-inicial.sh
```
Instala Docker, crea el usuario `restify`, las carpetas y redes de los 3 ambientes, swap, firewall (22/80/443) y fail2ban.
Luego, en el servidor, crea la configuración común (nunca va al repositorio):
```bash
ssh root@IP
cp /dev/null /srv/restify/config.env && chmod 600 /srv/restify/config.env
nano /srv/restify/config.env      # copia el contenido de deploy/config.env.example y complétalo
```

## 3. Llave de despliegue para GitHub Actions
En tu PC: `ssh-keygen -t ed25519 -f ~/.ssh/restify_deploy -N "" -C github-actions`
Agrega `~/.ssh/restify_deploy.pub` a `/home/restify/.ssh/authorized_keys` del servidor.
Obtén la huella del servidor: `ssh-keyscan -t ed25519 IP`

## 4. GitHub (repo `danielmedinaa/restify`, privado)
1. Ramas `main` y `develop`. Protege `main`: pull request obligatorio y que pasen los tests.
2. Settings → Environments: crea **dev**, **pre** y **pro**. En **pro** activa "Required reviewers" (tú) y limita las etiquetas a `v*`.
3. Settings → Secrets and variables → Actions → **Repository secrets**:
   - `VPS_HOST`: la IP del servidor
   - `VPS_SSH_KEY`: el contenido de `~/.ssh/restify_deploy` (la privada)
   - `VPS_KNOWN_HOSTS`: la línea que dio `ssh-keyscan`
4. Settings → Actions → General → Workflow permissions: "Read repository contents and packages".
5. Los paquetes (imágenes) quedan privados en ghcr.io; el workflow usa el `GITHUB_TOKEN`, no hace falta crear otro token.

## 5. Primer despliegue
```bash
git push origin develop        # → dev
git push origin main           # → pre
git tag v1.0.0 && git push origin v1.0.0     # → pro (aprueba en GitHub)
```
En cada ambiente nuevo, crea tu usuario del panel (el workflow imprime el comando al final):
```bash
docker compose -p restify-dev -f /srv/restify/dev/app/deploy/docker-compose.yml --env-file /srv/restify/dev/app/deploy/.env exec panel flask --app wsgi crear-superadmin
```
Entra a `https://panel.dev.turestify.com`, configura el 2FA y crea un cliente de prueba.

## A mano (sin Actions)
```bash
./deploy/subir.sh dev restify@IP
ssh root@IP '/srv/restify/dev/app/deploy/desplegar.sh dev'     # sin imágenes: las construye en el servidor
```

## Seguridad

**Aislamiento entre clientes.** Cada cliente tiene su **propia red** (`restify-<ambiente>-<cliente>-edge`) y su red interna
sin salida (base y Redis). A la red de un cliente solo se unen el proxy (Caddy) y el panel (lo hace el agente con
`docker network connect`); ningún cliente puede alcanzar a otro ni al panel de forma directa. Si el panel o el proxy se
recrean, `desplegar.sh` los reconecta solo (`agente.py reconectar`).

**Ya incluido en el código**
- Límites por IP en Caddy (429 con `Retry-After`): 600 peticiones/min en general, 20/min en logins
  (`/login`, `/login/2fa`, `/bff/auth/login`) y 5/min en el formulario de contacto (`deploy/proxy/Caddyfile`, `(limites)`).
- Cabeceras HSTS, `nosniff` y `Referrer-Policy`; se oculta `Server`.
- Logs de Docker con tope (10 MB × 3) y live-restore.
- **Panel restringible por IP**: `PANEL_IPS_PERMITIDAS` en `/srv/restify/config.env` (vacío = abierto). Con IP dinámica
  puedes quedarte fuera: úsalo solo con IP fija o por VPN.
- **Vigilancia** cada 5 min (`restify-vigilar`): disco >85 %, memoria <10 %, contenedores caídos o "unhealthy", páginas que no
  responden y certificados a menos de 14 días. Avisa solo cuando algo cambia. Para Telegram define `TELEGRAM_BOT_TOKEN` y
  `TELEGRAM_CHAT_ID` en `config.env`; sin ellos queda en el log (`journalctl -u restify-vigilar`).
- Dependabot semanal (`.github/dependabot.yml`), con los PR hacia `develop`.
- Las apps ya traen: bloqueo por intentos fallidos, 2FA en el panel, CSP estricta y cookies seguras.

**Cómo aplicarlo en un servidor que ya existe — en este orden**
1. **Endurecer el servidor** (SSH solo con llave, fail2ban, red del sistema y redes de Docker para muchos clientes):
   ```bash
   ssh root@IP 'bash -s' < deploy/endurecer-servidor.sh
   ```
   ⚠️ Mantén tu sesión abierta y, en OTRA terminal, comprueba que sigues entrando con llave. La primera vez reinicia Docker
   (unos segundos sin servicio; los contenedores vuelven solos).
2. **Desplegar el código nuevo**: push a `develop` (dev), luego `main` (pre) y, al final, etiqueta (pro). En cada ambiente
   el despliegue migra a los clientes existentes a su red propia al actualizar su versión.
3. **Comprobar el aislamiento** en un ambiente con dos clientes de prueba:
   ```bash
   # Desde la API de un cliente NO debe verse el del otro (debe fallar con "Name or service not known")
   docker exec restify-dev-<clienteA>-api-1 python -c "import socket; socket.gethostbyname('restify-dev-<clienteB>-api-1')"
   # ...y sí debe ver al panel
   docker exec restify-dev-<clienteA>-api-1 python -c "import urllib.request; print(urllib.request.urlopen('http://panel:8000/salud').status)"
   ```

**Pendiente (te toca a ti)**
- **GitHub → Settings → Branches**: regla para `main` y `develop` que exija PR y tests en verde.
- **GitHub → Settings → Code security**: Dependabot alerts, Secret scanning y Push protection.
- **Respaldos fuera del servidor** (S3): quedan para más adelante. Hasta entonces los respaldos solo viven en el VPS.
- Restar riesgo del agente: tiene acceso a Docker (equivale a root en el servidor). Está acotado a 4 acciones firmadas,
  pero protege `/srv/restify/*/agente.env` y la llave de CI.

## Landing: modo "Próximamente"

Mientras preparas el lanzamiento, la landing de **todos** los ambientes muestra una página de espera ("Estamos preparando
*algo* para ti") con botones de WhatsApp e Instagram; el formulario de demo queda bloqueado y el sitio no se indexa.
Es el comportamiento por defecto de `desplegar.sh`.

Para **abrir la landing**: en `/srv/restify/config.env` del servidor pon `LANDING_MODO=abierta` y vuelve a desplegar
(un push). Para volver a cerrarla, `LANDING_MODO=proximamente`. Los datos de contacto (`WHATSAPP_NUMERO`,
`CONTACTO_EMAIL`, `INSTAGRAM`) también se sincronizan desde ese archivo en cada despliegue.

## Cosas a vigilar
- **Primer certificado**: tarda 1-2 min. Logs: `docker compose -f /srv/restify/proxy/docker-compose.yml logs caddy`.
- **No borres el volumen `caddy_data`**: Let's Encrypt limita las emisiones.
- **Respaldos** (solo pro, diarios 04:00, 7 copias) quedan en `/srv/restify/pro/respaldos`, **en el mismo servidor**: súbelos a S3 más adelante.
- **Banner**: dev y pre muestran una barra fija abajo en landing, panel y en el sistema de cada cliente creado allí. En pro no aparece.
- **Memoria**: cada ambiente usa ~0.9 GB (panel, su base y landing) más ~1 GB por cliente de prueba.
- **La llave de CI** entra como `restify`, que solo puede ejecutar el `desplegar.sh` de cada ambiente con sudo. Aun así `restify` pertenece al grupo docker (equivale a root): protege esa llave.
- **Dominios propios de clientes**: aún no funcionan en modo agente (pendiente, ver `panel/README.md`).
- **Cambiar de dominio** obliga a recrear las instancias (sus URLs y CORS quedan fijas al crearlas).
- Esto está probado por partes (tests, sintaxis, Caddyfile, compose), pero **no se ha corrido en un servidor real**: espera ajustes en el primer despliegue.
