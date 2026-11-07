"use client";

import { useQuery } from "@tanstack/react-query";
import { can, useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { TurnoOut } from "@/lib/api/schemas";

/** Turno de caja abierto en la sucursal (null = caja cerrada). */
export function useTurnoActual(sucursalId: number | undefined) {
  const { data: me } = useMe();
  return useQuery({
    queryKey: ["caja", "turno", sucursalId],
    queryFn: () => api("/caja/turno-actual", { query: { sucursal_id: sucursalId }, schema: TurnoOut.nullable() }),
    enabled: !!sucursalId && can(me, "caja"),
    staleTime: 15_000,
  });
}
