# Restify · Front

Panel del personal, pantalla de cocina (KDS) y menú público por QR de Restify.

**Stack:** Next.js 16 (App Router) · React 19 · TypeScript estricto · Tailwind CSS 4 · Motion ·
TanStack Query · Zod · big.js

## Correr en local

Necesita el backend levantado (`../backend`, por defecto en `http://localhost:8010`).

```bash
cp .env.example .env.local   # y completa las keys
npm install
npm run dev                  # http://localhost:3000 (otro puerto: PORT=3001 npm run dev)
```

- `/design`: el sistema de diseño en vivo (tokens, tipografía y componentes).
- `npm run typecheck` · `npm run lint` · `npm run build`

## Con Docker

El backend tiene que estar arriba primero, porque el front se une a su red (`restify_default`).

```bash
cp .env.example .env
docker compose up -d --build   # http://localhost:3000
```

Dentro de Docker, `API_URL` se fuerza a `http://api:8000`. `NEXT_PUBLIC_WS_URL` se incrusta al
compilar: si cambia, reconstruye la imagen.

## Variables de entorno

| Variable | Dónde vive | Para qué |
|---|---|---|
| `API_URL` | Servidor | URL de la API vista desde Next (`http://api:8000` en Docker) |
| `PANEL_API_KEY` | Servidor | `X-API-Key` del panel del personal |
| `PUBLIC_API_KEY` | Servidor | `X-API-Key` del menú QR y el seguimiento |
| `KITCHEN_API_KEY` | Servidor | Opcional. Si existe, la usa el KDS en lugar de la del panel |
| `SESSION_SECRET` | Servidor | 32+ caracteres para cifrar la cookie de sesión |
| `COOKIE_SECURE` | Servidor | `true` por defecto. `false` solo para probar por http desde otro dispositivo de la red |
| `NEXT_PUBLIC_WS_URL` | Navegador | Base del WebSocket del backend (`ws://` o `wss://`) |

El navegador nunca ve las API keys ni el refresh token: todas las llamadas pasan por los route
handlers de Next (patrón BFF). Las keys se crean en el backend con
`docker compose exec api python -m app.cli crear-api-key --nombre "Panel web"`.

## Pantallas

| Ruta | Para quién |
|---|---|
| `/login` | Personal |
| `/panel` (Sala), `/panel/comandas`, `/panel/caja/[id]`, `/panel/caja/[id]/dividir`, `/panel/clientes` | Caja y meseros |
| `/cocina` | Pantalla de cocina (KDS), pensada para tablet o TV horizontal |
| `/panel/inventario`, `/panel/alertas`, `/panel/insumos`, `/panel/recetas`, `/panel/categorias`, `/panel/productos` | Inventario y catálogo |
| `/panel/ventas` | Reportes, ventas por facturar y libro de ventas (CSV) |
| `/panel/ventas/[id]/factura` | Documento para facturar a mano (ticket 80 mm o carta) y registro del N° de factura |
| `/panel/admin/{usuarios,roles,sucursales,monedas,mesas,seguridad}` | Administración (seguridad: solo superadmin) |
| `/mesa/[qr]`, `/pedido/[tracking]`, `/menu/[sucursal]` | Cliente final (sin login) |
| `/design` | Sistema de diseño en vivo |

## Sesión y BFF

- `POST /bff/auth/login`: llama a `/auth/login` con la key del panel y guarda el access y el
  refresh en **una cookie `rs_session`** `httpOnly; Secure; SameSite=Strict`, cifrada con JWE
  (A256GCM). El navegador la guarda pero no puede leerla.
- `/bff/{panel|cocina|public}/<ruta>`: es el proxy hacia `/api/v1/<ruta>`. Agrega la key de la app
  y el bearer, renueva el access si vence y reintenta una vez ante un 401. `public` no usa sesión y
  solo llega a `/public/*`.
- **Renovación sin carreras:** el backend revoca toda la sesión si ve un refresh reutilizado, así
  que las renovaciones simultáneas se deduplican por refresh token. El mapa vive en memoria del
  proceso: con varias réplicas de Next hace falta afinidad de sesión o moverlo a Redis.
- **CSRF:** además de `SameSite=Strict`, toda escritura exige el header `x-restify: 1` y un
  `Origin` igual al host.
- **WebSocket:** el navegador pide el ticket por el BFF (`/bff/panel/auth/ws-ticket`) y conecta
  directo a `NEXT_PUBLIC_WS_URL`. Pide un ticket nuevo en cada reconexión (backoff exponencial con
  jitter, hasta 30 s).

## Producción: IP real del cliente

El backend limita por IP (login y menú público). Para que el límite sea por cliente y no global:

1. **Pon un proxy inverso delante de Next** (el mismo nginx o Caddy con TLS que pide el backend) que
   **sobrescriba** `X-Forwarded-For` con la IP real. En nginx:
   `proxy_set_header X-Forwarded-For $remote_addr;`. Next deja pasar ese header tal cual llega, así
   que sin proxy un cliente podría falsificarlo.
2. En el backend, incluye la red desde la que llama Next en `FORWARDED_ALLOW_IPS`
   (p. ej. `127.0.0.1,172.23.0.0/16`, según `docker network inspect restify_default`).

## Archivos que pone el equipo

| Archivo | Uso |
|---|---|
| `public/fonts/Gagalin-Regular.woff2` (y `.woff`) | Tipografía display. Sin ella cae a General Sans |
| `public/brand/restify-sello.png` | Sello del logo, blanco sobre transparente (mín. 800 px). Sin él se ve la palabra RESTIFY |

General Sans viene incluida (`public/fonts/`, licencia FFL de Indian Type Foundry).

## Decisiones

- **Tema oscuro en todo**, con base `#1a1819`. Los tokens están en `src/app/globals.css` (`@theme`).
- **Dinero:** llega como string decimal y nunca se convierte a `float`. `src/lib/money.ts` formatea
  el string, y la única aritmética del cliente (la vista previa de caja) usa big.js con el mismo
  redondeo que el backend (`ROUND_HALF_UP`).
- **Movimiento:** los resortes están en `src/lib/motion.ts`. `MotionConfig reducedMotion="user"`
  respeta `prefers-reduced-motion`.
- **Medios:** `/media/*` se sirve vía `src/app/media/[...path]/route.ts`, que lee `API_URL` en runtime.
