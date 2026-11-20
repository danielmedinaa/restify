import "server-only";

import { env } from "./env";
import { TEMA_VACIO, TemaOut, type Tema } from "@/lib/api/schemas";

/** Tema de la marca para pintar toda la web. Si la API no responde, se ve la marca de RESTIFY. */
export async function obtenerTema(): Promise<Tema> {
  try {
    const res = await fetch(`${env.apiUrl}/api/v1/public/tema`, {
      headers: { "X-API-Key": env.publicKey },
      next: { revalidate: 10 },
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return TEMA_VACIO;
    const parsed = TemaOut.safeParse(await res.json());
    return parsed.success ? parsed.data : TEMA_VACIO;
  } catch {
    return TEMA_VACIO;
  }
}
