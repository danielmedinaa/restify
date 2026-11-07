"use client";

import * as DM from "@radix-ui/react-dropdown-menu";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Check, Minus, Plus, X } from "lucide-react";
import { LayoutGroup, motion, useMotionValue, type PanInfo } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Money } from "@/components/ui/Money";
import { Segmented } from "@/components/ui/Segmented";
import { toast } from "@/components/ui/Toast";
import { Loading, Skeleton } from "@/components/ui/Skeleton";
import { can, useMe } from "@/features/auth/useMe";
import { tituloComanda } from "@/features/comandas/estado";
import { METODO } from "@/features/comandas/ComandaDetalle";
import { ProgressLine } from "@/components/ui/Status";
import { CobrarModal } from "./CobrarModal";
import { principalDe, useComanda, useComandaAction, useDivisionIguales, useMonedas } from "@/features/comandas/queries";
import { menuContent, menuItem } from "@/features/panel/SucursalPicker";
import { createStore } from "@/features/publico/stores";
import { api } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { DivisionOut, type Comanda, type Division, type Item } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { remaining, isPositive } from "@/lib/money";
import { smooth, snappy } from "@/lib/motion";

const POOL = "pool";

interface Persona {
  id: string;
  nombre: string;
}

export function Dividir({ id }: { id: number }) {
  const comanda = useComanda(id);
  if (comanda.isPending) {
    return (
      <Loading label="Cargando cuenta">
        <Skeleton className="h-14 w-64" />
        <div className="mt-14 flex gap-6">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-64 w-64" />
          ))}
        </div>
      </Loading>
    );
  }
  if (comanda.isError) return <EmptyState title={describeError(comanda.error).title} description="" />;
  return <DividirComanda c={comanda.data} />;
}

function DividirComanda({ c }: { c: Comanda }) {
  const [modo, setModo] = useState<"platos" | "iguales" | "vaca">("platos");
  const { data: monedas } = useMonedas(c.sucursal_id);
  const simbolo = principalDe(monedas)?.simbolo ?? c.totales.total_monedas.find((m) => m.monto === c.totales.total)?.simbolo;
  const router = useRouter();
  const { data: me } = useMe();
  const hayPendiente = isPositive(c.totales.pendiente);
  const cubierta = c.estado === "abierta" && !hayPendiente && isPositive(c.totales.total);
  const cerrar = useComandaAction<void>(c.id, () => ({ path: "/cerrar" }), {
    onSuccess: () => {
      toast({ title: `Venta registrada · ${tituloComanda(c)}`, description: "La mesa quedó libre.", tone: "ok" });
      router.push("/panel");
    },
  });

  return (
    <>
      <PageHeader
        eyebrow={
          <Link href={`/panel/caja/${c.id}`} className="hover:text-fg-2">
            ← Caja
          </Link>
        }
        title={`Dividir · ${tituloComanda(c)}`}
        actions={
          <Segmented
            label="Cómo dividir"
            value={modo}
            onChange={setModo}
            options={[
              { value: "platos", label: "Por platos" },
              { value: "iguales", label: "Partes iguales" },
              { value: "vaca", label: "Vaca" },
            ]}
          />
        }
      />
      {c.estado === "abierta" && (
        <div className="-mt-4 mb-8 flex flex-wrap items-center gap-x-6 gap-y-3">
          {cubierta ? (
            <>
              <span className="text-lead text-ok">✓ Todos pagaron. La cuenta está cubierta.</span>
              {can(me, "caja", "editar") && (
                <Button loading={cerrar.isPending} onClick={() => cerrar.mutate()}>
                  Cerrar y liberar {c.mesa ? "la mesa" : "la comanda"}
                </Button>
              )}
            </>
          ) : (
            <span className="text-base text-fg-2">
              Falta cobrar <Money value={c.totales.pendiente} simbolo={simbolo} className="font-medium text-fg" /> de <Money value={c.totales.total} simbolo={simbolo} />
            </span>
          )}
        </div>
      )}
      {modo === "platos" ? <PorPlatos c={c} simbolo={simbolo} /> : modo === "iguales" ? <Iguales c={c} simbolo={simbolo} /> : <Vaca c={c} simbolo={simbolo} />}
    </>
  );
}

