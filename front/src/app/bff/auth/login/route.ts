import { z } from "zod";
import { backendFetch, clientIp, isApiKeyError, sessionFromTokens, type TokenOut } from "@/lib/server/backend";
import { detail, isSameOriginWrite, passthrough } from "@/lib/server/http";
import { writeSession } from "@/lib/server/session";

const LoginIn = z.object({ email: z.string().trim().min(1).max(254), password: z.string().min(1).max(128) });

export async function POST(request: Request) {
  if (!isSameOriginWrite(request)) return detail(403, "Origen no permitido");
  const parsed = LoginIn.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return detail(422, "Escribe tu correo y tu contraseña");

  const ip = clientIp(request);
  const res = await backendFetch("panel", "/auth/login", {
    method: "POST",
    body: JSON.stringify(parsed.data),
    contentType: "application/json",
    ip,
  });
  if (await isApiKeyError(res)) return detail(502, "El panel no está bien configurado (PANEL_API_KEY)");
  if (!res.ok) return passthrough(res);

  const session = sessionFromTokens((await res.json()) as TokenOut);
  await writeSession(session);
  // Devuelve el perfil para entrar al panel sin otra ida y vuelta
  return passthrough(await backendFetch("panel", "/auth/me", { token: session.access, ip }));
}
