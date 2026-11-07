"use client";

import { StatusDot } from "@/components/ui/Status";
import { useRealtimeStatus } from "@/lib/realtime/RealtimeProvider";

const LABEL = { en_vivo: "En vivo", conectando: "Conectando…", reconectando: "Reconectando…", detenido: "Sin tiempo real" } as const;
const TONE = { en_vivo: "ok", conectando: "muted", reconectando: "warn", detenido: "muted" } as const;

export function LiveStatus({ className }: { className?: string }) {
  const status = useRealtimeStatus();
  return (
    <span role="status" className={className}>
      <StatusDot tone={TONE[status]}>{LABEL[status]}</StatusDot>
    </span>
  );
}
