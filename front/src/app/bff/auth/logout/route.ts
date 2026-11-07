import { backendFetch, clientIp } from "@/lib/server/backend";
import { detail, isSameOriginWrite } from "@/lib/server/http";
import { clearSession, readSession } from "@/lib/server/session";

export async function POST(request: Request) {
  if (!isSameOriginWrite(request)) return detail(403, "Origen no permitido");
  const session = await readSession();
  if (session) {
    // Revoca toda la familia del refresh en el backend; si falla, igual se borra la cookie
    await backendFetch("panel", "/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: session.refresh }),
      contentType: "application/json",
      ip: clientIp(request),
    }).catch(() => null);
  }
  await clearSession();
  return new Response(null, { status: 204 });
}
