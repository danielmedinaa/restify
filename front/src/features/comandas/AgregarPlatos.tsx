"use client";

import Big from "big.js";
import { Minus, Plus, Search, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Money } from "@/components/ui/Money";
import { Sheet } from "@/components/ui/Sheet";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/Status";
import { Switch } from "@/components/ui/Switch";
import { describeError, type ErrorView } from "@/lib/api/errors";
import type { Comanda, MenuProducto } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { smooth, tap } from "@/lib/motion";
import { principalDe, useComandaAction, useMenu } from "./queries";

/** Una nota por unidad: 3 hamburguesas = 3 notas (vacías si no llevan nada). */
type Unidades = string[];

const MAX_POR_PRODUCTO = 50;

/** Pocas porciones: se avisa para no prometer lo que no hay. */
const ESCASO = 5;

export function AgregarPlatos({ open, onOpenChange, comanda }: { open: boolean; onOpenChange: (o: boolean) => void; comanda: Comanda }) {
  const menu = useMenu(comanda.sucursal_id, open);
  const [lineas, setLineas] = useState<Map<number, Unidades>>(new Map());
  const [q, setQ] = useState("");
  const [cocina, setCocina] = useState(true);
  const [error, setError] = useState<ErrorView | null>(null);

  const productos = useMemo(() => new Map(menu.data?.categorias.flatMap((c) => c.productos.map((p) => [p.id, p] as const))), [menu.data]);
  const simbolo = principalDe(menu.data?.monedas)?.simbolo;

  const filtradas = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (menu.data?.categorias ?? [])
      .map((c) => ({ ...c, productos: t ? c.productos.filter((p) => p.nombre.toLowerCase().includes(t)) : c.productos }))
      .filter((c) => c.productos.length > 0);
  }, [menu.data, q]);

  const cantidadTotal = [...lineas.values()].reduce((n, u) => n + u.length, 0);
  // Suma decimal exacta con big.js; el total real lo devuelve el backend al guardar
  const subtotal = [...lineas.entries()]
    .reduce((acc, [id, u]) => acc.plus(new Big(productos.get(id)?.precio ?? "0").times(u.length)), new Big(0))
    .toFixed(2);

  const agregar = useComandaAction<void>(
    comanda.id,
    () => ({
      path: "/items",
      body: {
        items: agrupar(lineas),
        enviar_a_cocina: cocina,
      },
    }),
    {
      onSuccess: () => cerrar(false),
      onError: (err) => {
        setError(describeError(err));
        return true;
      },
    },
  );

  function cerrar(o: boolean) {
    onOpenChange(o);
    if (!o) {
      setLineas(new Map());
      setQ("");
      setError(null);
    }
  }

  function editar(id: number, fn: (u: Unidades) => Unidades) {
    setLineas((prev) => {
      const next = new Map(prev);
      const u = fn(next.get(id) ?? []);
      if (u.length === 0) next.delete(id);
      else next.set(id, u);
      return next;
    });
  }
  const sumar = (p: MenuProducto) => editar(p.id, (u) => (u.length >= tope(p) ? u : [...u, ""]));
  const restar = (p: MenuProducto) => editar(p.id, (u) => u.slice(0, -1));
  const quitar = (p: MenuProducto, i: number) => editar(p.id, (u) => u.filter((_, j) => j !== i));
  const nota = (p: MenuProducto, i: number, texto: string) => editar(p.id, (u) => u.map((n, j) => (j === i ? texto : n)));

  return (
    <Sheet
      open={open}
      onOpenChange={cerrar}
      side="right"
      title="Agregar platos"
      description={comanda.mesa ? `A la comanda de ${comanda.mesa}` : `A la comanda ${comanda.id}`}
      footer={
        <div className="flex flex-col gap-4">
          {error && <ErrorBox error={error} onClose={() => setError(null)} />}
          <Switch checked={cocina} onCheckedChange={setCocina} label="Enviar a cocina al agregar" />
          <Button size="lg" className="w-full" disabled={cantidadTotal === 0} loading={agregar.isPending} onClick={() => agregar.mutate()}>
            {cantidadTotal === 0 ? (
              "Elige platos"
            ) : (
              <>
                Agregar {cantidadTotal} {cantidadTotal === 1 ? "plato" : "platos"} · <Money value={subtotal} simbolo={simbolo} />
              </>
            )}
          </Button>
        </div>
      }
    >
      <label className="sticky top-0 z-10 -mx-6 mb-2 flex items-center gap-3 border-b border-line bg-overlay/95 px-6 backdrop-blur-xl">
        <Search size={16} strokeWidth={1.5} className="text-fg-3" aria-hidden />
        <span className="sr-only">Buscar plato</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar plato"
          className="h-12 w-full bg-transparent text-base outline-none placeholder:text-fg-4 focus-visible:outline-none"
        />
      </label>

      {menu.isPending ? (
        <div className="flex flex-col gap-5 pt-4" aria-busy>
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex justify-between">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-5 w-16" />
            </div>
          ))}
        </div>
      ) : menu.isError ? (
        <EmptyState title="Sin menú" description={describeError(menu.error).title} className="py-8" />
      ) : filtradas.length === 0 ? (
        <p className="py-10 text-center text-base text-fg-3">{q ? "Nada con ese nombre." : "No hay platos disponibles en esta sucursal."}</p>
      ) : (
        filtradas.map((cat) => (
          <section key={cat.id ?? "otros"} className="flex flex-col pt-6">
            <h3 className="eyebrow pb-3">{cat.nombre}</h3>
            <ul className="grid grid-cols-2 gap-2">
              {cat.productos.map((p) => (
                <PlatoTile
                  key={p.id}
                  p={p}
                  unidades={lineas.get(p.id)}
                  simbolo={simbolo}
                  onSumar={() => sumar(p)}
                  onRestar={() => restar(p)}
                  onQuitar={(i) => quitar(p, i)}
                  onNota={(i, t) => nota(p, i, t)}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </Sheet>
  );
}

function tope(p: MenuProducto) {
  return Math.min(MAX_POR_PRODUCTO, p.porciones_disponibles ?? MAX_POR_PRODUCTO);
}

/** Unidades con la misma nota viajan juntas: 2 "sin cebolla" + 1 sin nota = 2 líneas. */
function agrupar(lineas: Map<number, Unidades>) {
  const items: { producto_id: number; cantidad: number; notas: string | null }[] = [];
  for (const [producto_id, unidades] of lineas) {
    const porNota = new Map<string, number>();
    for (const n of unidades) porNota.set(n.trim(), (porNota.get(n.trim()) ?? 0) + 1);
    for (const [notas, cantidad] of porNota) items.push({ producto_id, cantidad, notas: notas || null });
  }
  return items;
}

/** Portada del plato si tiene una foto (los videos no se reproducen aquí). */
function portada(p: MenuProducto) {
  const imagenes = p.medios.filter((m) => m.tipo === "imagen");
  return imagenes.find((m) => m.es_portada) ?? imagenes[0];
}

/**
 * Plato en la grilla. Tocarlo agrega una unidad; con unidades elegidas se abre a lo
 * ancho y cada unidad (#1, #2…) lleva su propia nota para cocina.
 */
function PlatoTile({
  p,
  unidades,
  simbolo,
  onSumar,
  onRestar,
  onQuitar,
  onNota,
}: {
  p: MenuProducto;
  unidades: Unidades | undefined;
  simbolo?: string;
  onSumar: () => void;
  onRestar: () => void;
  onQuitar: (i: number) => void;
  onNota: (i: number, texto: string) => void;
}) {
  const quedan = p.porciones_disponibles;
  const lleno = (unidades?.length ?? 0) >= tope(p);
  const foto = portada(p);
  const abierto = !!unidades;

  return (
    <motion.li layout transition={smooth} className={cn("overflow-hidden rounded-control border transition-colors", abierto ? "col-span-2 border-line-strong bg-wash" : "border-line")}>
      {abierto ? (
        <div className="flex flex-col">
          <div className="flex items-center gap-3 p-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-base font-medium">{p.nombre}</span>
              <Money value={p.precio} simbolo={simbolo} className="text-sm text-fg-2" />
            </div>
            <Stepper label={`Quitar un ${p.nombre}`} onClick={onRestar}>
              <Minus size={16} strokeWidth={1.5} />
            </Stepper>
            <span className="w-7 text-center font-display text-display-s leading-none tabular" aria-live="polite">
              {unidades.length}
            </span>
            <Stepper label={`Agregar un ${p.nombre}`} onClick={onSumar} disabled={lleno}>
              <Plus size={16} strokeWidth={1.5} />
            </Stepper>
          </div>
          <ol className="flex flex-col border-t border-line">
            <AnimatePresence initial={false}>
              {unidades.map((n, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={smooth}
                  className="flex items-center gap-3 px-3"
                >
                  <span className="w-6 shrink-0 text-sm tabular text-fg-3">#{i + 1}</span>
                  <input
                    value={n}
                    onChange={(e) => onNota(i, e.target.value)}
                    maxLength={255}
                    placeholder={i === 0 ? "Nota para cocina (sin cebolla, término medio…)" : "Nota para esta unidad"}
                    aria-label={`Nota para ${p.nombre} #${i + 1}`}
                    className="h-10 min-w-0 flex-1 border-b border-transparent bg-transparent text-sm outline-none placeholder:text-fg-4 focus:border-paper focus-visible:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => onQuitar(i)}
                    aria-label={`Quitar ${p.nombre} #${i + 1}`}
                    className="grid size-8 shrink-0 place-items-center rounded-full text-fg-3 hover:bg-wash hover:text-fg"
                  >
                    <X size={14} strokeWidth={1.5} />
                  </button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ol>
        </div>
      ) : (
        <motion.button type="button" onClick={onSumar} disabled={lleno} whileTap={tap} className="flex h-full w-full flex-col text-left hover:bg-wash disabled:opacity-40">
          {foto && (
            // eslint-disable-next-line @next/next/no-img-element -- miniatura servida por /media
            <img src={foto.url} alt={foto.texto_alt ?? ""} loading="lazy" className="aspect-[16/10] w-full object-cover" />
          )}
          <span className="flex flex-1 flex-col gap-1 p-3">
            <span className="line-clamp-2 text-base font-medium leading-snug">{p.nombre}</span>
            <span className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <Money value={p.precio} simbolo={simbolo} className="text-fg-2" />
              {quedan !== null && quedan <= ESCASO && <StatusDot tone="warn">Quedan {quedan}</StatusDot>}
            </span>
          </span>
        </motion.button>
      )}
    </motion.li>
  );
}

function Stepper({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <motion.button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      whileTap={disabled ? undefined : tap}
      className={cn("grid size-9 place-items-center rounded-full border border-line-strong transition-colors hover:bg-wash disabled:opacity-30")}
    >
      {children}
    </motion.button>
  );
}
