# ARRANQUE · Cómo prender todo RESTIFY en tu local

Todos los comandos se corren desde la carpeta raíz:

```bash
cd ~/Documentos/dev/danielmedina/restify
```

## Qué es cada cosa y en qué puerto vive

| Pieza | Para qué | Dónde se abre |
|---|---|---|
| **Backend** (tu RESTIFY de desarrollo) | La API + su base de datos | http://localhost:8010 |
| **Front** (tu RESTIFY de desarrollo) | La app que ve el restaurante | http://localhost:3001 |
| **Landing** | La página de venta | http://localhost:8020 |
| **Panel** | Tu consola para crear y controlar clientes | http://localhost:8030 |
| **Proxy** (Caddy) | Abre los sistemas de los clientes | `http://<cliente>.restify.localhost:8088` |
| **Agente** | El que crea/apaga de verdad los sistemas de los clientes | (corre en una terminal) |

> El puerto 8080 lo ocupa tu pgadmin, por eso el proxy usa el **8088**.

---

## A) UNA SOLA VEZ (si es la primera vez en esta máquina)

```bash
# 1. Red compartida entre el panel, el backend y los clientes
#    (si ya existe te lo dice y no pasa nada)
docker network create restify-net

# 2. Construir las imágenes que usan los sistemas de los clientes (tarda 1-5 min)
./infra/construir_imagenes.sh

# 3. Crear tu usuario del panel (te pide correo, nombre y contraseña)
#    Primero hay que prender el panel (paso 4 de la sección B), luego:
cd panel && docker compose exec web flask --app wsgi crear-superadmin && cd ..
```
La contraseña: 12+ caracteres con mayúsculas, minúsculas y números. La primera vez que entres
al panel te pide configurar el 2FA (guarda los 8 códigos de recuperación).

---

## B) CADA VEZ QUE QUIERAS TRABAJAR

### 1. Tu RESTIFY de desarrollo (backend)
```bash
cd backend && docker compose up -d && cd ..
```
Comprobar: `curl localhost:8010/health` → `{"status":"ok"}`

### 2. Tu RESTIFY de desarrollo (front)
En **otra terminal** (déjala abierta):
```bash
cd front && PORT=3001 npm run dev
```
Abre http://localhost:3001

> ⚠️ **Nunca borres la carpeta `front/.next`** mientras esto corre: se rompe el servidor de desarrollo.

### 3. La landing (opcional)
```bash
cd landing && docker compose up -d && cd ..
```

### 4. El panel
```bash
cd panel && docker compose up -d && cd ..
```
Abre http://localhost:8030

### 5. El proxy (para abrir los sistemas de los clientes)
```bash
cd infra/proxy && docker compose up -d && cd ../..
```

### 6. El agente (en **otra terminal**, déjala abierta)
```bash
./infra/iniciar.sh
```
Debe decir: `[agente] escuchando en ...agente.sock`.
Si no está encendido, el panel NO puede crear sistemas de clientes (te mostrará "error" y un botón de reintentar).

---

## C) PARA CREAR UN CLIENTE DE PRUEBA

1. Panel (http://localhost:8030) → **Clientes → Nuevo cliente**.
2. En el cliente → **Nueva suscripción e instancia** → elige plan y subdominio (ej. `resto1`).
3. Copia el **token** `rst_...` (se ve una sola vez).
4. Espera ~30 s y abre `http://resto1.restify.localhost:8088`.
5. Pega el token en **Configuración inicial** y sigue los pasos.

---

## D) COMPROBAR QUE TODO ESTÁ VIVO

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'      # contenedores
curl -s localhost:8010/health                            # backend
curl -s -o /dev/null -w "panel %{http_code}\n" localhost:8030/login
curl -s -o /dev/null -w "proxy %{http_code}\n" -H "Host: x.restify.localhost:8088" localhost:8088/   # 503 = proxy vivo
```

---

## E) APAGAR TODO

```bash
# Terminales del front y del agente: Ctrl+C

cd infra/proxy && docker compose down && cd ../..
cd panel        && docker compose down && cd ..      # (añade -v para borrar la base del panel)
cd landing      && docker compose down && cd ..
cd backend      && docker compose down && cd ..      # NO uses -v: borra tu base de desarrollo
```

Los sistemas de clientes (`restify-<cliente>-*`) siguen encendidos hasta que los **pauses o elimines desde el panel**.
Para borrarlos desde el panel: cuenta → **Cancelar** → **Eliminar instancia**.

### Borrar TODOS los sistemas de clientes de golpe (solo pruebas)
```bash
for d in ~/.restify-instancias/*/; do
  s=$(basename "$d"); docker compose -p "restify-$s" -f "$d/docker-compose.yml" down -v
done
rm -rf ~/.restify-instancias
```
(Después, en el panel, esas suscripciones quedan huérfanas: elimínalas o resetea la base del panel con `docker compose down -v`.)

---

## F) SI ALGO FALLA

| Síntoma | Qué hacer |
|---|---|
| El panel dice "error" al crear un cliente | ¿Agente encendido? → `./infra/iniciar.sh`, y botón **Reintentar crear la instancia**. |
| `resto1.restify.localhost:8088` no abre | ¿Proxy encendido? (paso B5). ¿La cuenta está pausada? |
| "Servicio no disponible" | Cuenta pausada, o aún creándose. |
| "Cuenta suspendida" | Es lo esperado si la suspendiste desde el panel. |
| `network restify-net not found` | Corre `docker network create restify-net`. |
| "port is already allocated" | Otro programa usa ese puerto (`ss -ltn \| grep :PUERTO`). |
| Cambié código del backend/front de clientes | Repite `./infra/construir_imagenes.sh` (los clientes **nuevos** usan la imagen nueva). |
| Logs de un cliente | `docker logs restify-resto1-api-1` · `docker logs restify-resto1-front-1` |

## G) PRUEBAS AUTOMÁTICAS (opcional)

```bash
cd backend && docker compose --profile test run --rm --build tests      # backend (~1 min)
cd panel   && docker compose --profile test run --rm --build tests      # panel
```

---

📘 Manuales: `infra/docs/manuales/manual-panel.md` (tú) y `infra/docs/manuales/manual-restify-app.md` (restaurantes) ·
📗 Detalle del agente: `infra/README.md` · 📙 Panel: `panel/README.md`
