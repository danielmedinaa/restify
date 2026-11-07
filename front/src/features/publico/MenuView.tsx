"use client";

import * as RD from "@radix-ui/react-dialog";
import { Minus, Plus, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Money } from "@/components/ui/Money";
import { Segmented } from "@/components/ui/Segmented";
import { Sheet } from "@/components/ui/Sheet";
import { StickyHeader } from "@/components/ui/StickyHeader";
import type { ErrorView } from "@/lib/api/errors";
import type { Menu, MenuProducto } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { fade, sheet, smooth, tap } from "@/lib/motion";
import { Escasez } from "./Escasez";
import { Medio } from "./Medio";
import { monedaVista, portada, precioEn, totalCarrito } from "./precio";
import { nombreValido, telefonoValido } from "./datosCliente";
import { carritoStore, monedaStore, type LineaCarrito } from "./stores";

/** Una unidad del plato en el detalle: su nota y los ingredientes que se quitan. */
interface Unidad {
  nota: string;
  sin: number[];
}

const MAX_LINEAS = 30;
const MAX_CANTIDAD = 50;

export interface PedidoEnvio {
  items: { producto_id: number; cantidad: number; notas: string | null; sin_insumo_ids: number[] }[];
  nombre_cliente?: string;
  telefono_cliente?: string;
  notas: string | null;
}

interface MenuViewProps {
  menu: Menu;
  eyebrow: string;
  titulo: string;
  /** Sin carrito: el menú solo se mira. */
  pedido?: {
    scope: string;
    /** Pedir nombre y notas (primer pedido) o solo platos (agregar al pedido). */
    conDatos: boolean;
    accion: string;
    enviar: (p: PedidoEnvio) => Promise<void>;
    error: ErrorView | null;
    limpiarError: () => void;
  };
  arriba?: React.ReactNode;
}

