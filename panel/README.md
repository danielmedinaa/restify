# RESTIFY · Panel de administración

Panel interno para gestionar clientes, planes, suscripciones e instancias de RESTIFY. Flask + SQLAlchemy + Postgres (migraciones con Alembic),
sin build ni CDNs (igual que la landing). **Por ahora solo localhost**; la infraestructura está lista pero
simulada hasta que haya VPS.

## Correr en local (Docker + Postgres)

```bash
docker network create restify-net      # una sola vez: red compartida con el backend de Restify
cp .env.example .env                   # cambia POSTGRES_PASSWORD, SECRET_KEY y CLAVE_CIFRADO (SECRET_KEY y CLAVE_CIFRADO distintas)
docker compose up -d --build           # Postgres + panel; aplica las migraciones y siembra roles/planes solo
docker compose exec web flask --app wsgi crear-superadmin     # pide correo, nombre y contraseña por consola
```

Abre **http://localhost:8030**. En el primer ingreso configuras el 2FA (obligatorio) y recibes 8 códigos de recuperación.

- Pruebas (SQLite en memoria): `docker compose --profile test run --rm --build tests`
- Pruebas contra Postgres: `TEST_DATABASE_URL=postgresql+psycopg://... pytest -q`
- Migraciones tras cambiar un modelo: `docker compose exec web flask --app wsgi db migrate -m "descripcion"` (queda en `migrations/`; copia el archivo generado al host o corre el comando con `-v "$PWD:/app"`) y `... db upgrade`. El contenedor aplica `db upgrade` en cada arranque.
- Respaldo: `docker compose exec db pg_dump -U panel panel > panel.sql`

## Conectar el backend de Restify (probar el flujo completo)

1. En el panel: **Clientes → Nuevo cliente → Nueva suscripción e instancia**. Al crearla se muestra el token **una sola vez**.
2. En `backend/.env` solo va la URL del panel (y, opcional, el subdominio para que no sirva el token de otro cliente):
   ```
   PANEL_URL=http://panel:8000/api/v1/estado
   INSTANCIA_SUBDOMINIO=el-subdominio-que-creaste
   ```
   `cd backend && docker compose up -d api`
3. Abre el front de esa instancia **sin usuarios todavía**: te lleva solo a **Configuración inicial** (`/configurar`):
   token → administrador → primer local → moneda y zona horaria → revisar. Al terminar crea todo en una transacción y entra al sistema.

El token que el cliente escribe queda guardado **cifrado** en la base de la instancia (no en el `.env`) y no se puede ver ni editar
desde Administración. Mientras la instancia no tenga usuarios cualquiera que abra la URL ve el asistente, pero sin un token válido
(validado contra este panel y, si defines `INSTANCIA_SUBDOMINIO`, de esa instancia) no puede crear nada; en cuanto existe un
usuario el asistente se cierra para siempre. Sin `PANEL_URL` (desarrollo) el asistente no pide token.

Instancias que ya tenían `PANEL_TOKEN` en el `.env` siguen funcionando (el `.env` manda sobre el guardado).

Desde ahí el backend consulta el panel (caché de 30 s): si pausas, suspendes o cancelas la suscripción, todo el sistema
responde `402` con un mensaje que el front muestra; si llegas al máximo de **sucursales, salas (zonas), mesas, productos
o usuarios** de tu plan, crear uno más responde `402` «Tu plan permite hasta N…». Cambiar el plan o los límites en el panel
aplica en ≤ 30 s, sin reiniciar nada. Si el panel no responde, el backend sigue con el último estado conocido (y si nunca
lo conoció, deja operar). Sin `PANEL_URL`/`PANEL_TOKEN` no hay restricciones.

Los límites se validan al **crear**; reactivar algo desactivado no los revisa todavía.

## Qué hace

