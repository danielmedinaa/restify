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

**Ya incluido en el código**
- **Límites por IP en Caddy** (responde 429 con `Retry-After`): 600 peticiones/min en general, 20/min en logins
  (`/login`, `/login/2fa`, `/bff/auth/login`) y 5/min en el formulario de contacto. Se ajustan en `deploy/proxy/Caddyfile`
  (`(limites)`). Un local con varios empleados detrás de una misma IP comparte el cupo: súbelo si hace falta.
- Cabeceras HSTS, `nosniff` y `Referrer-Policy` en todo; se oculta la cabecera `Server`.
- Logs de Docker con tope (10 MB × 3 por contenedor) en los compose y en cada cliente; `daemon.json` en servidores nuevos.
- Dependabot semanal (`.github/dependabot.yml`), con los PR hacia `develop`.
- Además de lo anterior, las apps ya traen: bloqueo por intentos fallidos, 2FA en el panel, CSP estricta y cookies seguras.

**Para aplicar lo nuevo en un servidor que ya existe** (el Caddy se reconstruye con el plugin de límites):
```bash
./deploy/subir.sh dev restify@IP
ssh root@IP '/srv/restify/dev/app/deploy/desplegar.sh dev --proxy'
```
Los logs con tope de las instancias de clientes ya creadas se aplican cuando se actualizan de versión.

**Para hacer tú**
1. **SSH sin contraseña** (solo después de comprobar que entras con tu llave, o te quedas fuera):
   ```bash
   ssh root@IP "sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && sshd -t && systemctl reload ssh"
   ```
   Antes de cerrar tu sesión, abre OTRA terminal y comprueba que sigues pudiendo entrar. En Ubuntu 24.04 revisa también
   `/etc/ssh/sshd_config.d/*.conf`: algunos archivos de ahí pueden volver a activar `PasswordAuthentication yes`.
2. **GitHub → Settings → Branches**: regla para `main` (y `develop`): exigir pull request y que pasen los tests.
3. **GitHub → Settings → Code security**: activa Dependabot alerts, Secret scanning y Push protection.
4. **Respaldos fuera del servidor**: copia `/srv/restify/pro/respaldos` a otro lugar (tu PC o almacenamiento externo).
5. **Pendiente grande**: aislar las instancias entre sí (hoy comparten la red del ambiente). Hacerlo antes de tener clientes reales.

## Cosas a vigilar
- **Primer certificado**: tarda 1-2 min. Logs: `docker compose -f /srv/restify/proxy/docker-compose.yml logs caddy`.
- **No borres el volumen `caddy_data`**: Let's Encrypt limita las emisiones.
- **Respaldos** (solo pro, diarios 04:00, 7 copias) quedan en `/srv/restify/pro/respaldos`, en el mismo servidor: cópialos fuera.
- **Banner**: dev y pre muestran una barra fija abajo en landing, panel y en el sistema de cada cliente creado allí. En pro no aparece.
- **Memoria**: cada ambiente usa ~0.9 GB (panel, su base y landing) más ~1 GB por cliente de prueba.
- **La llave de CI** entra como `restify`, que solo puede ejecutar el `desplegar.sh` de cada ambiente con sudo. Aun así `restify` pertenece al grupo docker (equivale a root): protege esa llave.
- **Dominios propios de clientes**: aún no funcionan en modo agente (pendiente, ver `panel/README.md`).
- **Cambiar de dominio** obliga a recrear las instancias (sus URLs y CORS quedan fijas al crearlas).
- Esto está probado por partes (tests, sintaxis, Caddyfile, compose), pero **no se ha corrido en un servidor real**: espera ajustes en el primer despliegue.
