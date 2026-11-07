"use client";

import { wsBase } from "@/lib/realtime/wsBase";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { chatPublicoKey } from "@/features/chat/queries";
import { api } from "@/lib/api/client";
import { MenuOut, MesaPublicaOut, PedidoPublicoOut, type PedidoPublico } from "@/lib/api/schemas";

export const pedidoKey = (tracking: string) => ["publico", "pedido", tracking] as const;

export function useMesaPublica(qr: string) {
  return useQuery({
    queryKey: ["publico", "mesa", qr],
    queryFn: () => api(`/public/mesas/${qr}`, { app: "public", schema: MesaPublicaOut }),
    retry: false,
    staleTime: 20_000,
  });
}

export function useMenuSucursal(sucursalId: number | undefined, enabled = true) {
  return useQuery({
    queryKey: ["publico", "menu", sucursalId],
    queryFn: () => api(`/public/sucursales/${sucursalId}/menu`, { app: "public", schema: MenuOut }),
    enabled: enabled && sucursalId != null,
    retry: false,
    staleTime: 20_000,
  });
}

export function usePedido(tracking: string) {
  return useQuery({
    queryKey: pedidoKey(tracking),
    queryFn: () => api(`/public/pedidos/${tracking}`, { app: "public", schema: PedidoPublicoOut }),
    retry: false,
  });
}

export type ConexionPedido = "conectando" | "en_vivo" | "reconectando";

/**
 * Seguimiento en vivo: /ws/pedidos/{tracking} manda el pedido completo en cada
 * cambio (y al conectar). Reconexión con backoff; no necesita ticket.
 */
export function usePedidoLive(tracking: string, activo: boolean): ConexionPedido {
  const qc = useQueryClient();
  const [estado, setEstado] = useState<ConexionPedido>("conectando");

  useEffect(() => {
    const base = wsBase();
    if (!activo || !base) return;
    let ws: WebSocket | null = null;
    let intento = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cerrado = false;

    const conectar = () => {
      ws = new WebSocket(`${base.replace(/\/$/, "")}/ws/pedidos/${encodeURIComponent(tracking)}`);
      ws.onmessage = (m) => {
        try {
          const ev = JSON.parse(String(m.data)) as { tipo: string; data: unknown };
          if (ev.tipo === "chat.mensaje") {
            void qc.invalidateQueries({ queryKey: chatPublicoKey(tracking) });
            return;
          }
          if (ev.tipo !== "pedido.actualizado") return;
          const p = PedidoPublicoOut.safeParse(ev.data);
          if (p.success) {
            qc.setQueryData<PedidoPublico>(pedidoKey(tracking), p.data);
            intento = 0;
            setEstado("en_vivo");
          }
        } catch {}
      };
      ws.onclose = (e) => {
        if (cerrado || e.code === 1008) return; // 1008: el pedido no existe
        setEstado("reconectando");
        const delay = Math.min(30_000, 1000 * 2 ** intento++);
        timer = setTimeout(conectar, delay / 2 + Math.random() * (delay / 2));
      };
    };
    conectar();
    const online = () => {
      if (ws?.readyState === WebSocket.OPEN) return;
      if (timer) clearTimeout(timer);
      intento = 0;
      conectar();
    };
    window.addEventListener("online", online);
    return () => {
      cerrado = true;
      window.removeEventListener("online", online);
      if (timer) clearTimeout(timer);
      ws?.close(1000);
    };
  }, [tracking, activo, qc]);

  return estado;
}
