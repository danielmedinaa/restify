# Manual de RESTIFY (para el restaurante)

**Para quién es:** para el dueño, el encargado, la caja, la cocina y los meseros de un restaurante que usa RESTIFY.
RESTIFY te ayuda a llevar **mesas, pedidos, cocina, caja, inventario y ventas** en un solo lugar, en tiempo real.

> Idea central: el cliente pide (o caja anota) → la cocina prepara → caja cobra → el sistema descuenta el
> inventario y guarda la venta. Tú solo vas siguiendo ese camino.

---

## PARTE 1 · Primera vez: dejar el sistema listo

### 1.1 Configuración inicial (una sola vez)
Tu proveedor te entrega una **dirección** (ej: `turestaurante.restify.com.ve`) y un **token** (empieza con `rst_`).

1. Abre la dirección. Te sale **Configuración inicial**.
2. **Token:** pégalo. Te dice tu plan.
3. **Administrador:** tu nombre, correo y contraseña (mínimo 10 caracteres con mayúsculas, minúsculas y números).
4. **Primer local:** nombre de tu sucursal (dirección y datos fiscales son opcionales).
5. **Moneda y zona horaria:** la moneda en la que pones tus precios (ej: Dólar) y tu país.
6. **Revisar** y **Terminar y entrar.**

Con eso ya estás dentro. (Esta pantalla solo se usa una vez.)

### 1.2 Armar tu restaurante: en este orden
Ve armando de lo básico a lo completo (menú de la izquierda):

1. **Administración → Monedas:** agrega otras monedas (ej: Bolívares) con su **tasa**. Marca cuál es de **divisa** y cuál es la **de la factura**.
2. **Inventario → Insumos:** los ingredientes (carne, pan, queso…) con su unidad (g, ml, unidad).
3. **Inventario → Existencias:** cuánto tienes de cada uno y el **stock mínimo** (el aviso de "se está acabando").
4. **Catálogo → Recetas:** cuánto lleva cada plato (ej: Hamburguesa = 150 g de carne + 1 pan). Puedes marcar ingredientes "quitables".
5. **Catálogo → Estaciones:** dónde se prepara (Cocina, Barra…).
6. **Catálogo → Categorías:** Hamburguesas, Bebidas, Postres…
7. **Catálogo → Productos:** cada plato con su **precio**, categoría, receta, fotos y IVA.
8. **Administración → Mesas y QR:** crea tus mesas (y zonas como Salón, Terraza). Aquí imprimes los **QR**.
9. **Administración → Usuarios y Roles:** crea al personal y dile a cada quien qué puede hacer.

> No tienes que hacerlo todo hoy. Con **monedas + productos + mesas** ya puedes empezar a tomar pedidos.

---

## PARTE 2 · El día a día

### 2.1 Abrir el día: Turno de caja
**Operación → Turno de caja → abrir.** Anota con cuánto efectivo empiezas (el "fondo") por moneda.
Todo lo que se cobre quedará registrado en este turno.
- Durante el día puedes registrar **ingresos** y **retiros** de efectivo.
- Al final, **cerrar el turno** hace el **arqueo**: el sistema te dice cuánto efectivo debería haber y lo comparas con lo que tienes.

### 2.2 Sala (el mapa de mesas)
**Operación → Sala** muestra tus mesas como un plano: libres, ocupadas, con pedido en cocina…
- Si tienes varias sucursales, elige la sucursal arriba.
- Arriba verás si estás **en vivo** (conectado en tiempo real).

### 2.3 Tomar un pedido (comanda)
Hay dos formas de que nazca un pedido:

**A) Lo anota caja/mesero**
1. En **Sala**, toca una mesa libre (o **Comandas → Abrir comanda** para llevar, sin mesa).
2. Agrega los platos. Cada unidad cuenta como un plato aparte (2 hamburguesas = *Hamburguesa #1* y *#2*).
3. Si el cliente pide quitar algo (sin cebolla), márcalo.
4. Pulsa **Enviar a cocina.**

**B) Lo pide el cliente con el QR** (ver Parte 3)
Llega como **Pendiente** y la mesa queda bloqueada. Caja lo revisa y lo **aprueba/envía a cocina**.
Si nadie lo confirma en ~15 minutos, **se cancela solo** y la mesa se libera.

