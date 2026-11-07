# Restify API

Backend para restaurantes: usuarios y roles con permisos CRUD por módulo, sucursales, inventario
dinámico con alertas de stock mínimo, recetas, productos con fotos y videos, menú digital,
mesas con QR, comandas, caja multimoneda, cocina en tiempo real y ventas.

**Stack:** FastAPI · SQLAlchemy 2 (async) · PostgreSQL 16 · Alembic · Redis · Docker

## Puesta en marcha

```bash
cp .env.example .env          # y cambia TODOS los secretos
docker compose up -d --build  # aplica las migraciones al arrancar

# Configuración inicial
docker compose exec api python -m app.cli crear-superadmin --email admin@turestaurante.com --nombre "Admin"
docker compose exec api python -m app.cli crear-api-key --nombre "Panel web"
docker compose exec api python -m app.cli crear-moneda-principal --codigo USD --nombre "Dólar" --simbolo '$'
```

- Documentación interactiva: `http://localhost:${API_PORT}/docs` (desactivada con `ENVIRONMENT=production`).
- Tests (Postgres y Redis reales, sobre las migraciones de Alembic): `docker compose --profile test run --rm --build tests`

### Migraciones

```bash
# Después de cambiar un modelo:
docker compose run --rm --user "$(id -u):$(id -g)" -v "$PWD:/app" api alembic revision --autogenerate -m "descripcion"
docker compose run --rm api alembic upgrade head        # (la API también lo hace al arrancar)
docker compose run --rm api alembic downgrade -1
```

## Seguridad

| Capa | Qué hace |
|---|---|
| API key (`X-API-Key`) | Obligatoria en todo `/api/v1`, una por app cliente (panel, cocina, menú público). Se guarda hasheada, se puede revocar y se muestra una sola vez. |
| JWT | Access token de 15 min y refresh token rotativo de 7 días. Si se reutiliza un refresh token ya usado, se revoca toda la sesión (detección de robo). |
| Contraseñas | Argon2. Mínimo 10 caracteres combinando mayúsculas, minúsculas y números. |
| Login | Rate limit por IP y por cuenta. La cuenta se bloquea 15 min tras 5 fallos. El mensaje de error es genérico para no revelar si el email existe. |
| Revocación | Cambiar la contraseña, el rol o desactivar un usuario invalida al instante todos sus tokens (`token_version`). |
| Permisos | Matriz `módulo × {crear, leer, editar, eliminar}` por rol. Nadie puede otorgar permisos que no tiene ni editar su propio rol. |
| Sucursales | Cada usuario solo ve y opera las sucursales que tiene asignadas (el superadmin ve todas). |
| QR y seguimiento | Tokens aleatorios de 192 bits, no los ids. El QR se puede regenerar si alguien lo fotografió. |
| WebSocket | Ticket de un solo uso que dura 30 s, para no poner el JWT en la URL. |
| Uploads | El tipo se valida por los bytes reales del archivo, con tamaño máximo y nombre aleatorio en disco. |
| Integridad | `CHECK` en BD para que el stock nunca sea negativo, índice único que bloquea la mesa y `SELECT … FOR UPDATE` contra la sobreventa. |
| HTTP | Headers de seguridad (CSP, nosniff, DENY, HSTS en producción), CORS restringido, `TrustedHost` y límite de tamaño del body. |
| Auditoría | Toda escritura (POST/PUT/PATCH/DELETE) queda registrada con usuario, API key, ruta, resultado e IP. |
| Contenedor | Usuario sin privilegios. Postgres y Redis no exponen puertos. Redis usa contraseña. |

**En producción:** pon un proxy inverso con TLS (nginx, Caddy o Traefik) delante de la API, define
`FORWARDED_ALLOW_IPS` con la IP del proxy, usa `ENVIRONMENT=production`, configura
`client_max_body_size 51m` en el proxy y programa respaldos de Postgres y del volumen `media`.

## Flujo de una comanda

```
 Cliente escanea QR                    Caja (o abre la comanda manualmente, con o sin mesa)
        │                                │
        ▼                                ▼
   PENDIENTE ── caja "enviar-cocina" ──► EN_COCINA ──► PREPARANDO ──► LISTO ──► ENTREGADO
   (mesa bloqueada: 423)        (se RESERVA el stock)                (se DESCUENTA el stock;
                                                                      alerta si llega al mínimo)
   Cancelar antes de LISTO ──► se libera la reserva
   Cerrar (pagado completo) ──► se genera la VENTA y se desbloquea la mesa
```

- **Stock dinámico:** si hay 200 g de carne y se vende una hamburguesa de 150 g, al enviarla a cocina
  se reservan los 150 g. El menú deja de ofrecerla porque solo quedan 50 g disponibles, menos que una
  porción. Cuando cocina la marca lista se descuentan los 150 g. Si los 50 g restantes están en el
  stock mínimo o por debajo, se crea la alerta *"Stock bajo de Carne molida: quedan 50 g (mínimo 60 g)"*
  y se emite en tiempo real.
