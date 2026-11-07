"use client";

import { useSyncExternalStore } from "react";

/**
 * Reloj compartido (un solo setInterval para todos los timers de la pantalla).
 * Devuelve null en el servidor y durante la hidratación: los relojes no
 * coinciden, así que nada que dependa de la hora debe ir en ese primer HTML.
 */
let now = 0;
let timer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!timer) {
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      listeners.forEach((l) => l());
    }, 1000);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

export function useNow(): number | null {
  return useSyncExternalStore(subscribe, () => now || Date.now(), () => null);
}
