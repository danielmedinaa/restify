"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { AlertaSeguridadOut, Pagina } from "@/lib/api/schemas";
import { useRealtime } from "@/lib/realtime/RealtimeProvider";

const KEY = ["seguridad", "alertas", "pendientes"];
const hora = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" });

/** Alarma corta y grave (Web Audio): dos pulsos, sin archivos. */
function alarma() {
  try {
    const ctx = new AudioContext();
    [0, 0.28].forEach((t) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "square";
      o.frequency.value = 440;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + t);
      g.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.22);
      o.connect(g).connect(ctx.destination);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + 0.24);
    });
  } catch {
    // sin audio (navegador sin gesto previo): la alerta visual basta
  }
}

/**
 * Alerta de posible peligro para el superadmin: banda roja fija sobre todo el panel mientras
 * haya alertas sin revisar, y un modal imposible de ignorar si alguna es crítica.
 * Llega en tiempo real (evento seguridad.alerta) y se consulta cada 30 s por si el socket cae.
 */
export function AlertaSeguridad() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const activo = !!me?.es_superadmin;
  const [vistaCritica, setVistaCritica] = useState<number | null>(null);
  const pendientes = useQuery({
    queryKey: KEY,
    queryFn: () => api("/seguridad/alertas", { query: { pendientes: true, limite: 5 }, schema: Pagina(AlertaSeguridadOut) }),
    enabled: activo,
    refetchInterval: 30_000,
  });
  useRealtime("seguridad.alerta", () => {
    alarma();
    navigator.vibrate?.([200, 100, 200]);
    void qc.invalidateQueries({ queryKey: KEY });
  });
  const revisar = useMutation({
    mutationFn: () => api("/seguridad/alertas/revisar", { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["seguridad"] });
      setVistaCritica(null);
    },
  });

  const total = pendientes.data?.total ?? 0;
  const ultima = pendientes.data?.items[0];
  const critica = pendientes.data?.items.find((a) => a.severidad === "critica");
  if (!activo) return null;

  return (
    <>
      <AnimatePresence>
        {total > 0 && ultima && (
          <motion.div
            role="alert"
            initial={{ y: -80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -80, opacity: 0 }}
            className="sticky top-0 z-[70] flex flex-wrap items-center gap-x-6 gap-y-2 bg-[#a3212b] px-4 py-3 text-white shadow-[0_10px_40px_-10px_rgb(163_33_43/0.8)] tablet:px-8"
          >
            <motion.span animate={{ scale: [1, 1.18, 1] }} transition={{ duration: 1.2, repeat: Infinity }} className="grid size-9 shrink-0 place-items-center rounded-full bg-white/15">
              <ShieldAlert size={20} strokeWidth={2} aria-hidden />
            </motion.span>
            <div className="flex min-w-0 flex-1 flex-col">
              <p className="font-semibold uppercase tracking-[0.06em]">
                Posible peligro de seguridad{total > 1 && ` · ${total} alertas`}
              </p>
              <p className="truncate text-sm text-white/85">
                {ultima.titulo}: {ultima.detalle} · {hora.format(new Date(ultima.created_at))}
              </p>
            </div>
            <div className="flex gap-2">
              <Link href="/panel/admin/seguridad" className="inline-flex h-9 items-center rounded-control bg-white px-4 text-sm font-semibold text-[#a3212b]">
                Ver detalles
              </Link>
              <button type="button" onClick={() => revisar.mutate()} className="h-9 rounded-control px-3 text-sm text-white/90 ring-1 ring-inset ring-white/40 hover:bg-white/10">
                Marcar revisadas
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {critica && vistaCritica !== critica.id && (
          <motion.div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="alerta-critica-t"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] grid place-items-center bg-[rgb(40_5_8/0.82)] p-4 backdrop-blur-md"
          >
            <motion.div
              initial={{ scale: 0.92, y: 12 }}
              animate={{ scale: 1, y: 0 }}
              className="flex w-full max-w-lg flex-col gap-5 rounded-sheet bg-[#1f0a0c] p-8 text-white ring-2 ring-[#e0444f] shadow-[0_0_80px_-10px_rgb(224_68_79/0.7)]"
            >
              <motion.span animate={{ opacity: [1, 0.4, 1] }} transition={{ duration: 1, repeat: Infinity }} className="flex items-center gap-3 text-sm font-semibold uppercase tracking-[0.1em] text-[#ff7a83]">
                <ShieldAlert size={22} strokeWidth={2} aria-hidden /> Alerta crítica
              </motion.span>
              <h2 id="alerta-critica-t" className="font-display text-display-m leading-none">
                {critica.titulo}
              </h2>
              <p className="text-lead text-white/85">{critica.detalle}</p>
              <p className="text-sm text-white/60">
                {hora.format(new Date(critica.created_at))}
                {critica.ip && ` · IP ${critica.ip}`}. Si no fuiste tú, cambia la contraseña de ese usuario y revisa la bitácora.
              </p>
              <div className="flex flex-wrap justify-end gap-2 pt-2">
                <Button variant="ghost" className="text-white/80 hover:bg-white/10" onClick={() => setVistaCritica(critica.id)}>
                  Lo veo luego
                </Button>
                <Link href="/panel/admin/seguridad" onClick={() => setVistaCritica(critica.id)} className="inline-flex h-10 items-center rounded-control bg-[#e0444f] px-4 font-medium text-white hover:bg-[#c93a44]">
                  Revisar ahora
                </Link>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
