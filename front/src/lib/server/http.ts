import "server-only";

/** Respuesta JSON con el mismo formato de error que el backend ({ detail }). */
export function detail(status: number, message: string): Response {
  return Response.json({ detail: message }, { status });
}

/**
 * Defensa CSRF además de SameSite=Strict: toda escritura debe venir de este mismo
 * origen y con el header propio, que un formulario de otro sitio no puede enviar
 * sin pasar por un preflight de CORS que aquí nunca se aprueba.
 */
export function isSameOriginWrite(request: Request): boolean {
  if (request.method === "GET" || request.method === "HEAD") return true;
  if (request.headers.get("x-restify") !== "1") return false;
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

const PASSTHROUGH = ["content-type", "content-disposition", "retry-after", "cache-control"];

export function passthrough(res: Response): Response {
  const headers = new Headers();
  for (const h of PASSTHROUGH) {
    const v = res.headers.get(h);
    if (v) headers.set(h, v);
  }
  if (!headers.has("cache-control")) headers.set("cache-control", "no-store");
  return new Response(res.status === 204 ? null : res.body, { status: res.status, headers });
}
