import "server-only";

import { env } from "./env";
import type { Session } from "./session";

export type AppKind = "panel" | "cocina" | "public";

export interface TokenOut {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expira_en_seg: number;
}

const API_KEY_DETAIL = "API key requerida o inválida";

export function apiKeyFor(app: AppKind): string {
  if (app === "public") return env.publicKey;
  if (app === "cocina") return env.kitchenKey;
  return env.panelKey;
}

/**
 * IP real del cliente para que el rate limit del backend sea por persona y no
 * global. Se toma el último salto de X-Forwarded-For, que es el que escribe el
 * proxy inverso de delante (nginx/Caddy).
 *
 * Ojo: Next solo pone la IP del socket si el header NO viene, y si viene lo deja
 * intacto. Sin proxy delante, el cliente puede falsificarla. Por eso en producción
 * el proxy debe sobrescribirlo (nginx: proxy_set_header X-Forwarded-For $remote_addr).
 */
export function clientIp(request: Request): string | null {
  const xff = request.headers.get("x-forwarded-for");
  const last = xff?.split(",").at(-1)?.trim();
  return last || request.headers.get("x-real-ip");
}

export interface BackendInit {
  method?: string;
  body?: BodyInit | null;
  contentType?: string | null;
  token?: string;
  ip?: string | null;
  accept?: string | null;
}

export function backendFetch(app: AppKind, path: string, init: BackendInit = {}): Promise<Response> {
  const headers = new Headers({ "X-API-Key": apiKeyFor(app) });
  if (init.contentType) headers.set("content-type", init.contentType);
  if (init.accept) headers.set("accept", init.accept);
  if (init.token) headers.set("authorization", `Bearer ${init.token}`);
  if (init.ip) headers.set("x-forwarded-for", init.ip);
  return fetch(`${env.apiUrl}/api/v1${path}`, {
    method: init.method ?? "GET",
    headers,
    body: init.body ?? null,
    cache: "no-store",
    redirect: "manual",
  });
}

/** Un 401 por API key mala es un error de configuración, no de sesión: no se renueva. */
export async function isApiKeyError(res: Response): Promise<boolean> {
  if (res.status !== 401) return false;
  try {
    const body = (await res.clone().json()) as { detail?: unknown };
    return body.detail === API_KEY_DETAIL;
  } catch {
    return false;
  }
}

export function sessionFromTokens(t: TokenOut): Session {
  // 20 s de margen para no usar un token que vence en tránsito
  return { access: t.access_token, refresh: t.refresh_token, accessExp: Date.now() + (t.expira_en_seg - 20) * 1000 };
}

/**
 * Renovación con deduplicación. El backend rota el refresh token y, si ve uno ya
 * usado, revoca toda la sesión (detección de robo). Si dos peticiones del mismo
 * navegador vencen a la vez, ambas deben recibir el MISMO par nuevo: se guarda la
 * promesa por refresh token durante un minuto.
 *
 * Limitación: es memoria del proceso. Con varias réplicas de Next hace falta
 * afinidad de sesión o mover este mapa a Redis.
 */
const inflight = new Map<string, { promise: Promise<Session | null>; at: number }>();

export function refreshSession(app: AppKind, refresh: string, ip: string | null): Promise<Session | null> {
  const now = Date.now();
  for (const [k, v] of inflight) if (now - v.at > 60_000) inflight.delete(k);

  const hit = inflight.get(refresh);
  if (hit) return hit.promise;

  const promise = backendFetch(app, "/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refresh }),
    contentType: "application/json",
    ip,
  })
    .then(async (res) => (res.ok ? sessionFromTokens((await res.json()) as TokenOut) : null))
    .catch((err: unknown) => {
      inflight.delete(refresh); // un fallo de red no debe quedar cacheado
      throw err;
    });
  inflight.set(refresh, { promise, at: now });
  return promise;
}
