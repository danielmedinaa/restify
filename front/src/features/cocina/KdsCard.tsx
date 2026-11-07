"use client";

import { Printer } from "lucide-react";

import { AnimatePresence, motion, useMotionValue, useTransform, type PanInfo } from "motion/react";
import { Timer } from "@/components/ui/Timer";
import { tituloComanda } from "@/features/comandas/estado";
import type { CocinaComanda } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { smooth, snappy } from "@/lib/motion";

type Plato = CocinaComanda["items"][number];
type Marcar = (id: number, estado: "preparando" | "listo") => void;

const SWIPE = 110;

function vibrar() {
  if (typeof navigator !== "undefined" && "vibrate" in navigator) navigator.vibrate(12);
}

/** Tarjeta de una comanda en cocina. El timer cuenta desde el plato más antiguo. */
export function KdsCard({ comanda, onMarcar, puedeEditar, onImprimir }: { comanda: CocinaComanda; onMarcar: Marcar; puedeEditar: boolean; onImprimir?: () => void }) {
  const desde = comanda.items.map((i) => i.enviado_en).filter((d): d is string => !!d).sort()[0];
  const titulo = tituloComanda({ mesa: comanda.mesa, nombre_cliente: comanda.nombre_cliente, id: comanda.comanda_id });
  return (
    <motion.article
      layout
      transition={smooth}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      aria-label={`${titulo}, ${comanda.items.length} platos`}
      className="grain flex flex-col gap-5 overflow-hidden rounded-sheet bg-sunken p-6"
    >
      {desde && <Timer since={desde} size="l" />}
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-display-m leading-none">{titulo}</h2>
        <span className="flex items-center gap-2 text-base tabular text-fg-3">
          #{comanda.comanda_id}
          {onImprimir && (
            <button type="button" onClick={onImprimir} aria-label={`Imprimir comanda ${comanda.comanda_id}`} title="Imprimir comanda" className="grid size-9 place-items-center rounded-full hover:bg-wash hover:text-fg">
              <Printer size={16} strokeWidth={1.5} />
            </button>
          )}
        </span>
      </header>
      {comanda.mesa && comanda.nombre_cliente && <p className="-mt-3 text-base text-fg-2">{comanda.nombre_cliente}</p>}
      {comanda.notas && <p className="border-l-2 border-warn pl-3 text-lead text-fg">{comanda.notas}</p>}
      <ul className="flex flex-col">
        <AnimatePresence initial={false}>
          {comanda.items.map((i) => (
            <PlatoRow key={i.id} plato={i} onMarcar={onMarcar} puedeEditar={puedeEditar} />
          ))}
        </AnimatePresence>
      </ul>
    </motion.article>
  );
}

function PlatoRow({ plato, onMarcar, puedeEditar }: { plato: Plato; onMarcar: Marcar; puedeEditar: boolean }) {
  const x = useMotionValue(0);
  // Al deslizar aparece "Listo" detrás y la fila se tiñe de salvia
  const fondo = useTransform(x, [0, SWIPE], ["rgb(147 166 142 / 0)", "rgb(147 166 142 / 0.35)"]);
  const preparando = plato.estado === "preparando";
  const siguiente = preparando ? "listo" : "preparando";

  function tocar() {
    if (!puedeEditar) return;
    vibrar();
    onMarcar(plato.id, siguiente);
  }

  function soltar(_: unknown, info: PanInfo) {
    if (info.offset.x > SWIPE || info.velocity.x > 800) {
      vibrar();
      onMarcar(plato.id, "listo");
    }
  }

  return (
    <motion.li
      layout
      transition={smooth}
      exit={{ x: 220, opacity: 0, backgroundColor: "rgb(147 166 142 / 0.35)", transition: { duration: 0.28 } }}
      style={{ backgroundColor: fondo }}
      className="relative -mx-3 rounded-control"
    >
      <span aria-hidden className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-base font-medium text-ok">
        Listo
      </span>
      <motion.button
        type="button"
        onClick={tocar}
        disabled={!puedeEditar}
        drag={puedeEditar ? "x" : false}
        dragConstraints={{ left: 0, right: 0 }}
        dragElastic={{ left: 0, right: 0.9 }}
        onDragEnd={soltar}
        style={{ x }}
        whileTap={{ scale: 0.985 }}
        transition={snappy}
        aria-label={`${plato.nombre}: ${preparando ? "en preparación, toca para marcar listo" : "nuevo, toca para empezar a preparar"}`}
        className={cn(
          "relative flex min-h-[72px] w-full touch-pan-y items-center justify-between gap-4 rounded-control border-t border-line bg-sunken px-3 py-3 text-left",
          "disabled:cursor-default",
        )}
      >
        <span className="flex min-w-0 flex-col gap-1">
          <span className={cn("text-[1.5rem] font-medium leading-tight", preparando ? "text-fg" : "text-fg-2")}>{plato.nombre}</span>
          {plato.notas && <span className="text-lead text-warn">{plato.notas}</span>}
        </span>
        <span
          className={cn(
            "shrink-0 rounded-full px-3 py-1.5 text-sm font-medium",
            preparando ? "bg-paper text-ink" : "border border-line-strong text-fg-2",
          )}
        >
          {preparando ? "Preparando" : "Nuevo"}
        </span>
      </motion.button>
    </motion.li>
  );
}
