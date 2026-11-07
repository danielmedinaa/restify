"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { can, useMe } from "@/features/auth/useMe";
import { keys, notifyError } from "@/features/comandas/queries";
import { api } from "@/lib/api/client";
import { MesaOut, ZonaOut, type Mesa } from "@/lib/api/schemas";

const zonasKey = (sucursalId: number | undefined) => ["zonas", sucursalId] as const;

export function useZonas(sucursalId: number | undefined) {
  const { data: me } = useMe();
  return useQuery({
    queryKey: zonasKey(sucursalId),
    queryFn: () => api("/zonas", { query: { sucursal_id: sucursalId }, schema: z.array(ZonaOut) }),
    enabled: sucursalId != null && can(me, "mesas"),
  });
}

export function useZonaMutations(sucursalId: number | undefined) {
  const qc = useQueryClient();
  const refrescar = () => {
    void qc.invalidateQueries({ queryKey: zonasKey(sucursalId) });
    void qc.invalidateQueries({ queryKey: keys.mesas(sucursalId) });
  };
  return {
    crear: useMutation({
      mutationFn: (nombre: string) => api("/zonas", { method: "POST", body: { sucursal_id: sucursalId, nombre }, schema: ZonaOut }),
      onSuccess: refrescar,
      onError: notifyError,
    }),
    renombrar: useMutation({
      mutationFn: (v: { id: number; nombre: string }) => api(`/zonas/${v.id}`, { method: "PATCH", body: { nombre: v.nombre }, schema: ZonaOut }),
      onSuccess: refrescar,
      onError: notifyError,
    }),
    eliminar: useMutation({
      mutationFn: (id: number) => api(`/zonas/${id}`, { method: "DELETE" }),
      onSuccess: refrescar,
      onError: notifyError,
    }),
  };
}

export type CambioMesa = Partial<Pick<Mesa, "pos_x" | "pos_y" | "zona_id" | "forma" | "ancho" | "alto">>;

/** Edita posición, tamaño, forma o zona de una mesa. Optimista: el plano responde al soltar. */
export function useEditarMesa(sucursalId: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number } & CambioMesa) => {
      const { id, ...body } = v;
      return api(`/mesas/${id}`, { method: "PATCH", body, schema: MesaOut });
    },
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: keys.mesas(sucursalId) });
      const prev = qc.getQueryData<Mesa[]>(keys.mesas(sucursalId));
      qc.setQueryData<Mesa[]>(keys.mesas(sucursalId), (list) => list?.map((m) => (m.id === v.id ? { ...m, ...v } : m)));
      return { prev };
    },
    onError: (err, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.mesas(sucursalId), ctx.prev);
      notifyError(err);
    },
  });
}

export function useUnirMesas(sucursalId: number | undefined) {
  const qc = useQueryClient();
  const refrescar = () => void qc.invalidateQueries({ queryKey: keys.mesas(sucursalId) });
  return {
    unir: useMutation({
      mutationFn: (v: { principal: number; otras: number[] }) =>
        api(`/mesas/${v.principal}/unir`, { method: "POST", body: { mesa_ids: v.otras }, schema: z.array(MesaOut) }),
      onSuccess: refrescar,
      onError: notifyError,
    }),
    separar: useMutation({
      mutationFn: (mesaId: number) => api(`/mesas/${mesaId}/separar`, { method: "POST", schema: MesaOut }),
      onSuccess: refrescar,
      onError: notifyError,
    }),
  };
}
