import { env } from "@/lib/server/env";

/**
 * Los medios del backend llegan como rutas relativas (/media/abc.jpg). Se sirven
 * desde este origen para no exponer la URL interna de la API ni pelear con CORS.
 * El backend no pide API key para /media, así que no se añade ninguna.
 */
const SEGMENTO = /^[A-Za-z0-9._-]+$/;

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (!path.every((s) => SEGMENTO.test(s) && s !== "." && s !== "..")) {
    return new Response(null, { status: 400 });
  }
  const headers = new Headers();
  const range = request.headers.get("range"); // los videos piden rangos
  if (range) headers.set("range", range);

  const upstream = await fetch(`${env.apiUrl}/media/${path.join("/")}`, { headers, cache: "no-store" });
  const out = new Headers();
  for (const h of ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]) {
    const v = upstream.headers.get(h);
    if (v) out.set(h, v);
  }
  out.set("cache-control", upstream.ok ? "public, max-age=86400" : "no-store");
  out.set("x-content-type-options", "nosniff");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}
