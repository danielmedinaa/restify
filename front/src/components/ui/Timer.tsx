"use client";

import { cn } from "@/lib/cn";
import { useNow } from "@/lib/useNow";

export interface TimerProps {
  /** ISO del momento en que arrancó (p. ej. enviado_en). */
  since: string;
  /** Minutos en que empieza a tensarse y en que llega al máximo. */
  calmMinutes?: number;
  tenseMinutes?: number;
  /** "l" para leerse a distancia (pantalla de cocina). */
  size?: "s" | "l";
  className?: string;
}

/** 0 = tranquilo, 1 = al límite. */
export function tension(elapsedMs: number, calmMinutes: number, tenseMinutes: number) {
  const min = elapsedMs / 60000;
  if (min <= calmMinutes) return 0;
  return Math.min(1, (min - calmMinutes) / Math.max(1, tenseMinutes - calmMinutes));
}

function format(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/**
 * El tiempo se tensa sin semáforo: la línea superior engrosa de 1 a 3 px y vira
 * de blanco a ocre de forma continua. Expone --tension para que la tarjeta reaccione.
 */
export function Timer({ since, calmMinutes = 8, tenseMinutes = 15, size = "s", className }: TimerProps) {
  const now = useNow();
  const elapsed = now === null ? 0 : now - new Date(since).getTime();
  const t = tension(elapsed, calmMinutes, tenseMinutes);
  const minutes = Math.floor(elapsed / 60000);
  return (
    <div className={cn("flex flex-col gap-2", className)} style={{ "--tension": t } as React.CSSProperties}>
      <span
        aria-hidden
        className="block w-full transition-[height,background-color] duration-700"
        style={{
          height: `${1 + t * 2}px`,
          backgroundColor: `color-mix(in oklab, var(--color-warn) ${Math.round(t * 100)}%, var(--color-line-strong))`,
        }}
      />
      <time
        dateTime={now === null ? undefined : since}
        className={cn("font-display tabular transition-colors duration-700", size === "l" ? "text-display-m" : "text-display-s")}
        style={{ color: `color-mix(in oklab, var(--color-warn) ${Math.round(t * 70)}%, var(--color-fg))` }}
      >
        {now === null ? "--:--" : format(elapsed)}
      </time>
      {now !== null && <span className="sr-only">Hace {minutes} minutos</span>}
    </div>
  );
}
