"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { StaffSocket, type SocketStatus, type StaffEvent } from "./staffSocket";

type Handler = (data: unknown, tipo: string) => void;

interface RealtimeCtx {
  status: SocketStatus;
  subscribe: (tipos: string[], handler: Handler) => () => void;
}

const Ctx = createContext<RealtimeCtx | null>(null);

export function RealtimeProvider({
  sucursalId,
  app = "panel",
  children,
}: {
  sucursalId: number | null;
  app?: "panel" | "cocina";
  children: React.ReactNode;
}) {
  const [status, setStatus] = useState<SocketStatus>("detenido");
  const handlers = useRef(new Map<string, Set<Handler>>());
  const [value] = useState<Omit<RealtimeCtx, "status">>(() => ({
    subscribe: (tipos, handler) => {
      for (const t of tipos) {
        if (!handlers.current.has(t)) handlers.current.set(t, new Set());
        handlers.current.get(t)!.add(handler);
      }
      return () => tipos.forEach((t) => handlers.current.get(t)?.delete(handler));
    },
  }));

  useEffect(() => {
    if (sucursalId == null) return;
    const socket = new StaffSocket({
      sucursalId,
      app,
      onStatus: setStatus,
      onEvent: (e: StaffEvent) => {
        handlers.current.get(e.tipo)?.forEach((h) => h(e.data, e.tipo));
        handlers.current.get("*")?.forEach((h) => h(e.data, e.tipo));
      },
    });
    socket.start();
    return () => socket.stop();
  }, [sucursalId, app]);

  return <Ctx.Provider value={{ status, subscribe: value.subscribe }}>{children}</Ctx.Provider>;
}

export function useRealtimeStatus(): SocketStatus {
  return useContext(Ctx)?.status ?? "detenido";
}

/** Suscribe un handler a uno o varios tipos de evento ("*" = todos). */
export function useRealtime(tipos: string | string[], handler: Handler) {
  const subscribe = useContext(Ctx)?.subscribe;
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  const key = Array.isArray(tipos) ? tipos.join("|") : tipos;
  useEffect(() => {
    if (!subscribe) return;
    return subscribe(key.split("|"), (d, t) => ref.current(d, t));
  }, [subscribe, key]);
}
