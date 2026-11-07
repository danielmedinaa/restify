"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { MeOut, type Accion, type Me, type Modulo } from "@/lib/api/schemas";

export const meKey = ["auth", "me"] as const;

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: () => api("/auth/me", { schema: MeOut }), staleTime: 60_000 });
}

/** La UI oculta lo que no se puede usar. El backend igual valida cada acción. */
export function can(me: Me | undefined, modulo: Modulo, accion: Accion = "leer"): boolean {
  if (!me) return false;
  if (me.es_superadmin) return true;
  return me.permisos[modulo]?.[accion] === true;
}
