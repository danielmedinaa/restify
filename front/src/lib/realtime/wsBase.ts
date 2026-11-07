/**
 * Base del WebSocket. Si se fijó NEXT_PUBLIC_WS_URL al compilar (desarrollo) se usa esa; si no, el mismo
 * dominio de la página. Así una sola imagen del front sirve para cualquier instancia (<cliente>.restify...).
 */
export function wsBase(): string | null {
  const fijo = process.env.NEXT_PUBLIC_WS_URL;
  if (fijo) return fijo;
  if (typeof window === "undefined") return null;
  return `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
}
