"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { X } from "lucide-react";
import { useSyncExternalStore } from "react";
import { cn } from "@/lib/cn";
import { fade, smooth } from "@/lib/motion";
import type { Tone } from "./Status";

export interface ToastData {
  id: number;
  title: string;
  description?: string;
  tone?: Tone;
  /** ms; 0 = no se cierra solo. */
  duration?: number;
  action?: { label: string; onClick: () => void };
}

let toasts: ToastData[] = [];
let seq = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function dismiss(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function toast(data: Omit<ToastData, "id">) {
  const id = ++seq;
  toasts = [...toasts.slice(-3), { duration: 5000, tone: "neutral", ...data, id }];
  emit();
  const duration = data.duration ?? 5000;
  if (duration > 0) setTimeout(() => dismiss(id), duration);
  return id;
}

const subscribe = (l: () => void) => (listeners.add(l), () => listeners.delete(l));
const EMPTY: ToastData[] = [];

const bar: Record<Tone, string> = {
  neutral: "bg-paper",
  ok: "bg-ok",
  warn: "bg-warn",
  err: "bg-err",
  muted: "bg-fg-4",
};

export function Toaster() {
  const list = useSyncExternalStore(subscribe, () => toasts, () => EMPTY);
  const reduce = useReducedMotion();
  return (
    <section
      aria-label="Notificaciones"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2"
    >
      <AnimatePresence initial={false}>
        {list.map((t) => (
          <motion.div
            key={t.id}
            layout={!reduce}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, x: 24 }}
            transition={reduce ? fade : smooth}
            role={t.tone === "err" ? "alert" : "status"}
            className="pointer-events-auto relative flex gap-3 overflow-hidden rounded-control bg-overlay/90 py-3.5 pl-4 pr-2 shadow-float backdrop-blur-xl"
          >
            <span aria-hidden className={cn("w-0.5 shrink-0 rounded-full", bar[t.tone ?? "neutral"])} />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <p className="text-base font-medium text-fg">{t.title}</p>
              {t.description && <p className="text-sm text-fg-2">{t.description}</p>}
            </div>
            {t.action && (
              <button
                type="button"
                onClick={() => {
                  t.action?.onClick();
                  dismiss(t.id);
                }}
                className="shrink-0 self-center rounded-md px-2.5 py-1.5 text-sm font-medium text-fg hover:bg-wash"
              >
                {t.action.label}
              </button>
            )}
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Descartar"
              className="grid size-8 shrink-0 place-items-center rounded-md text-fg-3 hover:bg-wash hover:text-fg"
            >
              <X size={16} strokeWidth={1.5} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </section>
  );
}
