# Manual del PANEL de RESTIFY

**Para quién es:** para ti, el dueño de RESTIFY. El panel es tu "oficina": desde aquí das de alta a tus clientes,
les creas su sistema, cobras (a mano), y los pausas o suspendes si hace falta.

> Piensa así: **cada cliente tiene su propio RESTIFY** (su propio sistema, con sus datos aparte).
> El panel es el lugar donde tú creas y controlas todos esos sistemas.

---

## 1. Cómo se prende y se apaga (en tu laptop)

Necesitas 3 cosas encendidas. Todo desde la carpeta `restify`:

| Qué | Comando | Dónde queda |
|---|---|---|
| El panel | `cd panel && docker compose up -d` | http://localhost:8030 |
| El proxy (para abrir los sistemas de los clientes) | `cd infra/proxy && docker compose up -d` | puerto 8088 |
| El agente (el que crea los sistemas) | `./infra/iniciar.sh` | **déjalo abierto en una terminal** |

La primera vez, antes de todo, corre una sola vez:
```
docker network create restify-net
./infra/construir_imagenes.sh
```

**Para apagar:** `Ctrl+C` en el agente, y `docker compose down` dentro de `panel` y de `infra/proxy`.
Los sistemas de los clientes siguen vivos hasta que los pauses o elimines desde el panel (o apagues Docker).

---

## 2. Entrar al panel por primera vez

1. Crea tu usuario (una sola vez): `cd panel && docker compose exec web flask --app wsgi crear-superadmin`
   - Te pide correo, nombre y contraseña. La contraseña: **12 o más caracteres, con mayúsculas, minúsculas y números**.
2. Abre **http://localhost:8030** y entra con ese correo y contraseña.
3. Te pide configurar el **2FA** (es obligatorio):
   - Baja una app como *Google Authenticator*, *Aegis* o *1Password*.
   - Escanea el cuadro QR y escribe el código de 6 números que te muestra.
4. Te da **8 códigos de recuperación**. **Guárdalos** (por ejemplo en tu gestor de contraseñas). Cada uno sirve
   una sola vez si pierdes tu celular. No se vuelven a mostrar.

**Cada vez que entres:** correo + contraseña, y luego el código de la app. Si estás 20 minutos sin tocar nada,
te saca solo (por seguridad).

---

## 3. Qué hay en el menú de la izquierda

| Sección | Para qué sirve |
|---|---|
| **Resumen** | Una mirada rápida: cuántos clientes, cuántas cuentas activas/pausadas/suspendidas, cuánto ingresas al mes y qué vence esta semana. |
| **Clientes** | Tus clientes (los restaurantes). Aquí los creas y les armas su sistema. |
| **Suscripciones** | La lista de todos los sistemas que tienes creados y en qué estado está cada uno. |
| **Planes** | Los paquetes que vendes (Básico, Pro…) con su precio y sus límites. |
| **Administradores** | Las personas que pueden entrar a ESTE panel (tú, y quien contrates para soporte). |
| **Roles** | Qué puede hacer cada tipo de administrador. |
| **Auditoría** | El historial de todo lo que se hizo en el panel y quién lo hizo. |

---

## 4. Lo primero: ajustar tus planes

Ya vienen 3 planes de ejemplo (**Básico $29, Pro $79, Premium $149**) con números inventados. Cámbialos a los tuyos.

1. Ve a **Planes** → **Editar** en uno (o **Nuevo plan**).
2. Pon el **nombre** y el **precio mensual**.
3. Pon los **límites**: cuántas sucursales, salas, mesas, productos y usuarios puede tener ese cliente.
   - **Déjalo vacío = ilimitado.**
4. **Guardar.**

Importante:
- Si cambias un plan, **todos los clientes que lo tienen reciben los nuevos límites** en menos de 30 segundos.
- Un plan que ya no quieres vender no se borra: se **archiva** (deja de ofrecerse a clientes nuevos, pero los
  que ya lo tienen siguen igual).

---

## 5. Dar de alta un cliente nuevo (paso a paso)

### Paso 1. Crear al cliente
**Clientes → Nuevo cliente.** Pon el nombre del restaurante (lo demás es opcional: RIF, contacto, correo…). **Guardar.**

