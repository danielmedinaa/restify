"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Big from "big.js";
import { Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { Sheet } from "@/components/ui/Sheet";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { can, useMe } from "@/features/auth/useMe";
import { FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { cantidad } from "@/features/inventario/unidad";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { InsumoOut, InventarioOut, MovimientoOut, Pagina, type Inventario } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

type Operacion = "entrada" | "merma" | "ajuste" | "minimo";
const TITULO: Record<Operacion, string> = { entrada: "Entrada", merma: "Merma", ajuste: "Conteo físico", minimo: "Stock mínimo" };
const AYUDA: Record<Operacion, string> = {
  entrada: "Lo que llegó (compra, traspaso). Se suma al stock.",
  merma: "Lo que se perdió o venció. Se resta del stock.",
  ajuste: "Lo que contaste en la cocina. Reemplaza el stock por este número.",
  minimo: "Al llegar a este número, el sistema avisa en tiempo real.",
};
const fecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const DEC = /^\d+([.,]\d{1,3})?$/;

/** Ancho de la barra de nivel: disponible frente a 3 veces el mínimo (decimal exacto, solo para dibujar). */
function nivel(i: Inventario): number {
  const tope = new Big(i.stock_minimo).times(3);
  if (tope.lte(0)) return 1;
  const r = new Big(i.disponible).div(tope);
  return r.gt(1) ? 1 : r.lt(0) ? 0 : Number(r.toFixed(3));
}

export default function InventarioPage() {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const [q, setQ] = useState("");
  const termino = useDeferredValue(q.trim());
  const [filtro, setFiltro] = useState<"todos" | "bajo">("todos");
  const lista = useQuery({
    queryKey: ["inventario", "sucursal", actual?.id, termino, filtro],
    queryFn: () => api("/inventario", { query: { sucursal_id: actual?.id, q: termino, bajo_minimo: filtro === "bajo" ? true : undefined, limite: 100 }, schema: Pagina(InventarioOut) }),
    enabled: !!actual && can(me, "inventario"),
    placeholderData: keepPreviousData,
  });
  const op = useFormSheet<{ inv: Inventario; tipo: Operacion }>();
  const alta = useFormSheet<null>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [historial, setHistorial] = useState<Inventario | null>(null);
  const inv = [["inventario"], ["alertas"], ["menu"]];

  const mover = useApiMutation<{ id: number; tipo: Operacion; body: Record<string, unknown> }>({
    path: (v) => (v.tipo === "minimo" ? `/inventario/${v.id}` : `/inventario/${v.id}/${v.tipo}`),
    method: (v) => (v.tipo === "minimo" ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: inv,
    ok: (v) => `${TITULO[v.tipo]} registrada`,
    onDone: op.cerrar,
    onError: setError,
  });
  const crear = useApiMutation<Record<string, unknown>>({ path: () => "/inventario", method: "POST", invalidate: inv, ok: "Insumo agregado a la sucursal", onDone: alta.cerrar, onError: setError });

  if (!can(me, "inventario")) return <SinAcceso />;
  const editar = can(me, "inventario", "editar");

  return (
    <>
      <PageHeader
        eyebrow={actual?.nombre}
        title="Existencias"
        actions={
          <>
            <Segmented
              label="Filtro"
              value={filtro}
              onChange={setFiltro}
              options={[
                { value: "todos", label: "Todo" },
                { value: "bajo", label: "Bajo mínimo" },
              ]}
            />
            {can(me, "inventario", "crear") && <Button onClick={() => (setError(null), alta.abrir(null))}>Agregar insumo</Button>}
          </>
        }
      />
      <label className="mb-10 flex max-w-md items-center gap-3 border-b border-line-strong focus-within:border-paper">
        <Search size={18} strokeWidth={1.5} className="text-fg-3" aria-hidden />
        <span className="sr-only">Buscar insumo</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar insumo" className="h-12 w-full bg-transparent text-lead outline-none placeholder:text-fg-4 focus-visible:outline-none" />
      </label>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.items.length === 0 ? (
        <EmptyState
          title={filtro === "bajo" ? "Todo en orden" : "Sin existencias"}
          description={filtro === "bajo" ? "Ningún insumo está en el mínimo." : "Agrega los insumos que maneja esta sucursal y su stock inicial."}
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Insumo</Th>
              <Th align="right">Disponible</Th>
              <Th align="right">Reservado</Th>
              <Th align="right">Mínimo</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.items.map((i) => {
              const u = i.insumo.unidad_abreviatura;
              return (
                <Tr key={i.id}>
                  <Td className="min-w-48">
                    <button type="button" onClick={() => setHistorial(i)} className="flex flex-col gap-2 text-left">
                      <span className="font-medium hover:underline">{i.insumo.nombre}</span>
                      <span aria-hidden className="block h-px w-40 bg-line">
                        <span className={cn("block h-full", i.bajo_minimo ? "bg-warn" : "bg-fg-3")} style={{ width: `${nivel(i) * 100}%` }} />
                      </span>
                    </button>
                  </Td>
                  <Td align="right">
                    <span className={cn("font-display text-display-s leading-none", i.bajo_minimo && "text-warn")}>{cantidad(i.disponible)}</span>
                    <span className="ml-1 text-sm text-fg-3">{u}</span>
                    {i.bajo_minimo && <span className="sr-only"> (bajo el mínimo)</span>}
                  </Td>
                  <Td align="right" className="text-fg-2">
                    {cantidad(i.reservado)} {u}
                  </Td>
                  <Td align="right" className="text-fg-2">
                    {cantidad(i.stock_minimo)} {u}
                  </Td>
                  <Td align="right">
                    {editar && (
                      <div className="flex justify-end gap-1">
                        {(["entrada", "merma", "ajuste", "minimo"] as const).map((t) => (
                          <Button key={t} size="sm" variant={t === "entrada" ? "line" : "ghost"} onClick={() => (setError(null), op.abrir({ inv: i, tipo: t }))}>
                            {t === "minimo" ? "Mínimo" : TITULO[t]}
                          </Button>
                        ))}
                      </div>
                    )}
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
      )}

      {op.state?.item && (
        <FormSheet
          key={op.state.key}
          open={op.state.open}
          onOpenChange={op.onOpenChange}
          title={`${TITULO[op.state.item.tipo]} · ${op.state.item.inv.insumo.nombre}`}
          description={AYUDA[op.state.item.tipo]}
          pending={mover.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const it = op.state?.item;
            if (!it) return;
            const valor = (txt(f, "cantidad") ?? "").replace(",", ".");
            const motivo = txt(f, "motivo");
            if (!DEC.test(valor)) return setError({ title: "Escribe una cantidad válida (hasta 3 decimales)", tone: "warn" });
            if (it.tipo === "ajuste" && (!motivo || motivo.length < 3)) return setError({ title: "El conteo físico necesita un motivo", tone: "warn" });
            const pres = it.tipo === "entrada" ? txt(f, "presentacion_id") : null;
            if (pres && !/^\d+$/.test(valor)) return setError({ title: "Las presentaciones se cuentan en envases enteros", tone: "warn" });
            if (!it.inv.insumo.permite_decimales && !/^\d+$/.test(valor)) return setError({ title: `${it.inv.insumo.nombre} se cuenta en ${it.inv.insumo.unidad_abreviatura} enteras`, tone: "warn" });
            const body =
              it.tipo === "minimo" ? { stock_minimo: valor } : it.tipo === "ajuste" ? { cantidad_real: valor, motivo } : { cantidad: valor, motivo, ...(pres ? { presentacion_id: Number(pres) } : {}) };
            mover.mutate({ id: it.inv.id, tipo: it.tipo, body });
          }}
        >
          <p className="text-base text-fg-2">
            Hoy: {cantidad(op.state.item.inv.cantidad)} {op.state.item.inv.insumo.unidad_abreviatura} en stock, {cantidad(op.state.item.inv.reservado)} reservados para cocina.
          </p>
          {op.state.item.tipo === "entrada" && op.state.item.inv.insumo.presentaciones.length > 0 && (
            <Select name="presentacion_id" label="Llegó en" defaultValue="">
              <option value="">{op.state.item.inv.insumo.unidad_abreviatura} sueltas</option>
              {op.state.item.inv.insumo.presentaciones.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre} ({cantidad(p.cantidad)} {op.state?.item?.inv.insumo.unidad_abreviatura})
                </option>
              ))}
            </Select>
          )}
          <Field
            name="cantidad"
            label={op.state.item.tipo === "ajuste" ? "Cantidad contada" : op.state.item.tipo === "minimo" ? "Mínimo" : "Cantidad"}
            inputMode="decimal"
            defaultValue={op.state.item.tipo === "minimo" ? cantidad(op.state.item.inv.stock_minimo).replace(/\./g, "") : ""}
            hint={op.state.item.tipo === "entrada" && op.state.item.inv.insumo.presentaciones.length > 0 ? "Cuántos envases (si elegiste una presentación) o cuántas unidades sueltas" : `En ${op.state.item.inv.insumo.unidad_abreviatura}`}
            autoFocus
          />
          {op.state.item.tipo !== "minimo" && <Field name="motivo" label="Motivo" maxLength={255} placeholder={op.state.item.tipo === "entrada" ? "Compra a proveedor" : "Se venció, conteo semanal…"} />}
        </FormSheet>
      )}

      {alta.state && actual && <AltaInventario state={alta.state} onOpenChange={alta.onOpenChange} sucursalId={actual.id} existentes={lista.data?.items ?? []} pending={crear.isPending} error={error} setError={setError} onCrear={(b) => crear.mutate(b)} />}

      <Movimientos inv={historial} onClose={() => setHistorial(null)} />
    </>
  );
}

function AltaInventario({
  state,
  onOpenChange,
  sucursalId,
  existentes,
  pending,
  error,
  setError,
  onCrear,
}: {
  state: { key: number; open: boolean };
  onOpenChange: (o: boolean) => void;
  sucursalId: number;
  existentes: Inventario[];
  pending: boolean;
  error: ErrorView | null;
  setError: (e: ErrorView | null) => void;
  onCrear: (body: Record<string, unknown>) => void;
}) {
  const insumos = useQuery({ queryKey: ["insumos"], queryFn: () => api("/insumos", { query: { activo: true }, schema: z.array(InsumoOut) }) });
  const libres = (insumos.data ?? []).filter((i) => !existentes.some((e) => e.insumo.id === i.id));
  return (
    <FormSheet
      key={state.key}
      open={state.open}
      onOpenChange={onOpenChange}
      title="Agregar insumo a la sucursal"
      pending={pending}
      error={error}
      onClearError={() => setError(null)}
      submitLabel="Agregar"
      onSubmit={(f) => {
        const insumo = txt(f, "insumo_id");
        const cant = (txt(f, "cantidad") ?? "0").replace(",", ".");
        const min = (txt(f, "stock_minimo") ?? "0").replace(",", ".");
        if (!insumo) return setError({ title: "Elige un insumo", tone: "warn" });
        if (!DEC.test(cant) || !DEC.test(min)) return setError({ title: "Cantidades inválidas", tone: "warn" });
        onCrear({ sucursal_id: sucursalId, insumo_id: Number(insumo), cantidad: cant, stock_minimo: min });
      }}
    >
      {libres.length === 0 && !insumos.isPending ? (
        <p className="text-base text-fg-2">Todos los insumos activos ya están en esta sucursal. Crea uno nuevo en Insumos.</p>
      ) : (
        <Select name="insumo_id" label="Insumo" defaultValue="">
          <option value="" disabled>
            Elige…
          </option>
          {libres.map((i) => (
            <option key={i.id} value={i.id}>
              {i.nombre} ({i.unidad_abreviatura})
            </option>
          ))}
        </Select>
      )}
      <Field name="cantidad" label="Stock inicial" inputMode="decimal" defaultValue="0" />
      <Field name="stock_minimo" label="Stock mínimo" inputMode="decimal" defaultValue="0" />
    </FormSheet>
  );
}

const TIPO_MOV = { entrada: "Entrada", ajuste: "Ajuste", merma: "Merma", consumo: "Consumo" } as const;

function Movimientos({ inv, onClose }: { inv: Inventario | null; onClose: () => void }) {
  const [ultimo, setUltimo] = useState(inv);
  if (inv && inv !== ultimo) setUltimo(inv);
  const i = inv ?? ultimo;
  const movs = useQuery({
    queryKey: ["inventario", "movimientos", i?.id],
    queryFn: () => api(`/inventario/${i!.id}/movimientos`, { query: { limite: 100 }, schema: Pagina(MovimientoOut) }),
    enabled: !!inv,
  });
  if (!i) return null;
  const u = i.insumo.unidad_abreviatura;
  return (
    <Sheet open={inv !== null} onOpenChange={(o) => !o && onClose()} side="right" title={i.insumo.nombre} description="Movimientos de stock, del más reciente al más antiguo.">
      {movs.isPending ? (
        <ListLoading rows={5} />
      ) : movs.isError ? (
        <ListError error={movs.error} />
      ) : movs.data.items.length === 0 ? (
        <p className="pt-4 text-base text-fg-3">Sin movimientos todavía.</p>
      ) : (
        <ul className="flex flex-col">
          {movs.data.items.map((m) => (
            <li key={m.id} className="flex items-baseline justify-between gap-4 border-t border-line py-3">
              <span className="flex flex-col">
                <span className="text-base">
                  {TIPO_MOV[m.tipo]}
                  {m.comanda_item_id && <span className="text-fg-3"> · plato {m.comanda_item_id}</span>}
                </span>
                <span className="text-sm text-fg-3">
                  {fecha.format(new Date(m.created_at))}
                  {m.motivo ? ` · ${m.motivo}` : ""}
                </span>
              </span>
              <span className="flex flex-col items-end">
                <span className={cn("tabular", m.cantidad.startsWith("-") ? "text-fg-2" : "text-fg")}>
                  {m.cantidad.startsWith("-") ? "−" : "+"}
                  {cantidad(m.cantidad.replace("-", ""))} {u}
                </span>
                <span className="text-sm tabular text-fg-3">
                  queda {cantidad(m.saldo)} {u}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
