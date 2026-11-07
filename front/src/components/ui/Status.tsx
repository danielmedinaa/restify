"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/cn";
import { smooth } from "@/lib/motion";

export type Tone = "neutral" | "ok" | "warn" | "err" | "muted";

const dot: Record<Tone, string> = {
  neutral: "bg-paper",
  ok: "bg-ok",
  warn: "bg-warn",
  err: "bg-err",
  muted: "bg-fg-4",
};

/** Punto + palabra. El color informa, el texto siempre se lee en fg. */
export function StatusDot({ tone = "neutral", children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm text-fg-2", className)}>
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", dot[tone])} />
      {children}
    </span>
  );
}

/** Línea fina que se llena: progreso de platos de una mesa o comanda. */
export function ProgressLine({
  value,
  max,
  tone = "neutral",
  label,
  className,
}: {
  value: number;
  max: number;
  tone?: Tone;
  label: string;
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className={cn("h-px w-full bg-line", className)}
    >
      <motion.div
        className={cn("h-full origin-left", dot[tone])}
        initial={false}
        animate={{ width: `${pct}%` }}
        transition={smooth}
      />
    </div>
  );
}
