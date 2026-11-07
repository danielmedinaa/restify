"use client";

import { motion, useMotionValue, type PanInfo } from "motion/react";
import Link from "next/link";
import { useRef } from "react";
import { Money } from "@/components/ui/Money";
import { ProgressLine, StatusDot } from "@/components/ui/Status";
import { ESTADO_SALA, estadoSala, minutosDesde, progreso, type EstadoSala } from "@/features/comandas/estado";
import type { ComandaResumen, Mesa } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { isPositive } from "@/lib/money";
import { smooth, tap } from "@/lib/motion";
import { useNow } from "@/lib/useNow";

/** Columnas del plano. Cada mesa ocupa ancho × alto celdas. */
export const COLS = 12;
/** Alto de cada fila en px. */
const FILA = 88;

export interface Celda {
  x: number;
  y: number;
}

export function ubicada(m: Mesa): m is Mesa & { pos_x: number; pos_y: number } {
  return m.pos_x != null && m.pos_y != null;
}

function choca(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

/** ¿Cabe la mesa en esa celda sin pisar a otra (ni salirse del plano)? */
export function cabe(mesas: Mesa[], mesa: Mesa, x: number, y: number): boolean {
  if (x < 0 || y < 0 || x + mesa.ancho > COLS) return false;
  const r = { x, y, w: mesa.ancho, h: mesa.alto };
  return !mesas.some((o) => o.id !== mesa.id && ubicada(o) && choca(r, { x: o.pos_x, y: o.pos_y, w: o.ancho, h: o.alto }));
}

/** Primer hueco libre recorriendo el plano de arriba abajo. */
export function huecoLibre(mesas: Mesa[], mesa: Mesa): Celda {
  for (let y = 0; ; y++) for (let x = 0; x + mesa.ancho <= COLS; x++) if (cabe(mesas, mesa, x, y)) return { x, y };
}

interface PlanoProps {
  /** Mesas de la zona visible (ya filtradas) y las que no tienen lugar en el plano. */
  mesas: Mesa[];
  todas: Mesa[];
  comandas: Map<number, ComandaResumen>;
  editando: boolean;
  /** Modo unir: tocar una mesa la selecciona. */
  uniendo: boolean;
  seleccion: number[];
  seleccionada: number | null;
  onSeleccionar: (mesa: Mesa) => void;
  onMover: (mesa: Mesa, celda: Celda) => void;
  onAbrirLibre: (mesa: Mesa) => void;
}

/**
 * Plano de la sala: grilla de 12 columnas donde cada mesa tiene su tamaño y forma.
 * En edición se arrastra con snap a la celda (sin pisar a otra); en uso, tocar abre la comanda.
 * En pantallas chicas el plano se vuelve una lista, que es más cómoda con el pulgar.
 */
export function Plano({ mesas, todas, comandas, editando, uniendo, seleccion, seleccionada, onSeleccionar, onMover, onAbrirLibre }: PlanoProps) {
  const gridRef = useRef<HTMLUListElement>(null);
  const colocadas = mesas.filter(ubicada);
  const filas = Math.max(4, ...colocadas.map((m) => m.pos_y + m.alto)) + (editando ? 2 : 0);

  const tile = (m: Mesa, enGrilla: boolean) => (
    <MesaTile
      key={m.id}
      mesa={m}
      todas={todas}
      comanda={comandas.get(m.unida_a_id ?? m.id)}
      editando={editando}
      uniendo={uniendo}
      marcada={seleccion.includes(m.id)}
      orden={seleccion.indexOf(m.id)}
      activa={seleccionada === m.id}
      enGrilla={enGrilla}
      gridRef={gridRef}
      onSeleccionar={() => onSeleccionar(m)}
      onDrop={(celda) => onMover(m, celda)}
      onAbrirLibre={() => onAbrirLibre(m)}
    />
  );

  const lista = [...colocadas].sort((a, b) => a.pos_y - b.pos_y || a.pos_x - b.pos_x);
  const sueltas = mesas.filter((m) => !ubicada(m));

  return (
    <>
      {/* Lista en móvil */}
      <ul className={cn("grid grid-cols-2 gap-3 tablet:hidden")}>{[...lista, ...sueltas].map((m) => tile(m, false))}</ul>
      {/* Plano en tablet y escritorio */}
      <ul
        ref={gridRef}
        className="relative hidden rounded-sheet bg-sunken/60 p-2 ring-1 ring-inset ring-line tablet:grid"
        style={{
          backgroundImage: "radial-gradient(var(--color-line) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
          gridTemplateColumns: `repeat(${COLS}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${filas}, ${FILA}px)`,
          ...(editando
            ? {
                backgroundImage:
                  "linear-gradient(to right, var(--color-line) 1px, transparent 1px), linear-gradient(to bottom, var(--color-line) 1px, transparent 1px)",
                backgroundSize: `calc((100% - 16px) / ${COLS}) ${FILA}px`,
                backgroundPosition: "8px 8px",
              }
            : {}),
        }}
      >
        {colocadas.map((m) => tile(m, true))}
      </ul>
      {sueltas.length > 0 && !editando && (
        <div className="mt-8 hidden flex-col gap-3 tablet:flex">
          <span className="eyebrow">Sin ubicar en el plano</span>
          <ul className="grid grid-cols-4 gap-3">{sueltas.map((m) => tile(m, false))}</ul>
        </div>
      )}
    </>
  );
}

/** Tinte de cada estado. Libre: solo el contorno, para que el plano se lea. */
const SUPERFICIE: Record<EstadoSala | "libre", string> = {
  libre: "ring-line hover:bg-wash",
  abierta: "bg-raised ring-line hover:bg-overlay",
  en_cocina: "bg-raised ring-line-strong hover:bg-overlay",
  por_aprobar: "bg-overlay ring-paper/35 hover:bg-wash-strong",
  por_servir: "bg-ok/12 ring-ok/45 hover:bg-ok/18",
  por_cobrar: "bg-warn/10 ring-warn/45 hover:bg-warn/16",
};

interface TileProps {
  mesa: Mesa;
  todas: Mesa[];
  comanda: ComandaResumen | undefined;
  editando: boolean;
  uniendo: boolean;
  marcada: boolean;
  orden: number;
  activa: boolean;
  enGrilla: boolean;
  gridRef: React.RefObject<HTMLUListElement | null>;
  onSeleccionar: () => void;
  onDrop: (celda: Celda) => void;
  onAbrirLibre: () => void;
}

const nombreMesa = (n: string) => (/^\d+$/.test(n) ? `Mesa ${n}` : n);

const SILLA = 12; // grosor de la silla en px
const MARGEN = SILLA + 4; // lo que la mesa se retira del borde para dejar sitio a las sillas

/** Sillas alrededor de la mesa: en el perímetro si es redonda, repartidas por los lados si no. */
function Sillas({ n, mesa, ocupada }: { n: number; mesa: Mesa; ocupada: boolean }) {
  const color = ocupada ? "bg-fg-3/70" : "bg-line-strong";
  if (mesa.forma === "redonda") {
    return (
      <>
        {Array.from({ length: n }, (_, k) => {
          const a = (2 * Math.PI * k) / n - Math.PI / 2;
          return (
            <span
              key={k}
              aria-hidden
              className={cn("absolute rounded-full transition-colors", color)}
              style={{
                width: SILLA + 2,
                height: SILLA + 2,
                left: `calc(50% + (50% - ${SILLA / 2 + 1}px) * ${Math.cos(a).toFixed(3)} - ${SILLA / 2 + 1}px)`,
                top: `calc(50% + (50% - ${SILLA / 2 + 1}px) * ${Math.sin(a).toFixed(3)} - ${SILLA / 2 + 1}px)`,
              }}
            />
          );
        })}
      </>
    );
  }
  // Lados en orden de preferencia: la mesa ancha se llena por arriba y abajo; la alta, por los costados
  const orden = mesa.ancho >= mesa.alto ? (["top", "bottom", "top", "bottom", "left", "right"] as const) : (["left", "right", "left", "right", "top", "bottom"] as const);
  const cuenta = { top: 0, bottom: 0, left: 0, right: 0 };
  for (let k = 0; k < n; k++) cuenta[orden[k % orden.length]!]++;
  return (
    <>
      {(Object.keys(cuenta) as (keyof typeof cuenta)[]).flatMap((lado) =>
        Array.from({ length: cuenta[lado] }, (_, k) => {
          const t = `${(((k + 1) / (cuenta[lado] + 1)) * 100).toFixed(2)}%`;
          const horizontal = lado === "top" || lado === "bottom";
          return (
            <span
              key={`${lado}${k}`}
              aria-hidden
              className={cn("absolute rounded-full transition-colors", color)}
              style={{
                ...(horizontal ? { width: 26, height: SILLA, left: `calc(${t} - 13px)` } : { width: SILLA, height: 26, top: `calc(${t} - 13px)` }),
                ...(lado === "top" ? { top: 0 } : lado === "bottom" ? { bottom: 0 } : lado === "left" ? { left: 0 } : { right: 0 }),
              }}
            />
          );
        }),
      )}
    </>
  );
}

function MesaTile({ mesa, todas, comanda, editando, uniendo, marcada, orden, activa, enGrilla, gridRef, onSeleccionar, onDrop, onAbrirLibre }: TileProps) {
  const now = useNow();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const estado = comanda ? estadoSala(comanda) : mesa.ocupada ? "abierta" : "libre";
  // Sin permiso de comandas solo se sabe que la mesa está ocupada
  const { label, tone } = !comanda && mesa.ocupada ? { label: "Ocupada", tone: "neutral" as const } : ESTADO_SALA[estado];
  const p = comanda ? progreso(comanda) : { hechos: 0, total: 0 };
  const ocupada = estado !== "libre";
  const nombre = mesa.nombre;
  const chica = enGrilla && (mesa.ancho < 3 || mesa.alto < 2);
  const principal = todas.find((m) => m.id === mesa.unida_a_id);
  const unidas = todas.filter((m) => m.unida_a_id === mesa.id);
  const comandaId = comanda?.id ?? mesa.comanda_abierta_id;
  // Sin capacidad cargada: una silla por cada ~1.5 celdas de perímetro, entre 2 y 12
  const sillas = Math.min(12, Math.max(2, mesa.capacidad ?? Math.round((mesa.ancho + mesa.alto) * 1.2)));

  const cuerpo = (
    <>
      <Sillas n={sillas} mesa={mesa} ocupada={ocupada} />
      <span
        className={cn(
          "absolute flex flex-col items-center justify-center gap-1 overflow-hidden px-2 text-center shadow-[0_6px_18px_-8px_rgb(0_0_0/0.6)] ring-1 ring-inset transition-colors duration-500",
          mesa.forma === "redonda" ? "rounded-[50%]" : "rounded-[18px]",
          !comanda && mesa.ocupada ? SUPERFICIE.abierta : SUPERFICIE[estado],
          estado === "por_servir" && "shadow-[0_0_22px_-4px_var(--color-ok)]",
          estado === "por_cobrar" && "shadow-[0_0_22px_-4px_var(--color-warn)]",
          marcada && "ring-2 ring-paper",
          activa && "ring-2 ring-paper",
          mesa.unida_a_id && "ring-paper/50",
        )}
        style={{ inset: MARGEN - 6 }}
      >
        <span
          title={nombre}
          className={cn("line-clamp-2 max-w-full break-words font-display leading-[0.95] transition-colors", ocupada ? "text-fg" : "text-fg-2")}
          style={{ fontSize: `clamp(15px, ${nombre.length > 8 ? 15 : 20}cqmin, 34px)` }}
        >
          {chica ? nombre.replace(/^mesa\s+/i, "") : nombre}
        </span>
        {!chica && p.total > 0 && <ProgressLine value={p.hechos} max={p.total} tone={tone} label={`${nombre}: ${label}`} className="w-3/5 bg-line-strong" />}
        <StatusDot tone={tone} className={cn("whitespace-nowrap text-xs", estado === "por_aprobar" && "[&>span:first-child]:animate-pulse")}>
          {label}
        </StatusDot>
        {comanda && !chica && (
          <span className="flex items-baseline gap-2 whitespace-nowrap text-xs tabular text-fg-3">
            {now !== null && <span>{minutosDesde(comanda.created_at, now)}′</span>}
            {isPositive(comanda.total) && <Money value={comanda.total} className="text-fg-2" />}
          </span>
        )}
        {!chica && (principal || unidas.length > 0) && (
          <span className="max-w-full truncate text-[11px] text-fg-3">{principal ? `Unida a ${nombreMesa(principal.nombre)}` : `Con ${unidas.map((u) => u.nombre).join(", ")}`}</span>
        )}
      </span>
      {marcada && <span className="absolute right-1 top-1 z-10 grid size-6 place-items-center rounded-full bg-paper text-sm font-medium text-ink">{orden + 1}</span>}
    </>
  );

  const base = "relative block h-full w-full text-left [container-type:size]";
  // En el plano la mesa lleva un margen para que se vea el hueco entre vecinas
  const style: React.CSSProperties | undefined =
    enGrilla && ubicada(mesa) ? { gridColumn: `${mesa.pos_x + 1} / span ${mesa.ancho}`, gridRow: `${mesa.pos_y + 1} / span ${mesa.alto}`, padding: 2 } : undefined;

  if (editando && enGrilla) {
    return (
      <motion.li
        layout
        transition={smooth}
        style={{ ...style, x, y }}
        drag
        dragMomentum={false}
        whileDrag={{ scale: 1.03, zIndex: 10, cursor: "grabbing" }}
        onDragEnd={(_, info: PanInfo) => {
          const rect = gridRef.current?.getBoundingClientRect();
          if (rect && ubicada(mesa)) {
            const celdaAncho = (rect.width - 16) / COLS; // 16 = relleno del plano
            onDrop({ x: mesa.pos_x + Math.round(info.offset.x / celdaAncho), y: mesa.pos_y + Math.round(info.offset.y / FILA) });
          }
          x.set(0);
          y.set(0);
        }}
        className="touch-none"
      >
        <div
          role="button"
          tabIndex={0}
          aria-label={`${nombre}. Arrástrala para moverla; con teclado, flechas.`}
          onClick={onSeleccionar}
          onKeyDown={(e) => {
            const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
            if (d && ubicada(mesa)) {
              e.preventDefault();
              onDrop({ x: mesa.pos_x + d[0]!, y: mesa.pos_y + d[1]! });
            }
            if (e.key === "Enter" || e.key === " ") onSeleccionar();
          }}
          className={cn(base, "cursor-grab")}
        >
          {cuerpo}
        </div>
      </motion.li>
    );
  }

  return (
    <motion.li layout transition={smooth} style={style} className={enGrilla ? undefined : "h-[140px]"}>
      {uniendo ? (
        <motion.button type="button" whileTap={tap} onClick={onSeleccionar} className={base}>
          {cuerpo}
        </motion.button>
      ) : ocupada && comandaId ? (
        <Link href={`/panel/comandas/${comandaId}`} className={base}>
          {cuerpo}
        </Link>
      ) : (
        <motion.button type="button" whileTap={tap} onClick={onAbrirLibre} className={base}>
          {cuerpo}
        </motion.button>
      )}
    </motion.li>
  );
}