/* ------------------------------------------------------------------ partes iguales */
function Iguales({ c, simbolo }: { c: Comanda; simbolo?: string }) {
  const [partes, setPartes] = useState(2);
  const div = useDivisionIguales(c.id, partes, true);
  return (
    <div className="flex flex-col gap-12">
      <div className="flex items-center gap-4">
        <Button variant="line" aria-label="Una parte menos" onClick={() => setPartes((p) => Math.max(2, p - 1))} disabled={partes <= 2}>
          <Minus size={16} strokeWidth={1.5} />
        </Button>
        <span className="w-24 text-center font-display text-display-l tabular" aria-live="polite">
          {partes}
        </span>
        <Button variant="line" aria-label="Una parte más" onClick={() => setPartes((p) => Math.min(50, p + 1))} disabled={partes >= 50}>
          <Plus size={16} strokeWidth={1.5} />
        </Button>
        <span className="text-lead text-fg-2">partes</span>
      </div>
      {div.data ? (
        <ul className="grid gap-x-10 tablet:grid-cols-2 desk:grid-cols-3">
          {div.data.partes.map((p) => (
            <ParteRow key={p.etiqueta} comanda={c} parte={p} simbolo={simbolo} />
          ))}
        </ul>
      ) : (
        <Skeleton className="h-40 w-full" />
      )}
      <p className="text-sm text-fg-3">La última parte absorbe el redondeo. Cada pago se registra con su etiqueta.</p>
    </div>
  );
}

function ParteRow({ comanda, parte, simbolo }: { comanda: Comanda; parte: Division["partes"][number]; simbolo?: string }) {
  const falta = remaining(parte.monto, parte.pagado);
  return (
    <li className="flex flex-col gap-3 border-t border-line py-5">
      <div className="flex items-baseline justify-between">
        <span className="text-title font-medium">{parte.etiqueta}</span>
        <Money value={parte.monto} simbolo={simbolo} size="s" />
      </div>
      <CobrarParte comanda={comanda} etiqueta={parte.etiqueta} falta={falta} pagado={parte.pagado} simbolo={simbolo} />
    </li>
  );
}

function CobrarParte({ comanda, etiqueta, falta, pagado, simbolo }: { comanda: Comanda; etiqueta: string; falta: string; pagado: string; simbolo?: string }) {
  const { data: me } = useMe();
  const { data: monedas } = useMonedas(comanda.sucursal_id);
  const [abierto, setAbierto] = useState(false);
  if (!isPositive(falta)) return <p className="flex items-center gap-2 rounded-control bg-ok/12 px-3 py-2 text-base font-medium text-ok ring-1 ring-inset ring-ok/40">
        <Check size={16} strokeWidth={2} aria-hidden /> {etiqueta} ya pagó
        {isPositive(pagado) && <Money value={pagado} simbolo={simbolo} className="ml-auto text-sm font-normal text-fg-2" />}
      </p>;
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-fg-3">{isPositive(pagado) ? <>Pagó <Money value={pagado} simbolo={simbolo} /></> : "Sin pagos"}</span>
      {can(me, "caja", "crear") && comanda.estado === "abierta" && (
        <button
          type="button"
          onClick={() => setAbierto(true)}
          className="inline-flex h-8 items-center rounded-control bg-paper px-3 text-sm font-medium text-ink hover:bg-paper/90"
        >
          Cobrar <Money value={falta} simbolo={simbolo} className="ml-1.5" />
        </button>
      )}
      {abierto && <CobrarModal comanda={comanda} monedas={monedas ?? []} etiqueta={etiqueta} falta={falta} onClose={() => setAbierto(false)} />}
    </div>
  );
}