| Sección | Detalle |
|---|---|
| Clientes | Datos comerciales, búsqueda por nombre, RIF, correo o dominio. |
| Planes | Precio y límites: **sucursales, salas, mesas, productos y usuarios** (vacío = ilimitado). Editar un plan aplica de inmediato a todas sus suscripciones. Se archivan, no se borran. |
| Suscripciones | Estados **activa · pausada · suspendida · cancelada**, cambio de plan, **límites a la medida** por cliente (pisan al plan), vencimiento y motivo. |
| Instancias | `<cliente>.restify.com.ve` (en local `.restify.localhost`), **dominio propio** con verificación DNS (TXT), token por instancia (rotable) y eliminación. |
| Administradores y roles | Matriz `módulo × {crear, leer, editar, eliminar}` como en Restify. Roles base: Superadmin, Soporte, Solo lectura. |
| Auditoría | Bitácora encadenada por hash; el botón «Verificar integridad» detecta si alguien editó o borró eventos. |

### Qué significa cada estado

- **Activa**: opera normal.
- **Pausada**: la pide el cliente; instancia detenida, datos intactos, se reanuda cuando quiera.
- **Suspendida**: por impago o abuso (pide motivo); acceso bloqueado, datos intactos.
- **Cancelada**: baja (pide motivo y tu contraseña). Es final; después puedes **eliminar la instancia** (exige escribir el subdominio y tu contraseña) y el subdominio queda libre.

## Seguridad

- **Login:** argon2id, mínimo 12 caracteres con mayúsculas/minúsculas/números, mensaje genérico (no revela qué correos existen), bloqueo de cuenta 15 min tras 5 fallos y límite por IP.
- **2FA obligatorio (TOTP):** secreto cifrado en la base (Fernet), un código no se puede reutilizar, códigos de recuperación de un solo uso (solo se guarda su hash).
- **Sesión:** cookie `HttpOnly` + `SameSite=Strict` (+ `Secure` y prefijo `__Host-` en producción), caduca a los 20 min sin actividad y a las 8 h en total. Cambiar contraseña, rol o desactivar a alguien cierra sus sesiones al instante.
- **CSRF** en todo POST; **CSP estricta** (sin scripts ni estilos en línea), `no-store`, `noindex`, HSTS en producción.
- **Permisos** por módulo y acción en cada ruta. Nadie otorga permisos que no tiene ni edita su propio rol.
- **Acciones destructivas** (cancelar, eliminar, rotar token, reiniciar 2FA) piden de nuevo la contraseña.
- **Dominio propio:** no se activa hasta demostrar propiedad con un TXT `_restify.<dominio>`; no se pueden reclamar dominios de RESTIFY ni reservados (`www`, `panel`, `api`…).
- **Instancias:** token propio de 40 bytes aleatorios (solo se guarda el hash, se muestra una vez). Los contenedores generados corren sin privilegios, con red interna para la base y sin capacidades.
- **Contenedor del panel:** usuario sin privilegios; en el compose solo escucha en `127.0.0.1`.

## Para las instancias de Restify (API)

Cada instancia consulta su estado con su token:

```
GET /api/v1/estado        Authorization: Bearer rst_...
→ {"estado":"activa","acceso":true,"motivo":null,"plan":"Pro","vence_en":"…",
   "limites":{"max_sucursales":3,"max_salas":4,"max_mesas":60,"max_productos":500,"max_usuarios":20}}
```

`null` en un límite = ilimitado. `acceso` es falso si la suscripción no está activa o venció hace más de 3 días.

> **Pendiente en el backend de Restify** (aún no se tocó): consultar esta API (con caché de ~30 s) para bloquear el
> acceso cuando `acceso=false` y devolver 403 al crear sucursales/salas/mesas/productos/usuarios por encima de los límites.

## Infra (cuando compres el VPS)

`app/infra/aprovisionador.py` define la interfaz (`crear`, `detener`, `reanudar`, `eliminar`, `actualizar_dominio`).
Hoy `APROVISIONADOR=simulado` escribe en `data/instancias/<subdominio>/` el `.env` (secretos aleatorios, modo 600),
el `docker-compose.yml` y el bloque de Caddy de cada instancia, sin ejecutar nada. Falta:

1. Un `AprovisionadorDocker` que ejecute `docker compose up/stop/down` por instancia y recargue Caddy.
2. DNS comodín `*.restify.com.ve` hacia el VPS y Caddy con TLS automático (por dominio propio, TLS bajo demanda).
3. Tareas programadas: suspender automático al vencer y respaldos de Postgres por instancia.
4. Poner el panel detrás de VPN/lista de IPs o Cloudflare Access, además del 2FA.