export function MenuView({ menu, eyebrow, titulo, pedido, arriba }: MenuViewProps) {
  const elegida = monedaStore.use();
  const moneda = monedaVista(menu, elegida);
  const store = pedido ? carritoStore(pedido.scope) : null;
  const lineasRaw = store?.use();
  const lineas = useMemo(() => lineasRaw ?? [], [lineasRaw]);
  const productos = useMemo(() => new Map(menu.categorias.flatMap((c) => c.productos.map((p) => [p.id, p] as const))), [menu]);
  const [detalle, setDetalle] = useState<MenuProducto | null>(null);
  const [carritoAbierto, setCarritoAbierto] = useState(false);
  const categorias = menu.categorias.filter((c) => c.productos.length > 0);
  const activa = useScrollSpy(categorias.map((c) => `cat-${c.id ?? "otros"}`));

  // Si el menú ya no ofrece un producto (se agotó), sale del carrito
  useEffect(() => {
    if (store && lineas.some((l) => !productos.has(l.producto_id))) store.set((ls) => ls.filter((l) => productos.has(l.producto_id)));
  }, [store, lineas, productos]);

  const cantidadEnCarrito = (id: number) => lineas.filter((l) => l.producto_id === id).reduce((n, l) => n + l.cantidad, 0);

  /** Una nota y unos ingredientes quitados por unidad. Las unidades iguales se juntan en una línea del carrito. */
  function agregar(p: MenuProducto, unidades: Unidad[]) {
    store?.set((prev) => {
      let ls = prev;
      for (const u of unidades) {
        const nota = u.nota.trim();
        const sin = [...u.sin].sort((a, b) => a - b);
        const i = ls.findIndex((l) => l.producto_id === p.id && l.notas === nota && (l.sin ?? []).join() === sin.join());
        if (i >= 0) ls = ls.map((l, j) => (j === i ? { ...l, cantidad: Math.min(MAX_CANTIDAD, l.cantidad + 1) } : l));
        else if (ls.length < MAX_LINEAS) ls = [...ls, { producto_id: p.id, cantidad: 1, notas: nota, sin }];
      }
      return ls;
    });
  }

  const totalPlatos = lineas.reduce((n, l) => n + l.cantidad, 0);
  const total = totalCarrito(lineas, productos, moneda.codigo);

  return (
    <div className="mx-auto min-h-dvh max-w-2xl pb-40">
      <StickyHeader>
        <div className="flex items-center justify-between gap-4 px-5 pb-3 pt-4">
          <div className="flex min-w-0 flex-col gap-1">
            <span className="eyebrow truncate">{eyebrow}</span>
            <h1 className="truncate font-display text-display-s leading-none">{titulo}</h1>
          </div>
          {menu.monedas.filter((m) => m.activa).length > 1 && (
            <Segmented
              label="Moneda de los precios"
              size="sm"
              value={moneda.codigo}
              onChange={(v) => monedaStore.set(() => v)}
              options={menu.monedas.filter((m) => m.activa).map((m) => ({ value: m.codigo, label: m.codigo }))}
            />
          )}
        </div>
        {categorias.length > 1 && (
          <nav aria-label="Categorías" className="scrollbar-none flex gap-1 overflow-x-auto px-3 pb-3">
            {categorias.map((c) => {
              const id = `cat-${c.id ?? "otros"}`;
              return (
                <a
                  key={id}
                  href={`#${id}`}
                  aria-current={activa === id ? "true" : undefined}
                  className={cn(
                    "relative whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm transition-colors",
                    activa === id ? "text-ink" : "text-fg-2 hover:text-fg",
                  )}
                >
                  {activa === id && <motion.span layoutId="cat-activa" transition={smooth} className="absolute inset-0 rounded-full bg-paper" />}
                  <span className="relative">{c.nombre}</span>
                </a>
              );
            })}
          </nav>
        )}
      </StickyHeader>

      {arriba}

      {categorias.length === 0 ? (
        <div className="px-5 py-24">
          <p className="font-display text-display-m">Cocina cerrada</p>
          <p className="mt-3 text-lead text-fg-2">Ahora mismo no hay platos disponibles. Vuelve en un rato.</p>
        </div>
      ) : (
        categorias.map((c) => (
          <section key={c.id ?? "otros"} id={`cat-${c.id ?? "otros"}`} aria-labelledby={`cat-t-${c.id ?? "otros"}`} className="scroll-mt-32 px-5 pt-12">
            <h2 id={`cat-t-${c.id ?? "otros"}`} className="pb-4 font-display text-display-m">
              {c.nombre}
            </h2>
            <ul className="flex flex-col">
              {c.productos.map((p) => (
                <ProductoFila key={p.id} p={p} moneda={moneda} enCarrito={cantidadEnCarrito(p.id)} onAbrir={() => setDetalle(p)} />
              ))}
            </ul>
          </section>
        ))
      )}

      <ProductoDetalle
        producto={detalle}
        moneda={moneda}
        onClose={() => setDetalle(null)}
        onAgregar={
          pedido
            ? (unidades) => {
                if (detalle) agregar(detalle, unidades);
                setDetalle(null);
              }
            : undefined
        }
      />

      {pedido && store && (
        <>
          <AnimatePresence>
            {totalPlatos > 0 && !carritoAbierto && (
              <motion.div
                initial={{ y: 120 }}
                animate={{ y: 0 }}
                exit={{ y: 120 }}
                transition={sheet}
                className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-2xl px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
              >
                <motion.button
                  type="button"
                  whileTap={tap}
                  onClick={() => setCarritoAbierto(true)}
                  className="flex h-16 w-full items-center justify-between gap-4 rounded-sheet bg-paper px-6 text-ink shadow-float"
                >
                  <span className="flex items-center gap-3 text-lead font-medium">
                    <span className="grid size-8 place-items-center rounded-full bg-ink font-display text-[1.1rem] leading-none text-paper">{totalPlatos}</span>
                    Ver pedido
                  </span>
                  <Money value={total} simbolo={moneda.simbolo} className="text-lead font-medium [&>span:first-child]:text-ink/60" />
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>
          <Carrito
            open={carritoAbierto}
            onOpenChange={setCarritoAbierto}
            lineas={lineas}
            productos={productos}
            moneda={moneda}
            total={total}
            cambiar={(i, cantidad) =>
              store.set((ls) => (cantidad <= 0 ? ls.filter((_, j) => j !== i) : ls.map((l, j) => (j === i ? { ...l, cantidad: Math.min(MAX_CANTIDAD, cantidad) } : l))))
            }
            conDatos={pedido.conDatos}
            accion={pedido.accion}
            error={pedido.error}
            limpiarError={pedido.limpiarError}
            enviar={async (datos) => {
              await pedido.enviar({
                items: lineas.map((l) => ({ producto_id: l.producto_id, cantidad: l.cantidad, notas: l.notas || null, sin_insumo_ids: l.sin ?? [] })),
                ...datos,
              });
              store.set(() => []);
              setCarritoAbierto(false);
            }}
          />
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ lista */
function ProductoFila({ p, moneda, enCarrito, onAbrir }: { p: MenuProducto; moneda: { codigo: string; simbolo: string }; enCarrito: number; onAbrir: () => void }) {
  const media = portada(p);
  return (
    <li>
      <motion.button
        type="button"
        whileTap={{ scale: 0.99 }}
        onClick={onAbrir}
        className="flex w-full items-start gap-4 border-t border-line py-5 text-left"
      >
        <span className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="text-title font-medium leading-snug">{p.nombre}</span>
          {p.descripcion && <span className="line-clamp-2 text-base text-fg-2">{p.descripcion}</span>}
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1">
            <Money value={precioEn(p, moneda.codigo)} simbolo={moneda.simbolo} className="text-lead font-medium" />
            <Escasez porciones={p.porciones_disponibles} />
          </span>
        </span>
        {media && (
          <motion.span layoutId={`media-${p.id}`} transition={smooth} className="relative size-24 shrink-0 overflow-hidden rounded-control bg-raised">
            <Medio medio={media} alt={p.nombre} />
          </motion.span>
        )}
        {enCarrito > 0 && (
          <span className="sr-only">
            {enCarrito} en tu pedido
          </span>
        )}
        {enCarrito > 0 && (
          <span aria-hidden className="-ml-2 grid size-7 shrink-0 place-items-center self-center rounded-full bg-paper font-display text-[1rem] leading-none text-ink">
            {enCarrito}
          </span>
        )}
      </motion.button>
    </li>
  );
}

/* ------------------------------------------------------------------ detalle a pantalla completa */
function ProductoDetalle({
  producto,
  moneda,
  onClose,
  onAgregar,
}: {
  producto: MenuProducto | null;
  moneda: { codigo: string; simbolo: string };
  onClose: () => void;
  onAgregar?: (unidades: Unidad[]) => void;
}) {
  const reduce = useReducedMotion();
  // Se conserva el último producto para que la animación de salida tenga contenido
  const [ultimo, setUltimo] = useState(producto);
  if (producto && producto !== ultimo) setUltimo(producto);
  const p = producto ?? ultimo;

  return (
    <RD.Root open={producto !== null} onOpenChange={(o) => !o && onClose()}>
      <AnimatePresence>
        {producto && p && (
          <RD.Portal forceMount>
            <RD.Overlay asChild forceMount>
              <motion.div className="fixed inset-0 z-40 bg-scrim backdrop-blur-[8px]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={fade} />
            </RD.Overlay>
            <RD.Content asChild forceMount>
              <motion.div
                initial={reduce ? { opacity: 0 } : { y: "100%" }}
                animate={reduce ? { opacity: 1 } : { y: 0 }}
                exit={reduce ? { opacity: 0 } : { y: "100%" }}
                transition={reduce ? fade : sheet}
                className="fixed inset-0 z-50 mx-auto flex max-w-2xl flex-col overflow-y-auto bg-canvas outline-none"
              >
                <DetalleContenido key={p.id} p={p} moneda={moneda} onAgregar={onAgregar} />
              </motion.div>
            </RD.Content>
          </RD.Portal>
        )}
      </AnimatePresence>
    </RD.Root>
  );
}

function DetalleContenido({
  p,
  moneda,
  onAgregar,
}: {
  p: MenuProducto;
  moneda: { codigo: string; simbolo: string };
  onAgregar?: (unidades: Unidad[]) => void;
}) {
  // Una nota (y sus ingredientes quitados) por unidad: 2 hamburguesas = 2 unidades
  const [unidades, setUnidades] = useState<Unidad[]>([{ nota: "", sin: [] }]);
  const cantidad = unidades.length;
  const medios = [...p.medios].sort((a, b) => Number(b.es_portada) - Number(a.es_portada) || a.orden - b.orden);
  const tope = Math.min(MAX_CANTIDAD, p.porciones_disponibles ?? MAX_CANTIDAD);
  const conMedia = medios.length > 0;

  return (
    <>
      <div className={cn("relative shrink-0", conMedia ? "h-[62dvh]" : "h-40")}>
        {conMedia && (
          <motion.div layoutId={`media-${p.id}`} transition={smooth} className="absolute inset-0 overflow-hidden">
            <div className="scrollbar-none flex h-full snap-x snap-mandatory overflow-x-auto">
              {medios.map((m, i) => (
                <div key={m.id} className="h-full w-full shrink-0 snap-center">
                  <Medio medio={m} alt={p.nombre} autoplay={i === 0} />
                </div>
              ))}
            </div>
          </motion.div>
        )}
        <RD.Close
          aria-label="Cerrar"
          className="absolute left-4 top-[max(1rem,env(safe-area-inset-top))] grid size-11 place-items-center rounded-full bg-canvas/50 text-fg backdrop-blur-md"
        >
          <X size={20} strokeWidth={1.5} />
        </RD.Close>
        {/* Franja con blur sobre la foto: nombre y precio sin tapar el plato con un degradado */}
        <div className={cn("absolute inset-x-0 bottom-0 flex flex-col gap-2 px-5 pb-5 pt-6", conMedia && "bg-canvas/45 backdrop-blur-xl")}>
          <RD.Title className="font-display text-display-m leading-[0.95]">{p.nombre}</RD.Title>
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <Money value={precioEn(p, moneda.codigo)} simbolo={moneda.simbolo} className="text-title font-medium" />
            <Escasez porciones={p.porciones_disponibles} />
          </span>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-8 px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-6">
        {p.descripcion ? (
          <RD.Description className="text-lead text-fg-2">{p.descripcion}</RD.Description>
        ) : (
          <RD.Description className="sr-only">{p.nombre}</RD.Description>
        )}
        {medios.length > 1 && <p className="-mt-4 text-sm text-fg-3">Desliza la foto para ver más.</p>}

        {onAgregar && (
          <>
            <fieldset className="flex flex-col gap-1">
              <legend className="eyebrow pb-1.5">{cantidad > 1 ? "Nota para cada uno" : "Nota para cocina"}</legend>
              {p.ingredientes.length > 0 && <p className="pb-2 text-sm text-fg-3">Toca un ingrediente para quitarlo de tu plato.</p>}
              <AnimatePresence initial={false}>
                {unidades.map((u, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={smooth}
                    className="flex flex-col gap-2 overflow-hidden"
                  >
                    <span className="flex items-center gap-3">
                    {cantidad > 1 && <span className="w-7 shrink-0 text-base tabular text-fg-3">#{i + 1}</span>}
                    <input
                      value={u.nota}
                      onChange={(e) => setUnidades((us) => us.map((x, j) => (j === i ? { ...x, nota: e.target.value } : x)))}
                      maxLength={200}
                      placeholder={i === 0 ? "Bien cocido, aparte la salsa…" : "Nota para este"}
                      aria-label={cantidad > 1 ? `Nota para ${p.nombre} #${i + 1}` : `Nota para ${p.nombre}`}
                      className="h-11 min-w-0 flex-1 border-b border-line-strong bg-transparent text-lead outline-none placeholder:text-fg-4 focus:border-paper focus-visible:outline-none"
                    />
                    {cantidad > 1 && (
                      <button
                        type="button"
                        onClick={() => setUnidades((us) => us.filter((_, j) => j !== i))}
                        aria-label={`Quitar ${p.nombre} #${i + 1}`}
                        className="grid size-9 shrink-0 place-items-center rounded-full text-fg-3 hover:bg-wash hover:text-fg"
                      >
                        <X size={16} strokeWidth={1.5} />
                      </button>
                    )}
                    </span>
                    {p.ingredientes.length > 0 && (
                      <span className="flex flex-wrap gap-2" role="group" aria-label={`Ingredientes de ${p.nombre}${cantidad > 1 ? ` #${i + 1}` : ""}`}>
                        {p.ingredientes.map((ing) => {
                          const quitado = u.sin.includes(ing.insumo_id);
                          return (
                            <button
                              key={ing.insumo_id}
                              type="button"
                              aria-pressed={quitado}
                              onClick={() =>
                                setUnidades((us) =>
                                  us.map((x, j) => (j === i ? { ...x, sin: quitado ? x.sin.filter((s) => s !== ing.insumo_id) : [...x.sin, ing.insumo_id] } : x)),
                                )
                              }
                              className={cn(
                                "rounded-full border px-3 py-1.5 text-sm transition-colors",
                                quitado ? "border-line bg-wash text-fg-3 line-through" : "border-line-strong text-fg-2 hover:text-fg",
                              )}
                            >
                              {quitado ? `Sin ${ing.nombre}` : ing.nombre}
                            </button>
                          );
                        })}
                      </span>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>
            </fieldset>
            <div className="mt-auto flex items-center gap-4">
              <div className="flex items-center gap-1">
                <Paso label="Uno menos" onClick={() => setUnidades((us) => (us.length > 1 ? us.slice(0, -1) : us))} disabled={cantidad <= 1}>
                  <Minus size={18} strokeWidth={1.5} />
                </Paso>
                <span className="w-10 text-center font-display text-display-s tabular" aria-live="polite">
                  {cantidad}
                </span>
                <Paso label="Uno más" onClick={() => setUnidades((us) => (us.length < tope ? [...us, { nota: "", sin: [] }] : us))} disabled={cantidad >= tope}>
                  <Plus size={18} strokeWidth={1.5} />
                </Paso>
              </div>
              <Button size="lg" className="flex-1" onClick={() => onAgregar(unidades)}>
                Agregar
              </Button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function Paso({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <motion.button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      whileTap={disabled ? undefined : tap}
      className="grid size-11 place-items-center rounded-full border border-line-strong transition-colors hover:bg-wash disabled:opacity-30"
    >
      {children}
    </motion.button>
  );
}

/* ------------------------------------------------------------------ carrito */
function Carrito({
  open,
  onOpenChange,
  lineas,
  productos,
  moneda,
  total,
  cambiar,
  conDatos,
  accion,
  error,
  limpiarError,
  enviar,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  lineas: LineaCarrito[];
  productos: Map<number, MenuProducto>;
  moneda: { codigo: string; simbolo: string };
  total: string;
  cambiar: (index: number, cantidad: number) => void;
  conDatos: boolean;
  accion: string;
  error: ErrorView | null;
  limpiarError: () => void;
  enviar: (datos: { nombre_cliente?: string; telefono_cliente?: string; notas: string | null }) => Promise<void>;
}) {
  const [nombre, setNombre] = useState("");
  const [telefono, setTelefono] = useState("");
  const [notas, setNotas] = useState("");
  const [enviando, setEnviando] = useState(false);
  // Se marcan los campos en rojo solo después del primer intento de envío
  const [intentado, setIntentado] = useState(false);
  const nombreOk = nombreValido(nombre);
  const telefonoOk = telefonoValido(telefono);
  const datosMalos = conDatos && intentado && (!nombreOk || !telefonoOk);

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Tu pedido"
      description="Revisa antes de enviarlo. El mesero lo confirma y pasa a cocina."
      footer={
        <div className="flex flex-col gap-3">
          {datosMalos && (
            <ErrorBox
              error={{
                title: "Revisa tus datos",
                description: "Si tu nombre o tu teléfono no son correctos, tu orden será ignorada.",
                tone: "warn",
              }}
            />
          )}
          {error && <ErrorBox error={error} onClose={limpiarError} />}
          <Button
            size="lg"
            className="w-full"
            loading={enviando}
            disabled={lineas.length === 0}
            onClick={async () => {
              if (conDatos && (!nombreOk || !telefonoOk)) {
                setIntentado(true);
                return;
              }
              setEnviando(true);
              try {
                await enviar(
                  conDatos
                    ? { nombre_cliente: nombre.replace(/\s+/g, " ").trim(), telefono_cliente: telefono.trim(), notas: notas.trim() || null }
                    : { notas: null },
                );
              } catch {
                // el error se muestra arriba (lo maneja quien envía)
              } finally {
                setEnviando(false);
              }
            }}
          >
            {accion} · <Money value={total} simbolo={moneda.simbolo} className="[&>span:first-child]:text-ink/60" />
          </Button>
        </div>
      }
    >
      <ul className="flex flex-col">
        <AnimatePresence initial={false}>
          {lineas.map((l, i) => {
            const p = productos.get(l.producto_id);
            if (!p) return null;
            return (
              <motion.li
                key={`${l.producto_id}-${l.notas}-${(l.sin ?? []).join()}`}
                layout
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={smooth}
                className="overflow-hidden"
              >
                <div className="flex items-center gap-4 border-t border-line py-4">
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-title font-medium">{p.nombre}</span>
                    {(l.sin ?? []).length > 0 && (
                      <span className="text-sm text-fg-3">
                        Sin {p.ingredientes.filter((g) => l.sin?.includes(g.insumo_id)).map((g) => g.nombre).join(", ")}
                      </span>
                    )}
                    {l.notas && <span className="text-sm text-fg-3">“{l.notas}”</span>}
                    <Money value={precioEn(p, moneda.codigo)} simbolo={moneda.simbolo} className="text-sm text-fg-2" />
                  </span>
                  <div className="flex items-center gap-1">
                    <Paso label={`Uno menos de ${p.nombre}`} onClick={() => cambiar(i, l.cantidad - 1)}>
                      <Minus size={16} strokeWidth={1.5} />
                    </Paso>
                    <span className="w-8 text-center font-display text-[1.4rem] leading-none tabular">{l.cantidad}</span>
                    <Paso
                      label={`Uno más de ${p.nombre}`}
                      onClick={() => cambiar(i, l.cantidad + 1)}
                      disabled={l.cantidad >= Math.min(MAX_CANTIDAD, p.porciones_disponibles ?? MAX_CANTIDAD)}
                    >
                      <Plus size={16} strokeWidth={1.5} />
                    </Paso>
                  </div>
                </div>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
      {conDatos && (
        <div className="flex flex-col gap-6 pt-6">
          <label className="flex flex-col gap-1.5">
            <span className="eyebrow">¿A nombre de quién?</span>
            <input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              maxLength={60}
              autoComplete="name"
              placeholder="Tu nombre"
              aria-invalid={intentado && !nombreOk ? true : undefined}
              className={cn(
                "h-11 border-b border-line-strong bg-transparent text-lead outline-none placeholder:text-fg-4 focus:border-paper focus-visible:outline-none",
                intentado && !nombreOk && "border-err",
              )}
            />
            {intentado && !nombreOk && <span className="text-sm text-err">Escribe tu nombre real, solo con letras.</span>}
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="eyebrow">Tu teléfono</span>
            <input
              value={telefono}
              onChange={(e) => setTelefono(e.target.value)}
              type="tel"
              inputMode="tel"
              maxLength={20}
              autoComplete="tel"
              placeholder="0412 123 4567"
              aria-invalid={intentado && !telefonoOk ? true : undefined}
              className={cn(
                "h-11 border-b border-line-strong bg-transparent text-lead tabular outline-none placeholder:text-fg-4 focus:border-paper focus-visible:outline-none",
                intentado && !telefonoOk && "border-err",
              )}
            />
            {intentado && !telefonoOk && <span className="text-sm text-err">Escribe un celular válido, por ejemplo 0412 123 4567.</span>}
          </label>
          <ul className="flex flex-col gap-2 border-l border-warn/60 pl-4 text-sm text-fg-2">
            <li>Usa tu nombre y teléfono reales: si tus datos no son correctos, tu orden será ignorada.</li>
            <li>Podemos escribirte o llamarte para confirmar. Si no respondes en 15 minutos, tu orden será cancelada.</li>
          </ul>
          <label className="flex flex-col gap-1.5">
            <span className="eyebrow">Algo más que debamos saber</span>
            <input
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
              maxLength={500}
              placeholder="Alergias, celebración…"
              className="h-11 border-b border-line-strong bg-transparent text-lead outline-none placeholder:text-fg-4 focus:border-paper focus-visible:outline-none"
            />
          </label>
        </div>
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------------ scroll-spy */
function useScrollSpy(ids: string[]): string | undefined {
  const [activa, setActiva] = useState<string | undefined>(undefined);
  const key = ids.join("|");
  const visibles = useRef(new Map<string, number>());
  useEffect(() => {
    const lista = key ? key.split("|") : [];
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) visibles.current.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0);
        const primera = lista.find((id) => (visibles.current.get(id) ?? 0) > 0);
        if (primera) setActiva(primera);
      },
      { rootMargin: "-140px 0px -50% 0px", threshold: [0, 0.01, 0.5] },
    );
    lista.forEach((id) => {
      const el = document.getElementById(id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [key]);
  return activa ?? ids[0];
}
