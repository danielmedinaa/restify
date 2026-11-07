"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "@/components/ui/Toast";
import { api } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { CocinaComandaOut, EstacionOut, type CocinaComanda } from "@/lib/api/schemas";

export const tableroKey = (sucursalId: number | undefined, estacionId: number | null = null) => ["cocina", "sucursal", sucursalId, estacionId] as const;

export function useEstaciones() {
  return useQuery({ queryKey: ["estaciones"], queryFn: () => api("/estaciones", { app: "cocina", schema: z.array(EstacionOut) }), staleTime: 60_000 });
}

export function useTablero(sucursalId: number | undefined, estacionId: number | null) {
  return useQuery({
    queryKey: tableroKey(sucursalId, estacionId),
    queryFn: () => api("/cocina", { app: "cocina", query: { sucursal_id: sucursalId, estacion_id: estacionId ?? undefined }, schema: z.array(CocinaComandaOut) }),
    enabled: sucursalId != null,
    // Red de seguridad por si se pierde un evento: el WS es la fuente principal
    refetchInterval: 60_000,
  });
}

/** Cambia el estado de un plato. Optimista: en la pantalla de cocina no se espera. */
export function useMarcar(sucursalId: number | undefined, estacionId: number | null) {
  const qc = useQueryClient();
  const key = tableroKey(sucursalId, estacionId);
  return useMutation({
    mutationFn: (v: { id: number; estado: "preparando" | "listo" }) =>
      api(`/cocina/items/${v.id}/estado`, { app: "cocina", method: "POST", body: { estado: v.estado } }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<CocinaComanda[]>(key);
      qc.setQueryData<CocinaComanda[]>(key, (list) =>
        list
          ?.map((c) => ({ ...c, items: c.items.map((i) => (i.id === v.id ? { ...i, estado: v.estado } : i)) }))
          // Los listos salen del tablero; la comanda se va cuando no le queda nada
          .map((c) => ({ ...c, items: c.items.filter((i) => i.estado !== "listo") }))
          .filter((c) => c.items.length > 0),
      );
      return { prev };
    },
    onError: (err, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
      const e = describeError(err);
      toast({ title: e.title, description: e.description, tone: e.tone });
      void qc.invalidateQueries({ queryKey: key });
    },
  });
}
