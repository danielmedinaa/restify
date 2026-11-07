import "server-only";

import { backendFetch } from "./backend";

export interface SetupEstado {
  pendiente: boolean;
  requiereToken: boolean;
}

/** ¿La instancia es nueva (sin usuarios)? null si el backend no responde: ahí se deja seguir al login. */
export async function setupEstado(): Promise<SetupEstado | null> {
  try {
    const res = await backendFetch("public", "/public/setup/estado");
    if (!res.ok) return null;
    const d = (await res.json()) as { pendiente: boolean; requiere_token: boolean };
    return { pendiente: d.pendiente, requiereToken: d.requiere_token };
  } catch {
    return null;
  }
}