/* ------------------------------------------------------------------ vaca */
/** Todos ponen lo que quieren hasta cubrir la cuenta. Cada aporte es un pago con el nombre de quien lo puso. */
function Vaca({ c, simbolo }: { c: Comanda; simbolo?: string }) {
  const { data: me } = useMe();
  const { data: monedas } = useMonedas(c.sucursal_id);
  const [abierto, setAbierto] = useState(false);
  const quitar = useComandaAction<number>(c.id, (pagoId) => ({ path: `/pagos/${pagoId}`, method: "DELETE" }));
  const abierta = c.estado === "abierta";
  const falta = c.totales.pendiente;
  const pagado = remaining(c.totales.total, falta);
  const aportes = c.pagos;

  return (
    <div className="flex max-w-2xl flex-col gap-10">
      <p className="max-w-xl text-base text-fg-2">Cada quien pone lo que quiera hasta cubrir la cuenta. Anota quién aportó y, si paga con un billete grande, el vuelto se calcula al momento.</p>
      <section aria-label="Avance de la vaca" className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-4">
          <span className="eyebrow">{isPositive(falta) ? "Falta" : "Cubierta"}</span>
          <Money value={isPositive(falta) ? falta : c.totales.total} simbolo={simbolo} size="l" roll />
        </div>
        <ProgressLine value={Number(pagado)} max={Number(c.totales.total) || 1} tone={isPositive(falta) ? "warn" : "ok"} label="Avance de la vaca" />
        <div className="flex justify-between text-sm text-fg-3">
          <span>
            Aportado <Money value={pagado} simbolo={simbolo} />
          </span>
          <span>
            Total <Money value={c.totales.total} simbolo={simbolo} />
          </span>
        </div>
      </section>

      {abierta && isPositive(falta) && can(me, "caja", "crear") && (
        <Button size="lg" onClick={() => setAbierto(true)}>
          <Plus size={18} strokeWidth={1.5} aria-hidden /> Agregar aporte
        </Button>
      )}
      {abierto && <CobrarModal comanda={c} monedas={monedas ?? []} falta={falta} vaca={{ siguiente: aportes.length + 1 }} onClose={() => setAbierto(false)} />}

      <section aria-label="Aportes" className="flex flex-col">
        <h2 className="eyebrow pb-2">Aportes · {aportes.length}</h2>
        {aportes.length === 0 ? (
          <p className="border-t border-line pt-4 text-sm text-fg-3">Todavía nadie ha puesto.</p>
        ) : (
          <ul>
            {aportes.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-4 border-t border-line py-3.5">
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-title font-medium">{p.etiqueta || "Pago"}</span>
                  <span className="text-sm text-fg-3">{METODO[p.metodo]}</span>
                </span>
                <span className="flex items-center gap-3">
                  <Money value={p.monto_principal} simbolo={simbolo} className="text-base" />
                  {abierta && can(me, "caja", "eliminar") && (
                    <button type="button" aria-label={`Quitar aporte de ${p.etiqueta || "pago"}`} onClick={() => quitar.mutate(p.id)} className="grid size-8 place-items-center rounded-md text-fg-3 hover:bg-wash hover:text-fg">
                      <X size={16} strokeWidth={1.5} />
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ por platos */
interface EstadoDivision {
  personas: Persona[];
  asignacion: Record<number, string>;
  seq: number;
}

const stores = new Map<number, ReturnType<typeof createStore<EstadoDivision | null>>>();
function divisionStore(comandaId: number) {
  let s = stores.get(comandaId);
  if (!s) {
    s = createStore<EstadoDivision | null>(`rs_division:${comandaId}`, null);
    stores.set(comandaId, s);
  }
  return s;
}

/** Sin reparto guardado: las personas que ya pagaron con etiqueta, o dos personas vacías. */
function repartoInicial(c: Comanda): EstadoDivision {
  const previas = [...new Set(c.pagos.map((p) => p.etiqueta).filter((e): e is string => !!e))];
  const nombres = previas.length ? previas : ["Persona 1", "Persona 2"];
  return { personas: nombres.map((nombre, i) => ({ id: `p${i}`, nombre })), asignacion: {}, seq: nombres.length };
}
function PorPlatos({ c, simbolo }: { c: Comanda; simbolo?: string }) {
  const items = useMemo(() => c.items.filter((i) => i.estado !== "cancelado"), [c.items]);
  // El reparto se guarda por comanda: al ir a cobrar una parte y volver, sigue igual
  const store = divisionStore(c.id);
  const guardado = store.use();
  const estado: EstadoDivision = guardado ?? repartoInicial(c);
  const { personas, asignacion, seq } = estado;
  const actualizar = (fn: (e: EstadoDivision) => EstadoDivision) => store.set((prev) => fn(prev ?? repartoInicial(c)));

  const grupos = personas
    .map((p) => ({ etiqueta: p.nombre.trim() || "Sin nombre", item_ids: items.filter((i) => asignacion[i.id] === p.id).map((i) => i.id) }))
    .filter((g) => g.item_ids.length > 0);

  const division = useQuery({
    queryKey: ["division", c.id, "items", JSON.stringify(grupos)],
    queryFn: () => api(`/comandas/${c.id}/division`, { method: "POST", body: { grupos }, schema: DivisionOut }),
    enabled: grupos.length > 0,
    placeholderData: keepPreviousData,
  });
  const parteDe = (nombre: string) => division.data?.partes.find((p) => p.etiqueta === (nombre.trim() || "Sin nombre"));

  const mover = (itemId: number, destino: string) =>
    actualizar((e) => {
      const a = { ...e.asignacion };
      if (destino === POOL) delete a[itemId];
      else a[itemId] = destino;
      return { ...e, asignacion: a };
    });

  function agregarPersona() {
    actualizar((e) => ({ ...e, personas: [...e.personas, { id: `p${e.seq}`, nombre: `Persona ${e.personas.length + 1}` }], seq: e.seq + 1 }));
  }

  function quitarPersona(id: string) {
    actualizar((e) => ({
      ...e,
      personas: e.personas.filter((p) => p.id !== id),
      asignacion: Object.fromEntries(Object.entries(e.asignacion).filter(([, pid]) => pid !== id)),
    }));
  }

  function renombrar(id: string, nombre: string) {
    actualizar((e) => ({ ...e, personas: e.personas.map((p) => (p.id === id ? { ...p, nombre } : p)) }));
  }

  const nombresRepetidos = new Set(
    personas.map((p) => p.nombre.trim().toLowerCase()).filter((n, i, all) => all.indexOf(n) !== i),
  );

  const columnas = [{ id: POOL, nombre: "Sin asignar" }, ...personas];
  const pool = items.filter((i) => !asignacion[i.id]);

  if (items.length === 0) return <EmptyState title="Nada que dividir" description="La comanda no tiene platos." />;

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-2xl text-base text-fg-2">
        Arrastra cada plato hacia quien lo pagará. Con teclado, abre el plato y elige a quién moverlo. Los montos los calcula el
        servidor.
      </p>
      <LayoutGroup>
        <div className="-mx-4 flex gap-4 overflow-x-auto px-4 pb-4 tablet:mx-0 tablet:px-0">
          {columnas.map((col) => {
            const propios = col.id === POOL ? pool : items.filter((i) => asignacion[i.id] === col.id);
            const parte = col.id === POOL ? undefined : parteDe(col.nombre);
            const repetido = col.id !== POOL && nombresRepetidos.has(col.nombre.trim().toLowerCase());
            return (
              <section
                key={col.id}
                data-columna={col.id}
                aria-label={col.nombre}
                className={cn(
                  "flex min-h-80 w-72 shrink-0 flex-col gap-4 rounded-sheet p-4 transition-colors",
                  col.id === POOL ? "bg-sunken" : "bg-raised",
                )}
              >
                <header className="flex items-center justify-between gap-2">
                  {col.id === POOL ? (
                    <h2 className="eyebrow">
                      Sin asignar · {pool.length}
                    </h2>
                  ) : (
                    <>
                      <input
                        value={col.nombre}
                        onChange={(e) => renombrar(col.id, e.target.value)}
                        maxLength={60}
                        aria-label="Nombre de la persona"
                        aria-invalid={repetido || undefined}
                        className={cn(
                          "min-w-0 flex-1 border-b bg-transparent font-display text-display-s outline-none focus-visible:outline-none",
                          repetido ? "border-err" : "border-transparent focus:border-paper",
                        )}
                      />
                      <button
                        type="button"
                        onClick={() => quitarPersona(col.id)}
                        aria-label={`Quitar a ${col.nombre}`}
                        className="grid size-8 place-items-center rounded-md text-fg-3 hover:bg-wash hover:text-fg"
                      >
                        <X size={16} strokeWidth={1.5} />
                      </button>
                    </>
                  )}
                </header>
                {repetido && <p className="-mt-2 text-sm text-err">Usa un nombre distinto: los pagos se separan por nombre.</p>}

                <ul className="flex flex-1 flex-col gap-2">
                  {propios.map((i) => (
                    <Ficha key={i.id} item={i} columnas={columnas} actual={col.id} onMover={(dest) => mover(i.id, dest)} simbolo={simbolo} />
                  ))}
                  {propios.length === 0 && (
                    <li className="grid flex-1 place-items-center rounded-control border border-dashed border-line-strong p-6 text-center text-sm text-fg-3">
                      {col.id === POOL ? "Todo repartido" : "Suelta aquí sus platos"}
                    </li>
                  )}
                </ul>

                {col.id === POOL ? (
                  division.data && isPositive(division.data.sin_asignar) ? (
                    <p className="text-sm text-fg-3">
                      Sin repartir <Money value={division.data.sin_asignar} simbolo={simbolo} />
                    </p>
                  ) : null
                ) : (
                  <footer className="flex flex-col gap-3 border-t border-line pt-3">
                    <Money value={parte?.monto ?? "0.00"} simbolo={simbolo} size="s" roll />
                    {parte && <CobrarParte comanda={c} etiqueta={parte.etiqueta} falta={remaining(parte.monto, parte.pagado)} pagado={parte.pagado} simbolo={simbolo} />}
                  </footer>
                )}
              </section>
            );
          })}
          <button
            type="button"
            onClick={agregarPersona}
            className="flex min-h-80 w-40 shrink-0 flex-col items-center justify-center gap-2 rounded-sheet border border-dashed border-line-strong text-fg-2 transition-colors hover:bg-wash hover:text-fg"
          >
            <Plus size={20} strokeWidth={1.5} aria-hidden />
            Persona
          </button>
        </div>
      </LayoutGroup>
    </div>
  );
}

function Ficha({
  item,
  columnas,
  actual,
  onMover,
  simbolo,
}: {
  item: Item;
  columnas: { id: string; nombre: string }[];
  actual: string;
  onMover: (destino: string) => void;
  simbolo?: string;
}) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const [open, setOpen] = useState(false);
  // El click que sigue a un arrastre no debe abrir el menú
  const arrastrado = useRef(false);
  const ref = useRef<HTMLLIElement>(null);

  function soltar(info: PanInfo) {
    // El punto viene en coordenadas de página; elementsFromPoint usa las del viewport
    // La ficha arrastrada está bajo el puntero (y sigue dentro de su columna de origen): se ignora
    const capas = document
      .elementsFromPoint(info.point.x - window.scrollX, info.point.y - window.scrollY)
      .filter((el) => !ref.current?.contains(el));
    const destino = capas.map((el) => el.closest<HTMLElement>("[data-columna]")?.dataset.columna).find(Boolean);
    if (destino && destino !== actual) onMover(destino);
    x.set(0);
    y.set(0);
    setTimeout(() => (arrastrado.current = false), 0);
  }

  return (
    <motion.li
      ref={ref}
      layout
      layoutId={`ficha-${item.id}`}
      transition={smooth}
      style={{ x, y }}
      drag
      dragMomentum={false}
      whileDrag={{ scale: 1.05, zIndex: 20, cursor: "grabbing", boxShadow: "var(--shadow-float)" }}
      onDragStart={() => (arrastrado.current = true)}
      onDragEnd={(_, info) => soltar(info)}
      className="touch-none rounded-control"
    >
      <DM.Root open={open} onOpenChange={setOpen}>
        <DM.Trigger
          asChild
          // Radix abre en pointerdown, lo que chocaría con el arrastre: con puntero se abre
          // en click (si no hubo arrastre); el teclado sigue usando el manejo de Radix
          onPointerDown={(e) => e.preventDefault()}
          onClick={(e) => {
            if (e.detail > 0 && !arrastrado.current) setOpen((o) => !o);
          }}
        >
          <motion.button
            type="button"
            whileTap={{ scale: 0.98 }}
            transition={snappy}
            className="flex w-full cursor-grab items-baseline justify-between gap-3 rounded-control bg-wash-strong px-3 py-2.5 text-left"
          >
            <span className="min-w-0 truncate text-base font-medium">{item.nombre}</span>
            <Money value={item.precio_unitario} simbolo={simbolo} className="shrink-0 text-sm text-fg-2" />
          </motion.button>
        </DM.Trigger>
        <DM.Portal>
          <DM.Content align="start" sideOffset={6} className={menuContent}>
            <DM.Label className="eyebrow px-2.5 py-1.5">Mover a</DM.Label>
            {columnas
              .filter((col) => col.id !== actual)
              .map((col) => (
                <DM.Item key={col.id} className={menuItem} onSelect={() => onMover(col.id)}>
                  {col.nombre}
                </DM.Item>
              ))}
          </DM.Content>
        </DM.Portal>
      </DM.Root>
    </motion.li>
  );
}
