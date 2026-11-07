import type { z } from "zod";
import { ApiError } from "./errors";

export type App = "panel" | "cocina" | "public";

export interface RequestOptions<S extends z.ZodType | undefined> {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, string | number | boolean | null | undefined>;
  /** Objeto (se envía como JSON) o FormData (subidas). */
  body?: unknown;
  schema?: S;
  app?: App;
  signal?: AbortSignal;
}

type Result<S> = S extends z.ZodType ? z.infer<S> : unknown;

let onUnauthorized: (() => void) | null = null;
/** El shell del panel registra qué hacer cuando la sesión muere (ir al login). */
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

/**
 * Todas las llamadas del navegador pasan por el BFF (/bff/<app>/...). Nunca
 * llevan API key ni tokens: eso lo agrega el servidor.
 */
export async function api<S extends z.ZodType | undefined = undefined>(
  path: string,
  { method = "GET", query, body, schema, app = "panel", signal }: RequestOptions<S> = {},
): Promise<Result<S>> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  const url = `/bff/${app}${path}${qs.size ? `?${qs}` : ""}`;

  const headers: HeadersInit = { "x-restify": "1", accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["content-type"] = "application/json";
  }

  const res = await fetch(url, { method, headers, body: payload, signal, credentials: "same-origin" });
  if (res.status === 204) return undefined as Result<S>;

  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const retry = Number(res.headers.get("retry-after")) || null;
    const err = new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? null, retry);
    if (res.status === 401 && app !== "public") onUnauthorized?.();
    throw err;
  }
  if (!schema) return data as Result<S>;
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    // El contrato cambió: mejor fallar fuerte que mostrar datos a medias
    console.error(`[api] Respuesta inesperada de ${path}`, parsed.error.issues);
    throw new ApiError(500, "La respuesta del servidor no tiene el formato esperado");
  }
  return parsed.data as Result<S>;
}