- **Cada unidad es un plato:** 2 hamburguesas se ven como *Hamburguesa #1* y *Hamburguesa #2*, y
  cocina las marca listas por separado.
- **QR opcional:** se puede desactivar por mesa con `qr_habilitado=false`. Caja abre comandas a mano
  en cualquier mesa o sin mesa (para llevar), y puede asignar o cambiar la mesa después.
- **Monedas:** precios en la moneda principal, convertidos a cada moneda secundaria con su tasa
  (`multiplicar` o `dividir`). Se puede pagar mezclando monedas y métodos, y cada pago guarda la tasa
  usada en ese momento.
- **Dividir cuenta:** en N partes iguales (`GET /comandas/{id}/division?partes=3`) o por platos
  (`POST /comandas/{id}/division`). Los pagos llevan una `etiqueta` para saber cuánto pagó cada parte.

## Facturación manual (SENIAT)

RESTIFY **no emite facturas**: el restaurante factura con su talonario o su máquina fiscal, y el
sistema le da los datos listos y lleva el control.

1. **Configuración.**
   - En cada sucursal: RIF, razón social, domicilio fiscal y si cobra IGTF.
   - En monedas: cuál es la **moneda de la factura** (bolívares) y cuáles son **divisas**.
   - En cada producto: sin IVA o su % de IVA.
   - En cada cliente: tipo y número de documento.
2. **Al cerrar la comanda**, la venta congela la tasa de la moneda fiscal. Cada plato ya guardó su
   alícuota al pedirse.
3. **`GET /ventas/{id}/fiscal`** devuelve el documento con emisor, receptor, líneas, base imponible e
   IVA por alícuota, exento, IGTF y total en Bs. Lleva la leyenda *"Documento sin validez fiscal"*.
4. Con **`PUT /ventas/{id}/factura`** se guarda el N° de factura, el N° de control y el receptor tal
   como se escribió. El número no puede repetirse en la sucursal.
5. **`GET /ventas/libro`** exporta el libro de ventas (CSV para Excel) con las facturas registradas.

Supuestos:
- **IVA por producto:** sin IVA o el % que corresponda. **Por sucursal** se decide si el precio
  cargado ya lo incluye o si se suma encima. En ese caso, cada plato congela al pedirse su precio con
  IVA, así que caja, pagos y ventas cobran el total correcto.
- **Tasa de la factura:** la del pago que el cliente hizo en bolívares. Si pagó todo en divisas, la
  vigente al cobrar.
- **El IGTF (3 %, `IGTF_PORCENTAJE`) es informativo**: se calcula sobre los pagos en divisas, pero
  todavía no se suma al cobro en caja.

## Caja, compras y costos

- **Turnos de caja:** `POST /caja/turnos` abre la caja con un fondo por moneda. Cada pago queda en el turno abierto. Con `POST /caja/turnos/{id}/movimientos` se registran ingresos y retiros, y `POST /caja/turnos/{id}/cerrar` hace el arqueo.
  - Efectivo esperado por moneda = fondo + cobrado en efectivo + ingresos − retiros − vueltos. Se asume que el vuelto se entrega en efectivo de la moneda principal.
- **Descuentos, cortesías y propina:** `PUT /comandas/{id}/descuento` (% o monto, con motivo), `PUT /comandas/{id}/items/{item}/cortesia` y `PUT /comandas/{id}/propina`. Todo queda en la bitácora.
  - La cortesía no se cobra ni se factura.
  - El descuento se reparte entre las alícuotas en el documento fiscal.
  - La propina se cobra, pero no es venta.
- **IGTF cobrado en caja:** en las sucursales que lo cobran, cada pago en divisas lleva el IGTF incluido (abono = pago × 100/103), y caja sugiere el monto exacto.
- **Compras y proveedores:** `POST /compras` suma el stock en la sucursal y actualiza el costo de cada insumo (el último costo pagado).
- **Rentabilidad:** `GET /rentabilidad?sucursal_id=` devuelve, por plato, costo de receta, margen y food cost.
- **Pedidos QR vencidos:** si nadie confirma un pedido en `QR_VENCIMIENTO_MIN` minutos (15 por defecto), se cancela solo y la mesa queda libre.

## Alertas de seguridad

El backend detecta, entre otras cosas: login fallido repetido por IP, cuentas bloqueadas, reutilización de un
refresh token (posible robo de sesión), API keys falsas, accesos sin permiso repetidos y exceso de peticiones.
Cada caso crea una `AlertaSeguridad` y la emite en tiempo real a los superadmin, a quienes el panel les muestra
una banda roja (y un modal si la alerta es crítica). Se consultan en `GET /seguridad/alertas` y se marcan con
`POST /seguridad/alertas/revisar`.

## Configuración desde el panel

En *Administración → Configuración* (solo superadmin) se cambia sin tocar el `.env`:
- IGTF
- vencimiento de los pedidos QR
- URLs del menú y del seguimiento
- zona horaria
- intentos y bloqueo de login
- límite del menú público
- tamaño de fotos y videos
- credenciales de la consulta de cédulas

