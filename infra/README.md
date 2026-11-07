# Agente de instancias

Crea de verdad una instancia de RESTIFY por cliente (4 contenedores: base de datos, redis, API y front) cuando
la pides desde el panel. Corre **en tu máquina, fuera del panel**: el panel nunca toca Docker, solo le pide al
agente cuatro cosas fijas (crear, detener, reanudar, eliminar) por un socket Unix firmado con HMAC.

```
 panel (contenedor) ──socket firmado──▶ agente (proceso tuyo) ──▶ docker compose ──▶ restify-<cliente>-{db,redis,api,front}
 navegador ─▶ Caddy :8088 ─▶  <cliente>.restify.localhost ─▶ front / websocket de esa instancia
```

## Arrancar (laptop)

```bash
cd ~/Documentos/dev/danielmedina/restify
docker network create restify-net            # una vez (si ya existe, ignora el aviso)
./infra/construir_imagenes.sh               # una vez, y cuando cambies el código (~1-5 min)
(cd infra/proxy && docker compose up -d)    # Caddy en http://<cliente>.restify.localhost:8088
(cd panel && docker compose up -d --build)   # el panel (usa APROVISIONADOR=agente de su .env)
./infra/iniciar.sh                          # déjalo corriendo en una terminal (Ctrl+C lo detiene)
```

Luego en el panel (http://localhost:8030): Clientes → Nuevo → «Nueva suscripción e instancia». En ~20-40 s
la instancia queda «en línea» y aparece el token. Abre `http://<subdominio>.restify.localhost:8088`: te lleva al
asistente de **Configuración inicial** y ahí pegas el token.

Si el agente estaba apagado, la instancia queda en «error»: enciende el agente y pulsa **Reintentar crear la
instancia** en la suscripción (es seguro repetirlo: no cambia los secretos).

## Qué hace cada acción del panel

| En el panel | En Docker |
|---|---|
| Crear suscripción | Genera secretos únicos, levanta db+redis+api, crea las 2 API keys del front y levanta el front |
| Pausar | `stop` (el sistema muestra «Servicio no disponible») |
| Suspender | Sigue encendida: el sistema responde «Cuenta suspendida» con el motivo |
| Reanudar / Activar | `start` y espera a que la API responda |
| Cancelar → Eliminar instancia | `down -v`: borra contenedores **y datos**, y la carpeta de la instancia |

Cada instancia usa como máximo ~960 MB (db 256, api 384, front 256, redis 64) y la base/redis están en una red
interna sin salida a internet. Las instancias comparten la red `restify-net` con el proxy y el panel, así que en
el laptop se ven entre sí (en el VPS se aíslan con una red por instancia + proxy).

## Limpiar todo cuando termines

```bash
# 1. Desde el panel: cancela y elimina cada instancia (o a mano:)
docker ps -a --format '{{.Names}}' | grep '^restify-[a-z0-9-]*-\(db\|redis\|api\|front\)-1$'
docker compose -p restify-<subdominio> -f ~/.restify-instancias/<subdominio>/docker-compose.yml down -v
rm -rf ~/.restify-instancias
# 2. Apaga el proxy y el panel
(cd infra/proxy && docker compose down); (cd panel && docker compose down)       # -v borra la base del panel
```

## Seguridad

- Sin dependencias (solo biblioteca estándar de Python); escucha **solo** en `panel/run/agente.sock`, nunca en red.
- Cada petición lleva firma HMAC-SHA256 con marca de tiempo (60 s). El secreto es `AGENTE_SECRETO` de `panel/.env`.
- Valida el subdominio (3-32 caracteres `a-z0-9-`, sin reservados), el dominio, el puerto y la URL del panel antes de actuar.
- Ejecuta `docker` con lista de argumentos fija, sin shell; los secretos de cada instancia quedan en archivos `600`.
- Contenedores sin capacidades extra (`cap_drop: ALL`) y `no-new-privileges`.
- Pruebas: `cd infra && pytest -q` (con Docker simulado).

## Para el VPS

El mismo agente corre como servicio de systemd; el proxy pasa a Caddy con TLS (certificado comodín
`*.restify.com.ve` vía DNS) y los dominios propios se agregan con TLS bajo demanda. `actualizar_dominio` del
panel aún no hace nada en modo agente.