### 2.4 El camino de un pedido
```
PENDIENTE → EN COCINA → PREPARANDO → LISTO → ENTREGADO → (cobrado y cerrado)
```
- Al **enviar a cocina**, el sistema **reserva** los ingredientes.
- Cuando la cocina lo marca **listo**, se **descuenta** del inventario.
- Si cancelas antes de "listo", se **libera** lo reservado.
- El menú **deja de ofrecer** un plato cuando ya no alcanza el ingrediente.

### 2.5 Cocina (pantalla de cocina)
**Operación → Cocina** es la pantalla para los cocineros (se puede dejar en una tablet/TV):
- Ven los platos que entran, por estación (Cocina, Barra).
- Marcan cada plato: **preparando → listo**.
- Suena/avisa cuando entra algo nuevo, en tiempo real.

### 2.6 Cobrar
En la comanda, pulsa **Cobrar.**
- Elige la **moneda** y el **método** (efectivo, punto, transferencia…). Puedes **mezclar** monedas y métodos en una misma cuenta.
- En efectivo puedes poner con qué billete paga y el sistema calcula el **vuelto**.
- Para transferencias, anota la **referencia**.
- **Dividir cuenta:** en partes iguales, o por platos (cada quien paga lo suyo).
- Cuando queda todo pagado, se **cierra** la comanda: se crea la **venta** y la mesa se libera.

**Extras en la cuenta** (todo queda anotado en la Bitácora):
- **Descuento** (en % o monto, con motivo).
- **Cortesía** en un plato (no se cobra).
- **Propina** (se cobra, pero no cuenta como venta).

### 2.7 Cerrar el día
1. Cierra el **turno de caja** (arqueo).
2. Revisa **Negocio → Ventas → Cierre del día.**

---

## PARTE 3 · Pedidos con QR (para tus clientes)

**Lo que hace tu cliente:**
1. Escanea el **QR de su mesa**.
2. Ve el **menú** (con fotos). Los platos agotados no aparecen.
3. Elige y envía el pedido.
4. Recibe un **link de seguimiento** para ver su pedido en vivo y agregar más platos.

**Lo que haces tú:**
- Imprime los QR en **Administración → Mesas y QR** (puedes **regenerar** el QR de una mesa si alguien lo fotografió).
- Puedes **apagar el QR** de una mesa (entonces solo caja abre comandas ahí).
- Los pedidos QR llegan como **Pendiente**: caja debe confirmarlos.

---

## PARTE 4 · Inventario y compras

| Pantalla | Para qué |
|---|---|
| **Existencias** | Cuánto tienes de cada insumo ahora. |
| **Reponer** | Cuando llega mercancía: escanea el **código de barras o QR** con la cámara y suma la entrada. |
| **Alertas** | Lo que está en o bajo el **stock mínimo**. Te avisa también con una campanita arriba. |
| **Insumos** | La lista de ingredientes (crear, editar). |
| **Compras / Proveedores** | Registra lo que compras y a quién. **Actualiza el costo** de cada insumo (el último que pagaste). |

Cosas que puedes registrar en una existencia: **entrada**, **merma** (se dañó/venció) y **ajuste** (conteo físico).

---

## PARTE 5 · Saber si ganas o pierdes

- **Ventas:** lista de ventas con filtros por día, mes o año. Entra a una venta para ver su detalle.
- **Rentabilidad:** por cada plato, cuánto **te cuesta** (según su receta), cuánto ganas (**margen**) y el **food cost**.
  Así sabes qué plato te deja plata y cuál no.
- **Clientes:** tu libreta de clientes (para facturar y para conocerlos).

### Facturación (importante)
> **RESTIFY NO emite facturas.** Tú facturas con tu talonario o máquina fiscal. RESTIFY te da los datos listos y lleva el control.

1. Configura una vez: en la **sucursal** (RIF, razón social, domicilio fiscal), en **monedas** (cuál es la de la factura) y en cada **producto** (su IVA).
2. En una venta, abre **Factura** para ver el documento con los montos, el IVA y el total en Bs. Lleva la leyenda "Documento sin validez fiscal".
3. Cuando emitas tu factura real, **anota el número de factura y de control** en la venta. No se pueden repetir.
4. Puedes exportar el **libro de ventas** para tu contador (Excel).

