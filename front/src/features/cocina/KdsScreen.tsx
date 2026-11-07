"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Maximize, Minimize, Printer, Volume2, VolumeX } from "lucide-react";
import { AnimatePresence } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StickyHeader } from "@/components/ui/StickyHeader";
import { can, useMe } from "@/features/auth/useMe";
import { LiveStatus } from "@/features/panel/LiveStatus";
import { SucursalPicker } from "@/features/panel/SucursalPicker";
import { SucursalProvider, useSucursal } from "@/features/panel/sucursal";
import { setUnauthorizedHandler } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { CocinaComanda, Me } from "@/lib/api/schemas";
import { TicketCocina, TicketPortal } from "@/features/caja/Ticket";
import { createStore } from "@/features/publico/stores";
import { RealtimeProvider, useRealtime } from "@/lib/realtime/RealtimeProvider";
import { chime, unlockAudio } from "./chime";
import { KdsCard } from "./KdsCard";
import { tableroKey, useEstaciones, useMarcar, useTablero } from "./queries";

const SONIDO_KEY = "rs_kds_sonido";
// Imprimir sola cada comanda nueva (sin diálogo si Chrome corre con --kiosk-printing)
const autoImprimirStore = createStore<boolean>("rs_kds_imprimir", false);
// Estación de esta pantalla: un id, null = todas, "auto" = la primera activa (aún sin elegir)
const estacionStore = createStore<number | null | "auto">("rs_kds_estacion", "auto");
// Los platos llegan a cocina por varios caminos (comanda creada ya enviada, platos
// agregados, aprobación de un pedido QR): se escucha todo lo que toca comandas.
const EVENTOS = [
  "cocina.nuevos",
  "cocina.item_actualizado",
  "comanda.creada",
  "comanda.actualizada",
  "comanda.cancelada",
  "comanda.cerrada",
];

export function KdsScreen({ initialSucursalId }: { initialSucursalId: number | null }) {
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();

  useEffect(() => {
    setUnauthorizedHandler(() => {
      qc.clear();
      router.replace("/login?motivo=expirada&next=%2Fcocina");
    });
    return () => setUnauthorizedHandler(null);
  }, [qc, router]);

  if (me.isPending) return <BoardSkeleton />;
  if (me.isError) return <Centro title={describeError(me.error).title} description="Recarga la pantalla para intentar de nuevo." />;
  if (!can(me.data, "cocina")) return <Centro title="Sin acceso" description="Tu rol no puede ver la cocina. Pídele acceso a un administrador." />;

  return (
    <SucursalProvider me={me.data} initialId={initialSucursalId}>
      <Tablero me={me.data} />
    </SucursalProvider>
  );
}

