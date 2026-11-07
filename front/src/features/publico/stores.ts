"use client";

import { useSyncExternalStore } from "react";

/**
 * Estado del cliente que vive en su teléfono (localStorage): carrito por mesa,
 * moneda elegida y pedidos hechos desde este dispositivo. Se lee con
 * useSyncExternalStore para que el HTML del servidor (vacío) y el del cliente
 * no choquen al hidratar.
 */
export function createStore<T>(key: string, fallback: T) {
  const listeners = new Set<() => void>();
  let cache: { raw: string | null; value: T } | null = null;

  function read(): T {
    let raw: string | null = null;
    try {
      raw = localStorage.getItem(key);
    } catch {}
    if (cache && cache.raw === raw) return cache.value;
    let value = fallback;
    try {
      if (raw) value = JSON.parse(raw) as T;
    } catch {}
    cache = { raw, value };
    return value;
  }

  function write(next: T) {
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      cache = { raw: JSON.stringify(next), value: next };
    }
    listeners.forEach((l) => l());
  }

  function subscribe(l: () => void) {
    listeners.add(l);
    const onStorage = (e: StorageEvent) => e.key === key && l();
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(l);
      window.removeEventListener("storage", onStorage);
    };
  }

  return {
    use: () => useSyncExternalStore(subscribe, read, () => fallback),
    get: read,
    set: (fn: (prev: T) => T) => write(fn(read())),
  };
}

// ---------------------------------------------------------------- carrito
export interface LineaCarrito {
  producto_id: number;
  cantidad: number;
  notas: string;
  /** Insumos que el cliente quita del plato (ids). Ausente en carritos viejos. */
  sin?: number[];
}

const carritos = new Map<string, ReturnType<typeof createStore<LineaCarrito[]>>>();
const VACIO: LineaCarrito[] = [];

export function carritoStore(scope: string) {
  let s = carritos.get(scope);
  if (!s) {
    s = createStore<LineaCarrito[]>(`rs_carrito:${scope}`, VACIO);
    carritos.set(scope, s);
  }
  return s;
}

// ---------------------------------------------------------------- moneda elegida
export const monedaStore = createStore<string | null>("rs_moneda", null);

// ---------------------------------------------------------------- pedidos de este teléfono
/** qr_token -> tracking_token del último pedido hecho desde este dispositivo. */
export const misPedidosStore = createStore<Record<string, string>>("rs_mis_pedidos", {});