---

## PARTE 6 · Administración (dueño / encargado)

| Pantalla | Para qué |
|---|---|
| **Usuarios** | Crear al personal. Si alguien se va, **desactívalo** (cierra su sesión al instante). |
| **Roles** | Decidir qué puede hacer cada rol (ver, crear, editar, eliminar) en cada módulo. Ejemplo: "Cajero" sí cobra, pero no toca precios. |
| **Sucursales** | Tus locales y sus datos fiscales. Cada persona solo ve las sucursales que le asignes. |
| **Monedas** | Monedas y **tasas** (actualízalas cuando cambie el dólar). |
| **Mesas y QR** | Mesas, zonas, forma y tamaño, y sus QR. |
| **Bitácora** | Historial de "quién hizo qué" (descuentos, cambios de precio, etc.). |
| **Configuración** *(solo el administrador principal)* | IGTF, zona horaria, tiempo para que venza un pedido QR, etc. |
| **Seguridad** *(solo el administrador principal)* | Alertas de seguridad e intentos sospechosos. |

### Sugerencia de roles
- **Dueño/Administrador:** todo.
- **Caja:** comandas, caja, clientes, ventas (lectura).
- **Mesero:** sala y comandas.
- **Cocina:** solo la pantalla de cocina.
- **Compras:** inventario, insumos, compras y proveedores.

### Contraseña y cuenta
Abajo del menú, tu nombre → **Mi cuenta**: ahí cambias tu contraseña (cierra tus otras sesiones).

---

## PARTE 7 · Tu plan y sus límites

Tu plan define cuántas **sucursales, salas, mesas, productos y usuarios** puedes tener.
Si intentas crear uno de más verás un aviso claro: *"Llegaste al límite de tu plan…"*.
Para ampliar, **pídele a RESTIFY un cambio de plan**. Al hacerlo, el cambio se aplica en menos de un minuto, sin reiniciar nada.

### Mensajes que puedes ver
| Mensaje | Qué significa |
|---|---|
| **Cuenta suspendida** | Hay un pago pendiente u otro motivo (te lo indica). Contacta a RESTIFY; al regularizarlo vuelve en segundos. Tus datos están a salvo. |
| **Cuenta pausada / Servicio no disponible** | Tu cuenta está en pausa. Contacta a RESTIFY para reanudarla. |
| **Suscripción vencida** | Pasó tu fecha de pago y los días de gracia. Renueva con RESTIFY. |
| **Llegaste al límite de tu plan** | Pide un cambio de plan para agregar más. |
| **Tu sesión terminó** | Por seguridad se cierra tras un rato sin usarse. Vuelve a entrar. |
| **Mesa ocupada** | Esa mesa ya tiene una comanda abierta. |
| **Stock insuficiente** | Falta algún ingrediente para ese plato (te dice cuál y cuánto). |

---

## Preguntas frecuentes

**¿Se cae si se va el internet?** El sistema necesita conexión para funcionar en tiempo real. Si se va, espera a que vuelva; lo ya guardado no se pierde.

**¿Puedo usarlo en tablet o celular?** Sí, funciona desde el navegador. La cocina y la caja se pueden dejar en una tablet.

**Se me olvidó la contraseña.** Pídele a tu administrador que te asigne una nueva (o que revise tu usuario en Administración → Usuarios).

**¿Dónde veo quién cambió algo?** En **Administración → Bitácora**.

**Un plato no aparece en el menú QR.** Probablemente falta ingrediente (se agotó), el producto está inactivo o no está en esa sucursal.

---

## Rutina diaria en 6 pasos
1. **Abrir turno de caja.**
2. Mesas libres en **Sala**; pedidos por **Comandas** o QR.
3. **Cocina** marca platos listos.
4. **Cobrar** y cerrar cada cuenta.
5. Revisar **Alertas** de inventario y **Reponer** lo que llegó.
6. **Cerrar turno** y mirar el **Cierre del día**.
