"use client";

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import {
  ComandaOut,
  ComandaResumenOut,
  DivisionOut,
  MenuOut,
  MesaOut,
  MonedaOut,
  Pagina,
  type Comanda,
  type ComandaResumen,
  type Mesa,
  type Moneda,
} from "@/lib/api/schemas";

// ---------------------------------------------------------------- keys
export const keys = {
  abiertas: (sucursalId: number | undefined) => ["comandas", "abiertas", "sucursal", sucursalId] as const,
  historial: (sucursalId: number | undefined, estado: string) => ["comandas", estado, "sucursal", sucursalId] as const,
  comanda: (id: number) => ["comanda", id] as const,
  mesas: (sucursalId: number | undefined) => ["mesas", "sucursal", sucursalId] as const,
  menu: (sucursalId: number | undefined) => ["menu", "sucursal", sucursalId] as const,
  monedas: ["monedas"] as const,
};

// ---------------------------------------------------------------- lecturas
/** Todas las comandas abiertas de la sucursal (la API pagina de a 100). */
async function fetchAbiertas(sucursalId: number): Promise<ComandaResumen[]> {
  const out: ComandaResumen[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await api("/comandas", {
      query: { sucursal_id: sucursalId, estado: "abierta", limite: 100, offset },
      schema: Pagina(ComandaResumenOut),
    });
    out.push(...page.items);
    if (out.length >= page.total || page.items.length === 0) return out;
  }
}

export function useComandasAbiertas(sucursalId: number | undefined) {
  const { data: me } = useMe();
  return useQuery({
    queryKey: keys.abiertas(sucursalId),
    queryFn: () => fetchAbiertas(sucursalId!),
    enabled: sucursalId != null && can(me, "comandas"),
  });
}

export function useComanda(id: number) {
  return useQuery({ queryKey: keys.comanda(id), queryFn: () => api(`/comandas/${id}`, { schema: ComandaOut }) });
}

export function useMesas(sucursalId: number | undefined) {
  const { data: me } = useMe();
  return useQuery({
    queryKey: keys.mesas(sucursalId),
    queryFn: () => api("/mesas", { query: { sucursal_id: sucursalId, activa: true }, schema: z.array(MesaOut) }),
    enabled: sucursalId != null && can(me, "mesas"),
  });
}

export function useMenu(sucursalId: number | undefined, enabled = true) {
  const { data: me } = useMe();
  return useQuery({
    queryKey: keys.menu(sucursalId),
    queryFn: () => api(`/menu/${sucursalId}`, { schema: MenuOut }),
    enabled: enabled && sucursalId != null && can(me, "productos"),
    staleTime: 30_000,
  });
}

/**
 * Monedas activas con su tasa, para la vista previa de caja. Quien no puede leer
 * monedas las obtiene del menú (que las incluye). Si no hay ninguna fuente, la
 * caja funciona igual pero sin vista previa.
 */
export function useMonedas(sucursalId: number | undefined): { data: Moneda[] | undefined; isPending: boolean } {
  const { data: me } = useMe();
  const directas = useQuery({
    queryKey: keys.monedas,
    queryFn: () => api("/monedas", { schema: z.array(MonedaOut) }),
    enabled: can(me, "monedas"),
    staleTime: 60_000,
  });
  const menu = useMenu(sucursalId, !can(me, "monedas"));
  const data = (directas.data ?? menu.data?.monedas)?.filter((m) => m.activa);
  return { data, isPending: data === undefined && (directas.isPending || menu.isPending) && (can(me, "monedas") || can(me, "productos")) };
}

export function principalDe(monedas: Moneda[] | undefined) {
  return monedas?.find((m) => m.es_principal);
}

export function useDivisionIguales(id: number, partes: number, enabled: boolean) {
  return useQuery({
    queryKey: ["division", id, "iguales", partes],
    queryFn: () => api(`/comandas/${id}/division`, { query: { partes }, schema: DivisionOut }),
    enabled,
  });
}

// ---------------------------------------------------------------- caché
/** Upsert de un resumen en la lista de abiertas (los eventos WS traen el resumen). */
export function upsertResumen(qc: QueryClient, r: ComandaResumen) {
  qc.setQueryData<ComandaResumen[]>(keys.abiertas(r.sucursal_id), (list) => {
    if (!list) return list;
    const rest = list.filter((c) => c.id !== r.id);
    return r.estado === "abierta" ? [r, ...rest].sort((a, b) => b.id - a.id) : rest;
  });
  // La mesa cambia de ocupada/libre: el plano se recalcula desde las abiertas, pero
  // comanda_abierta_id viene de /mesas
  void qc.invalidateQueries({ queryKey: keys.mesas(r.sucursal_id) });
}

/** Tras una mutación que devuelve la comanda completa: detalle + lista al día. */
export function applyComanda(qc: QueryClient, c: Comanda) {
  qc.setQueryData(keys.comanda(c.id), c);
  void qc.invalidateQueries({ queryKey: keys.abiertas(c.sucursal_id) });
}

export function notifyError(err: unknown) {
  const e = describeError(err);
  toast({ title: e.title, description: [e.description, ...(e.items ?? [])].filter(Boolean).join(" · "), tone: e.tone, duration: 8000 });
}

// ---------------------------------------------------------------- escrituras
type Body = Record<string, unknown> | undefined;

/** Mutación sobre una comanda que responde ComandaOut. */
export function useComandaAction<V>(id: number, build: (v: V) => { path: string; method?: "POST" | "PUT" | "PATCH" | "DELETE"; body?: Body }, opts?: {
  optimistic?: (c: Comanda, v: V) => Comanda;
  onSuccess?: (c: Comanda, v: V) => void;
  /** Si devuelve true, el error ya se mostró en la UI y no se notifica con toast. */
  onError?: (err: unknown, v: V) => boolean | void;
}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: V) => {
      const { path, method = "POST", body } = build(v);
      return api(`/comandas/${id}${path}`, { method, body, schema: ComandaOut });
    },
    onMutate: async (v) => {
      if (!opts?.optimistic) return undefined;
      await qc.cancelQueries({ queryKey: keys.comanda(id) });
      const prev = qc.getQueryData<Comanda>(keys.comanda(id));
      if (prev) qc.setQueryData(keys.comanda(id), opts.optimistic(prev, v));
      return { prev };
    },
    onError: (err, v, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.comanda(id), ctx.prev);
      if (!opts?.onError?.(err, v)) notifyError(err);
    },
    onSuccess: (c, v) => {
      applyComanda(qc, c);
      opts?.onSuccess?.(c, v);
    },
  });
}

export function useMoverMesa(sucursalId: number | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; pos_x: number | null; pos_y: number | null }) =>
      api(`/mesas/${v.id}`, { method: "PATCH", body: { pos_x: v.pos_x, pos_y: v.pos_y }, schema: MesaOut }),
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

export function useAbrirComanda() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { sucursal_id: number; mesa_id?: number | null; nombre_cliente?: string | null; cliente_id?: number | null }) =>
      api("/comandas", { method: "POST", body: v, schema: ComandaOut }),
    onSuccess: (c) => applyComanda(qc, c),
  });
}
