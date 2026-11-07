"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "@/lib/api/client";
import { MensajeOut } from "@/lib/api/schemas";
import { notifyError } from "@/features/comandas/queries";

export const chatKey = (comandaId: number) => ["chat", comandaId] as const;
export const chatPublicoKey = (tracking: string) => ["publico", "chat", tracking] as const;

const Lista = z.array(MensajeOut);

/** Chat visto desde caja. Los mensajes nuevos llegan por tiempo real (ComandasLive invalida la clave). */
export function useChatStaff(comandaId: number) {
  const qc = useQueryClient();
  const lista = useQuery({ queryKey: chatKey(comandaId), queryFn: () => api(`/comandas/${comandaId}/mensajes`, { schema: Lista }) });
  const enviar = useMutation({
    mutationFn: (texto: string) => api(`/comandas/${comandaId}/mensajes`, { method: "POST", body: { texto }, schema: MensajeOut }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: chatKey(comandaId) }),
    onError: notifyError,
  });
  return { lista, enviar };
}

/** Chat visto desde la mesa. usePedidoLive invalida la clave cuando llega un mensaje. */
export function useChatPublico(tracking: string) {
  const qc = useQueryClient();
  const lista = useQuery({
    queryKey: chatPublicoKey(tracking),
    queryFn: () => api(`/public/pedidos/${tracking}/mensajes`, { app: "public", schema: Lista }),
    retry: false,
  });
  const enviar = useMutation({
    mutationFn: (texto: string) => api(`/public/pedidos/${tracking}/mensajes`, { app: "public", method: "POST", body: { texto }, schema: MensajeOut }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: chatPublicoKey(tracking) }),
  });
  return { lista, enviar };
}
