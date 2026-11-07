import { backendFetch, clientIp, isApiKeyError, refreshSession, type AppKind } from "@/lib/server/backend";
import { detail, isSameOriginWrite, passthrough } from "@/lib/server/http";
import { clearSession, readSession, writeSession, type Session } from "@/lib/server/session";

/**
 * Proxy BFF: /bff/{panel|cocina|public}/<ruta de la API>
 *
 * - Agrega la X-API-Key de la app (solo vive en el servidor).
 * - panel y cocina: agrega el access token de la cookie cifrada; lo renueva si
 *   vence y reintenta una vez si la API responde 401.
 * - public: sin sesión y limitado a /public/*.
 */
const APPS = new Set<AppKind>(["panel", "cocina", "public"]);
const SEGMENT = /^[A-Za-z0-9_-]+$/;
// Estas rutas manejan tokens y tienen su propio handler en /bff/auth
const BLOCKED = new Set(["auth/login", "auth/refresh", "auth/logout"]);

type Ctx = { params: Promise<{ app: string; path: string[] }> };

async function handle(request: Request, { params }: Ctx): Promise<Response> {
  const { app: rawApp, path } = await params;
  const app = rawApp as AppKind;
  if (!APPS.has(app) || !path.every((s) => SEGMENT.test(s))) return detail(404, "No encontrado");
  if (!isSameOriginWrite(request)) return detail(403, "Origen no permitido");

  const route = path.join("/");
  if (BLOCKED.has(route)) return detail(404, "No encontrado");
  if (app === "public" && path[0] !== "public") return detail(404, "No encontrado");

  const url = new URL(request.url);
  const apiPath = `/${route}${url.search}`;
  const ip = clientIp(request);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  // Se guarda en memoria para poder reintentar tras renovar el token
  const body = hasBody ? await request.arrayBuffer() : null;
  const init = {
    method: request.method,
    body: body && body.byteLength > 0 ? body : null,
    contentType: request.headers.get("content-type"),
    accept: request.headers.get("accept"),
    ip,
  };

  if (app === "public") {
    const res = await backendFetch(app, apiPath, init);
    return (await isApiKeyError(res)) ? misconfigured(app) : passthrough(res);
  }

  let session: Session | null = await readSession();
  if (!session) return detail(401, "Tu sesión terminó. Vuelve a entrar.");

  let refreshed = false;
  if (session.accessExp <= Date.now()) {
    session = await refreshSession(app, session.refresh, ip);
    refreshed = true;
    if (!session) return expired();
  }

  let res = await backendFetch(app, apiPath, { ...init, token: session.access });
  if (res.status === 401 && !refreshed && !(await isApiKeyError(res))) {
    session = await refreshSession(app, session.refresh, ip);
    refreshed = true;
    if (!session) return expired();
    res = await backendFetch(app, apiPath, { ...init, token: session.access });
  }

  if (res.status === 401) {
    if (await isApiKeyError(res)) return misconfigured(app);
    return expired();
  }
  if (refreshed) await writeSession(session);
  return passthrough(res);
}

async function expired(): Promise<Response> {
  await clearSession();
  return detail(401, "Tu sesión terminó. Vuelve a entrar.");
}

function misconfigured(app: AppKind): Response {
  const variable = app === "public" ? "PUBLIC_API_KEY" : app === "cocina" ? "KITCHEN_API_KEY o PANEL_API_KEY" : "PANEL_API_KEY";
  console.error(`[bff] La API rechazó la API key de "${app}". Revisa ${variable}.`);
  return detail(502, "El servidor no está bien configurado. Avisa al administrador.");
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