function Tablero({ me }: { me: Me }) {
  const qc = useQueryClient();
  const { actual } = useSucursal();
  const estaciones = useEstaciones();
  // Cada pantalla recuerda su estación: la de cocina no ve lo de barra. "auto" = la primera activa
  const guardada = estacionStore.use();
  const activas = estaciones.data?.filter((e) => e.activa) ?? [];
  const estacionId = guardada === null ? null : typeof guardada === "number" && activas.some((e) => e.id === guardada) ? guardada : (activas[0]?.id ?? null);
  const estacion = estaciones.data?.find((e) => e.id === estacionId) ?? null;
  const tablero = useTablero(actual?.id, estacionId);
  const marcar = useMarcar(actual?.id, estacionId);
  const sonido = useSonido();
  const pantallaCompleta = usePantallaCompleta();
  useWakeLock();

  const autoImprimir = autoImprimirStore.use();
  // Cola de tickets por imprimir: uno a la vez (el navegador imprime de a un documento)
  const [cola, setCola] = useState<CocinaComanda[]>([]);
  const imprimiendo = cola[0] ?? null;
  useEffect(() => {
    if (!imprimiendo) return;
    const listo = () => setCola((c) => c.slice(1));
    window.addEventListener("afterprint", listo, { once: true });
    const t = setTimeout(() => window.print(), 50); // deja montar el ticket antes de imprimir
    return () => {
      clearTimeout(t);
      window.removeEventListener("afterprint", listo);
    };
  }, [imprimiendo]);

  // Suena (y si se pidió, imprime) cuando aparece un plato que el tablero no había visto
  const vistos = useRef<Set<number> | null>(null);
  useEffect(() => {
    if (!tablero.data) return;
    const ids = tablero.data.flatMap((c) => c.items.map((i) => i.id));
    const previos = vistos.current;
    const hayNuevos = previos !== null && ids.some((id) => !previos.has(id));
    vistos.current = new Set([...(previos ?? []), ...ids]);
    if (hayNuevos && sonido.activo) chime();
    if (hayNuevos && autoImprimir && previos) {
      // Solo los platos nuevos de cada comanda: lo demás ya salió impreso antes
      const nuevas = tablero.data
        .map((c) => ({ ...c, items: c.items.filter((i) => !previos.has(i.id)) }))
        .filter((c) => c.items.length > 0);
      setCola((c) => [...c, ...nuevas]);
    }
  }, [tablero.data, sonido.activo, autoImprimir]);

  return (
    <RealtimeProvider sucursalId={actual?.id ?? null} app="cocina">
      <Eventos onEvento={() => void qc.invalidateQueries({ queryKey: ["cocina", "sucursal", actual?.id] })} />
      <StickyHeader>
        <div className="flex h-16 items-center gap-4 px-4 tablet:px-6">
          <h1 className="font-display text-display-s leading-none">{estacion?.nombre ?? "Preparación"}</h1>
          {estaciones.data && estaciones.data.length > 0 && (
            <select
              aria-label="Estación"
              value={estacionId ?? ""}
              onChange={(e) => {
                const elegida = e.target.value ? Number(e.target.value) : null;
                estacionStore.set(() => elegida);
                vistos.current = null; // al cambiar de estación no suena por platos que ya estaban
              }}
              className="h-10 rounded-control bg-wash px-3 text-base text-fg outline-none [&>option]:bg-overlay"
            >
              <option value="">Todas</option>
              {estaciones.data.filter((e) => e.activa).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nombre}
                </option>
              ))}
            </select>
          )}
          <SucursalPicker className="w-auto max-w-[220px]" />
          {tablero.data && (
            <span className="hidden text-base tabular text-fg-2 tablet:inline">
              {tablero.data.length} {tablero.data.length === 1 ? "comanda" : "comandas"} ·{" "}
              {tablero.data.reduce((n, c) => n + c.items.length, 0)} platos
            </span>
          )}
          <div className="ml-auto flex items-center gap-1">
            <LiveStatus className="mr-3 hidden tablet:inline" />
            <BotonIcono
              label={autoImprimir ? "Dejar de imprimir comandas nuevas" : "Imprimir comandas nuevas automáticamente"}
              onClick={() => autoImprimirStore.set((v) => !v)}
              activo={autoImprimir}
            >
              <Printer size={20} strokeWidth={1.5} className={autoImprimir ? "text-fg" : undefined} />
            </BotonIcono>
            <BotonIcono label={sonido.activo ? "Silenciar avisos" : "Activar sonido de pedidos nuevos"} onClick={sonido.alternar} activo={sonido.activo}>
              {sonido.activo ? <Volume2 size={20} strokeWidth={1.5} /> : <VolumeX size={20} strokeWidth={1.5} />}
            </BotonIcono>
            {pantallaCompleta.soportada && (
              <BotonIcono label={pantallaCompleta.activa ? "Salir de pantalla completa" : "Pantalla completa"} onClick={pantallaCompleta.alternar}>
                {pantallaCompleta.activa ? <Minimize size={20} strokeWidth={1.5} /> : <Maximize size={20} strokeWidth={1.5} />}
              </BotonIcono>
            )}
            {can(me, "comandas") && (
              <Link href="/panel" className="ml-2 rounded-control px-3 py-2 text-sm text-fg-2 hover:bg-wash hover:text-fg">
                Panel
              </Link>
            )}
          </div>
        </div>
      </StickyHeader>

      <main className="p-4 tablet:p-6">
        {tablero.isPending ? (
          <BoardSkeleton embedded />
        ) : tablero.isError ? (
          <Centro title={describeError(tablero.error).title} description="Reintentando…" />
        ) : tablero.data.length === 0 ? (
          <Centro title="Todo al día" description="No hay platos en cocina. Los nuevos aparecen aquí al instante." />
        ) : (
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr))]">
            <AnimatePresence mode="popLayout">
              {tablero.data.map((c) => (
                <KdsCard
                  key={c.comanda_id}
                  comanda={c}
                  puedeEditar={can(me, "cocina", "editar")}
                  onMarcar={(id, estado) => marcar.mutate({ id, estado })}
                  onImprimir={() => setCola((q) => [...q, c])}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </main>
      {imprimiendo && (
        <TicketPortal>
          <TicketCocina
            comandaId={imprimiendo.comanda_id}
            mesa={imprimiendo.mesa}
            nombreCliente={imprimiendo.nombre_cliente}
            notas={imprimiendo.notas}
            items={imprimiendo.items}
          />
        </TicketPortal>
      )}
    </RealtimeProvider>
  );
}

function Eventos({ onEvento }: { onEvento: () => void }) {
  useRealtime(EVENTOS, () => onEvento());
  return null;
}

/* ------------------------------------------------------------------ hooks del dispositivo */
// Preferencia de sonido en localStorage, leída sin desfase entre servidor y cliente
const sonidoListeners = new Set<() => void>();
function leerSonido(): boolean {
  try {
    return localStorage.getItem(SONIDO_KEY) !== "off";
  } catch {
    return true;
  }
}
function guardarSonido(on: boolean) {
  try {
    localStorage.setItem(SONIDO_KEY, on ? "on" : "off");
  } catch {}
  sonidoListeners.forEach((l) => l());
}
const subscribeSonido = (l: () => void) => (sonidoListeners.add(l), () => sonidoListeners.delete(l));

/**
 * El sonido arranca activo, pero el navegador solo deja sonar tras un gesto: el
 * primer toque en la pantalla lo desbloquea.
 */
function useSonido() {
  const preferido = useSyncExternalStore(subscribeSonido, leerSonido, () => true);
  const [desbloqueado, setDesbloqueado] = useState(false);

  useEffect(() => {
    const desbloquear = () => {
      if (unlockAudio()) setDesbloqueado(true);
    };
    window.addEventListener("pointerdown", desbloquear, { once: true });
    return () => window.removeEventListener("pointerdown", desbloquear);
  }, []);

  const alternar = useCallback(() => {
    unlockAudio();
    setDesbloqueado(true);
    const next = !leerSonido();
    guardarSonido(next);
    if (next) chime();
  }, []);

  return { activo: preferido && desbloqueado, alternar };
}

const noop = () => () => {};
function usePantallaCompleta() {
  const [activa, setActiva] = useState(false);
  const soportada = useSyncExternalStore(noop, () => !!document.documentElement.requestFullscreen, () => false);
  useEffect(() => {
    const onChange = () => setActiva(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const alternar = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen().catch(() => null);
  };
  return { activa, soportada, alternar };
}

/** Mantiene la pantalla encendida mientras la cocina está abierta (si el navegador lo permite). */
function useWakeLock() {
  useEffect(() => {
    let lock: WakeLockSentinel | null = null;
    const pedir = async () => {
      try {
        if (document.visibilityState === "visible" && "wakeLock" in navigator) lock = await navigator.wakeLock.request("screen");
      } catch {
        lock = null;
      }
    };
    void pedir();
    document.addEventListener("visibilitychange", pedir);
    return () => {
      document.removeEventListener("visibilitychange", pedir);
      void lock?.release();
    };
  }, []);
}

/* ------------------------------------------------------------------ piezas */
function BotonIcono({ label, onClick, activo, children }: { label: string; onClick: () => void; activo?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={activo}
      title={label}
      className="grid size-11 place-items-center rounded-control text-fg-2 transition-colors hover:bg-wash hover:text-fg"
    >
      {children}
    </button>
  );
}

function Centro({ title, description }: { title: string; description: string }) {
  return (
    <div className="grid min-h-[70dvh] place-items-center px-6">
      <EmptyState title={title} description={description} />
    </div>
  );
}

function BoardSkeleton({ embedded }: { embedded?: boolean }) {
  return (
    <div className={embedded ? "" : "p-6"} role="status" aria-busy>
      <span className="sr-only">Cargando cocina</span>
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr))]">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex flex-col gap-5 rounded-sheet bg-sunken p-6">
            <Skeleton className="h-10 w-24" />
            <Skeleton className="h-10 w-40" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