### Paso 2. Crear su sistema
En la ficha del cliente, pulsa **Nueva suscripción e instancia**:
- Elige el **plan**.
- Escribe el **subdominio**: es el nombre de su dirección. Si pones `donluigi`, su sistema será
  `donluigi.restify.localhost:8088` (cuando compres el dominio: `donluigi.restify.com.ve`).
  - Solo minúsculas, números y guiones. Entre 3 y 32 caracteres. Hay nombres reservados (`www`, `panel`, `api`…).
- Pulsa **Crear y activar**. Espera unos 20 a 40 segundos (el agente está armando su sistema).

### Paso 3. Copiar el TOKEN
Sale una pantalla con un código largo que empieza con **`rst_`**. Ese es el **token**.

> ⚠️ **Se muestra UNA sola vez.** Cópialo ya. Es la "llave" de ese sistema. Si lo pierdes, no pasa nada grave:
> lo rotas (ver sección 8) y te da uno nuevo.

### Paso 4. Entregárselo al cliente
Mándale al cliente (por un medio seguro, tipo WhatsApp directo, no en un grupo):
1. Su **dirección** (ej: `donluigi.restify.localhost:8088`).
2. El **token**.

### Paso 5. Lo que hace el cliente
Al abrir su dirección por primera vez, le sale solo la **pantalla de Configuración inicial**:
1. Pega el **token**.
2. Crea su **usuario administrador** (nombre, correo, contraseña).
3. Pone su **primer local** (nombre y datos).
4. Elige su **moneda** y zona horaria.
5. **Terminar y entrar.** Ya está dentro con todo configurado.

Después de eso la pantalla de configuración inicial **desaparece para siempre** (nadie más puede usarla).

---

## 6. Estados de una cuenta: cuándo usar cada uno

Entra a la cuenta desde **Suscripciones** (o desde el cliente) y verás los botones.

| Estado | Cuándo usarlo | Qué pasa |
|---|---|---|
| **Activa** | Está al día. | Todo funciona normal. |
| **Pausada** | El cliente te pide parar un tiempo (vacaciones, remodelación). | Su sistema se **apaga**. Si alguien entra ve "Servicio no disponible". Sus datos quedan guardados. |
| **Suspendida** | Debe pagos, o hizo algo indebido. **Pide un motivo.** | Su sistema sigue encendido pero **le bloquea todo** y muestra "Cuenta suspendida" con tu motivo. Sus datos quedan guardados. |
| **Cancelada** | Se dio de baja. **Pide motivo y tu contraseña.** | Se apaga. **No se puede volver atrás.** |

- Para **reactivar** una pausada o suspendida, pulsa **Activar** / **Reanudar**. Vuelve en segundos.
- Un cliente suspendido o pausado **no pierde nada**: todo vuelve como estaba.
- Los cambios llegan al sistema del cliente en **hasta 30 segundos**.

### Eliminar un sistema del todo
Solo se puede si la cuenta está **Cancelada**. Aparece la caja roja **Eliminar instancia**: escribe el
subdominio exacto y tu contraseña. **Esto BORRA todos sus datos** (ventas, productos, todo). No hay vuelta atrás.
Úsalo solo cuando estés 100% seguro (y, si puedes, después de que el cliente haya respaldado lo suyo).

---

## 7. Cambiar el plan o los límites de un cliente

Dentro de la cuenta, sección **Plan y límites**:

- **Cambiar de plan:** elige el nuevo plan y pulsa **Cambiar plan**. Los límites nuevos aplican de inmediato.
- **Límites a la medida:** en la tabla ves el límite *del plan* y una casilla para ponerle uno *especial* a ESE cliente.
  Ejemplo: tiene plan Básico (1 sucursal) pero le quieres regalar 2: escribe `2` en sucursales.
  Vacío = usa el del plan.

**¿Qué ve el cliente cuando llega a un límite?** Al intentar crear algo de más (otra sucursal, otro producto…)
el sistema le dice: *"Llegaste al límite de tu plan. Tu plan permite hasta N… Pide un cambio de plan."*
Eso es tu oportunidad de venderle el siguiente plan 😉

---

## 8. Otras cosas útiles de una cuenta

### Fecha de vencimiento
**Vencimiento → elige la fecha → Guardar.** Cuando pasa esa fecha, el sistema sigue funcionando **3 días de gracia**
y luego se bloquea solo hasta que lo renueves (cambiando la fecha). Vacío = nunca vence.

> El panel **no cobra por ti**: tú cobras (transferencia, Zelle, lo que uses) y luego mueves la fecha.

