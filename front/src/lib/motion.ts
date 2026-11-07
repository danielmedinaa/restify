import type { Transition } from "motion/react";

/** Toques, switches, chips: ~180 ms, sin rebote visible. */
export const snappy: Transition = { type: "spring", stiffness: 520, damping: 38, mass: 0.8 };

/** Listas, layout, cambios de estado: ~300 ms. */
export const smooth: Transition = { type: "spring", stiffness: 300, damping: 32 };

/** Bottom sheets, modales, paneles laterales. */
export const sheet: Transition = { type: "spring", stiffness: 380, damping: 40, mass: 0.9 };

/** Respuesta física al tocar algo accionable. */
export const tap = { scale: 0.97 } as const;

/** Sustituto cuando el usuario pide menos movimiento. */
export const fade: Transition = { duration: 0.12, ease: "linear" };
