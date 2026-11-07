"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "@/components/ui/Toast";
import { chime, unlockAudio } from "@/features/cocina/chime";
import { chatKey } from "@/features/chat/queries";
import { ComandaResumenOut } from "@/lib/api/schemas";
import { useRealtime, useRealtimeStatus } from "@/lib/realtime/RealtimeProvider";
import { tituloComanda } from "./estado";
import { keys, upsertResumen } from "./queries";

const EVENTOS = [
  "comanda.creada",
  "comanda.actualizada",
  "comanda.items_cliente",
  "comanda.cerrada",
  "comanda.cancelada",
  "cocina.nuevos",
  "cocina.item_actualizado",
  "chat.mensaje",
];

/**
 * Mantiene al día, sin refetch, la lista de comandas abiertas: cada evento trae
 * el resumen de la comanda. El detalle abierto en pantalla se vuelve a pedir.
 */
export function ComandasLive() {
  const qc = useQueryClient();
  const router = useRouter();

  // El navegador solo deja sonar tras un gesto: el primer toque en el panel lo desbloquea
  useEffect(() => {
    const desbloquear = () => unlockAudio();
    window.addEventListener("pointerdown", desbloquear, { once: true });
    return () => window.removeEventListener("pointerdown", desbloquear);
  }, []);

  useRealtime(EVENTOS, (data, tipo) => {
    if (tipo === "chat.mensaje") {
      const m = data as { comanda_id?: number; autor?: string; mesa?: string | null; texto?: string };
      if (typeof m.comanda_id !== "number") return;
      void qc.invalidateQueries({ queryKey: chatKey(m.comanda_id) });
      if (m.autor === "cliente") {
        chime();
        toast({
          title: `${m.mesa ? (/^\d+$/.test(m.mesa) ? `Mesa ${m.mesa}` : m.mesa) : `Comanda #${m.comanda_id}`} escribió`,
          description: m.texto,
          action: { label: "Ver", onClick: () => router.push(`/panel/comandas/${m.comanda_id}`) },
          duration: 12_000,
        });
      }
      return;
    }
    const r = ComandaResumenOut.safeParse(data);
    if (!r.success) return;
    upsertResumen(qc, r.data);
    void qc.invalidateQueries({ queryKey: keys.comanda(r.data.id) });

    const ver = { label: "Ver", onClick: () => router.push(`/panel/comandas/${r.data.id}`) };
    if ((tipo === "comanda.creada" && r.data.origen === "qr") || tipo === "comanda.items_cliente") chime();
    if (tipo === "comanda.creada" && r.data.origen === "qr") {
      toast({ title: `Pedido por QR · ${tituloComanda(r.data)}`, description: "Espera tu aprobación para ir a cocina.", action: ver, duration: 12_000 });
    }
    if (tipo === "comanda.items_cliente") {
      toast({ title: `${tituloComanda(r.data)} pidió más platos`, description: "Están por aprobar.", action: ver, duration: 12_000 });
    }
  });

  // Tras una reconexión pudieron perderse eventos: se vuelve a pedir todo lo vivo
  const status = useRealtimeStatus();
  const prev = useRef(status);
  useEffect(() => {
    if (status === "en_vivo" && prev.current === "reconectando") {
      void qc.invalidateQueries({ queryKey: ["comandas"] });
      void qc.invalidateQueries({ queryKey: ["mesas"] });
      void qc.invalidateQueries({ queryKey: ["comanda"] });
    }
    prev.current = status;
  }, [status, qc]);

  return null;
}