**Cómo funciona:**
- **El panel manda sobre el `.env`.** "Restablecer" borra el valor guardado y se vuelve a usar el del `.env`.
- **Los cambios se aplican sin reiniciar,** en todos los workers en menos de 10 segundos.
- **Los secretos se guardan cifrados** con una clave derivada de `JWT_SECRET` y la API nunca los devuelve. Si cambias `JWT_SECRET`, hay que volver a cargarlos.
- **Cada cambio queda en la bitácora,** con el nombre del campo pero nunca su valor.

Por seguridad quedan **solo en el `.env`**: base de datos, Redis, `JWT_SECRET`, CORS, hosts permitidos e IPs del proxy.

## Consulta de cédulas (opcional)

Con el App ID y el token de [cedula.com.ve](https://cedula.com.ve), servicio de terceros, **no
oficial**, plan gratuito de 75 consultas por hora), cargados en *Configuración* (o en `CEDULA_API_APP_ID` / `CEDULA_API_TOKEN`), el panel autocompleta el nombre de una persona por su cédula cuando
todavía no es cliente.
- El token vive solo en el servidor.
- Las respuestas se guardan 30 días en caché.
- No devuelve el domicilio, solo la zona del centro de votación.
- Sin credenciales, la consulta queda desactivada (503).

## Endpoints principales (`/api/v1`)

| Módulo | Rutas |
|---|---|
| Auth | `POST /auth/login` · `/auth/refresh` · `/auth/logout` · `GET /auth/me` · `POST /auth/cambiar-password` · `/auth/ws-ticket` |
| Roles | `GET /roles/modulos` · CRUD `/roles` |
| Usuarios | CRUD `/usuarios` (con `sucursal_ids` y `rol_id`) |
| Sucursales | CRUD `/sucursales` |
| Monedas | CRUD `/monedas` · `POST /monedas/{id}/principal` |
| Insumos / Inventario | CRUD `/insumos` · `/inventario` · `POST /inventario/{id}/entrada`, `/merma`, `/ajuste` · `GET /inventario/{id}/movimientos` · `GET /alertas` |
| Recetas / Categorías | CRUD `/recetas` · `/categorias` |
| Productos | CRUD `/productos` · `PUT /productos/{id}/sucursales/{sucursal_id}` (precio y disponibilidad por sucursal) · `POST /productos/{id}/medios/archivo` (subida) · `POST /productos/{id}/medios/url` (externo) |
| Mesas | CRUD `/mesas` · `GET /mesas/{id}/qr?formato=png\|svg` · `POST /mesas/{id}/regenerar-qr` |
| Comandas | `/comandas` · `POST /comandas/{id}/items` · `/enviar-cocina` · `/items/{id}/entregar` · `/items/{id}/cancelar` · `/cancelar` |
| Caja | `POST /comandas/{id}/pagos` · `DELETE /comandas/{id}/pagos/{pago_id}` · `POST /comandas/{id}/cerrar` · `/comandas/{id}/division` |
| Cocina | `GET /cocina?sucursal_id=` · `POST /cocina/items/{id}/estado` (`preparando` o `listo`) |
| Ventas | `GET /ventas?dia=&mes=&anio=&fecha_desde=&fecha_hasta=&monto_min=&monto_max=&ordenar=` · `GET /ventas/{id}` (con platos y pagos) · `GET /ventas/resumen?agrupar=dia\|mes\|anio` · `?facturada=false` (pendientes por facturar) |
| Facturación | `GET /ventas/{id}/fiscal` (documento para facturar) · `PUT /ventas/{id}/factura` (registra N° de factura y control) · `DELETE /ventas/{id}/factura` · `GET /ventas/libro?mes=&anio=` (libro de ventas CSV) |
| Clientes | CRUD `/clientes?q=` |
| Público | `GET /public/mesas/{qr_token}` (menú y estado de la mesa) · `POST /public/mesas/{qr_token}/comandas` · `GET /public/pedidos/{tracking}` · `POST /public/pedidos/{tracking}/items` · `GET /public/sucursales/{id}/menu` |
| Seguridad (superadmin) | `/api-keys` · `GET /auditoria` |

### Tiempo real (WebSocket)

- **Personal:** `POST /api/v1/auth/ws-ticket` y luego `ws://host/ws/staff?ticket=...&sucursal_id=1`.
  Eventos: `comanda.creada`, `comanda.actualizada`, `comanda.items_cliente`, `cocina.nuevos`,
  `cocina.item_actualizado`, `comanda.cerrada`, `comanda.cancelada`, `stock.alerta`,
  `stock.alerta_resuelta`, `menu.actualizado`.
- **Cliente:** `ws://host/ws/pedidos/{tracking_token}`. Recibe `pedido.actualizado` con el estado de
  cada plato.

Los eventos pasan por Redis pub/sub, así que funcionan con varios workers o réplicas.