### Dominio propio del cliente (ej: `menu.turestaurante.com`)
1. En **Dominio**, escribe el dominio del cliente y **Guardar dominio**.
2. El panel te muestra 2 registros DNS que el cliente (o quien le maneja el dominio) debe crear. Mándaselos.
3. Cuando los cree, pulsa **Verificar ahora**. Si sale "verificado", listo.
> En tu laptop esto es solo de práctica. Para que funcione de verdad hace falta el servidor (VPS).

### Rotar el token (si se filtró o se perdió)
**Token de la instancia** → escribe tu contraseña → **Rotar token**. Te muestra el nuevo (una vez).
El anterior deja de servir al instante.

### "Reintentar crear la instancia"
Si al crear un sistema algo falló (casi siempre: el **agente estaba apagado**), la cuenta queda con estado de
infraestructura "error" y aparece este botón. Enciende el agente y púlsalo. Es seguro repetirlo.

---

## 9. Administradores y roles (para tu equipo)

### Crear un administrador
**Administradores → Nuevo administrador:** nombre, correo, rol y una contraseña **temporal**.
Cuando entre por primera vez le obliga a cambiarla y a configurar su 2FA.

### Roles que ya vienen
- **Superadmin:** todo. (Tú.) No se puede editar.
- **Soporte:** atiende clientes y cambia estados, pero no toca planes ni administradores.
- **Solo lectura:** puede mirar, no cambia nada.

### Crear un rol a tu gusto
**Roles → Nuevo rol** y marca la tabla: por cada área (Clientes, Suscripciones…) marca *crear, leer, editar, eliminar*.
Solo puedes dar permisos que tú mismo tienes. Al guardar, quienes tengan ese rol deben volver a entrar.

### Si alguien perdió su celular
**Administradores → Editar** esa persona → **Reiniciar 2FA** (te pide tu contraseña). En su próximo ingreso
configura uno nuevo.

---

## 10. Auditoría (quién hizo qué)

**Auditoría** muestra cada acción: crear clientes, cambiar estados, entradas fallidas… con fecha y quién fue.
- Filtra escribiendo, por ejemplo, `suscripcion.` o `auth.`.
- **Verificar integridad:** comprueba que nadie haya borrado o cambiado eventos a escondidas. Debe decir
  *"La cadena de eventos está íntegra"*.

---

## 11. Tu cuenta

Abajo del menú de la izquierda, bajo tu nombre → **Mi cuenta**:
- **Cambiar contraseña** (cierra tus otras sesiones).
- **Regenerar códigos de recuperación** (los anteriores dejan de servir).

---

## 12. Si algo no funciona

| Problema | Qué hacer |
|---|---|
| La cuenta quedó en **"error"** al crearla | Enciende el agente (`./infra/iniciar.sh`) y pulsa **Reintentar crear la instancia**. |
| No abre `donluigi.restify.localhost:8088` | ¿Está encendido el proxy? (`cd infra/proxy && docker compose up -d`). ¿La cuenta está pausada? |
| Sale "Servicio no disponible" | La cuenta está **pausada**, se está creando aún, o el sistema está apagado. |
| El cliente dice "Cuenta suspendida" | Es lo esperado si la suspendiste. Actívala cuando pague. |
| El cliente dice "Ese token es de otra instancia" | Le diste el token de otro cliente. Revisa cuál es el correcto. |
| El cliente dice "Token incorrecto" | Está incompleto o mal copiado. Rota el token y mándale el nuevo. |
| Perdiste el celular del 2FA | Usa uno de tus **códigos de recuperación**. Si no los tienes, otro superadmin puede reiniciarte el 2FA. |
| Te bloqueó la cuenta | Son 5 intentos fallidos: espera 15 minutos. |
| Quieres borrar todo y empezar de cero | Mira "Limpiar todo" en `infra/README.md`. |

---

## 13. Glosario express

- **Instancia:** el sistema de UN cliente (su propia base de datos y su propia dirección).
- **Subdominio:** la primera parte de su dirección (`donluigi` en `donluigi.restify...`).
- **Token:** la llave secreta que une el sistema del cliente con tu panel.
- **Suscripción:** el "contrato": qué plan tiene, hasta cuándo, en qué estado.
- **2FA:** el segundo candado: un código que cambia cada 30 segundos en tu celular.
- **Agente:** el programita en tu máquina que de verdad crea y apaga los sistemas. Si está apagado, el panel no puede crear nada.
