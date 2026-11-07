"use client";

import Big from "big.js";
import { useQuery } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { TextArea } from "@/components/ui/TextArea";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { cantidad } from "@/features/inventario/unidad";
import { useUnidades } from "@/features/inventario/useUnidades";
import { api } from "@/lib/api/client";
import { formatAmount } from "@/lib/money";
import type { ErrorView } from "@/lib/api/errors";
import { InsumoOut, RecetaOut, type Receta } from "@/lib/api/schemas";

const DEC = /^\d+([.,]\d{1,3})?$/;

export default function RecetasPage() {
  const { data: me } = useMe();
  const un = useUnidades();
  const lista = useQuery({ queryKey: ["recetas"], queryFn: () => api("/recetas", { schema: z.array(RecetaOut) }), enabled: can(me, "recetas") });
  const form = useFormSheet<Receta>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [borrar, setBorrar] = useState<Receta | null>(null);
  const inv = [["recetas"], ["menu"]];
  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/recetas/${v.id}` : "/recetas"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: inv,
    ok: (v) => (v.id ? "Receta actualizada" : "Receta creada"),
    onDone: form.cerrar,
    onError: setError,
  });
  const eliminar = useApiMutation<Receta>({ path: (r) => `/recetas/${r.id}`, method: "DELETE", body: () => undefined, invalidate: inv, ok: "Receta eliminada", onDone: () => setBorrar(null) });

  if (!can(me, "recetas")) return <SinAcceso />;
  return (
    <>
      <PageHeader title="Recetas" actions={can(me, "recetas", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nueva receta</Button>} />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">Lo que lleva cada porción. Con ellas el menú sabe cuántas porciones quedan y cocina descuenta el stock al marcar listo.</p>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.length === 0 ? (
        <EmptyState title="Sin recetas" description="Crea la receta de un plato y asígnala al producto para controlar su stock." />
      ) : (
        <ul className="grid gap-x-12 tablet:grid-cols-2">
          {lista.data.map((r) => (
            <li key={r.id} className={`flex flex-col gap-3 border-t border-line py-6 ${r.activa ? "" : "opacity-50"}`}>
              <div className="flex items-baseline justify-between gap-4">
                <button type="button" disabled={!can(me, "recetas", "editar")} onClick={() => (setError(null), form.abrir(r))} className="text-left font-display text-display-s leading-none hover:underline disabled:hover:no-underline">
                  {r.nombre}
                  <span className="ml-3 align-middle font-sans text-sm font-normal tabular text-fg-3">
                    {r.codigo}
                    {r.costo && ` · costo ${formatAmount(r.costo)}`}
                  </span>
                </button>
                {can(me, "recetas", "eliminar") && (
                  <Button size="sm" variant="ghost" onClick={() => setBorrar(r)}>
                    Eliminar
                  </Button>
                )}
              </div>
              {r.descripcion && <p className="text-sm text-fg-3">{r.descripcion}</p>}
              <ul className="flex flex-col gap-1 text-base text-fg-2">
                {r.ingredientes.map((i) => (
                  <li key={i.insumo_id} className="flex justify-between gap-4">
                    <span>{i.insumo}</span>
                    <span className="tabular">
                      {cantidad(i.cantidad)} {un.abrev(i.unidad)}
                    </span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {form.state && <RecetaForm state={form.state} onOpenChange={form.onOpenChange} pending={guardar.isPending} error={error} setError={setError} onGuardar={(v) => guardar.mutate(v)} />}
      <Confirmar
        open={borrar !== null}
        onOpenChange={(o) => !o && setBorrar(null)}
        title={`¿Eliminar la receta ${borrar?.nombre ?? ""}?`}
        description="Solo se puede si ningún producto la usa."
        accion="Eliminar"
        pending={eliminar.isPending}
        onConfirm={() => borrar && eliminar.mutate(borrar)}
      />
    </>
  );
}

function RecetaForm({
  state,
  onOpenChange,
  pending,
  error,
  setError,
  onGuardar,
}: {
  state: { item: Receta | null; key: number; open: boolean };
  onOpenChange: (o: boolean) => void;
  pending: boolean;
  error: ErrorView | null;
  setError: (e: ErrorView | null) => void;
  onGuardar: (v: { id?: number; body: Record<string, unknown> }) => void;
}) {
  const un = useUnidades();
  const insumos = useQuery({ queryKey: ["insumos"], queryFn: () => api("/insumos", { schema: z.array(InsumoOut) }) });
  const [filas, setFilas] = useState(() =>
    state.item ? state.item.ingredientes.map((i, n) => ({ k: n, insumo_id: String(i.insumo_id), cantidad: cantidad(i.cantidad).replace(/\./g, ""), removible: i.removible, sub: false })) : [{ k: 0, insumo_id: "", cantidad: "", removible: true, sub: false }],
  );
  const [seq, setSeq] = useState(filas.length);
  const r = state.item;
  return (
    <FormSheet
      key={state.key}
      open={state.open}
      onOpenChange={onOpenChange}
      title={r ? r.nombre : "Nueva receta"}
      pending={pending}
      error={error}
      onClearError={() => setError(null)}
      onSubmit={(f) => {
        const nombre = txt(f, "nombre");
        // En un insumo de kg o L se puede escribir en g o ml: se convierte a la unidad del insumo
        const ingredientes = filas
          .filter((x) => x.insumo_id)
          .map((x) => {
            const c = x.cantidad.replace(",", ".");
            const sub = un.sub(insumos.data?.find((i) => String(i.id) === x.insumo_id)?.unidad ?? "");
            return { insumo_id: Number(x.insumo_id), cantidad: x.sub && sub && DEC.test(c) ? new Big(c).div(sub.factor).toFixed(3) : c, removible: x.removible };
          });
        if (!nombre) return setError({ title: "Ponle un nombre", tone: "warn" });
        if (ingredientes.length === 0) return setError({ title: "Agrega al menos un ingrediente", tone: "warn" });
        if (ingredientes.some((i) => !DEC.test(i.cantidad) || Number(i.cantidad.replace(",", ".")) === 0)) return setError({ title: "Revisa las cantidades (mayores que cero)", tone: "warn" });
        if (new Set(ingredientes.map((i) => i.insumo_id)).size !== ingredientes.length) return setError({ title: "Un insumo está repetido", tone: "warn" });
        const codigo = txt(f, "codigo")?.toUpperCase();
        const body = { nombre, descripcion: txt(f, "descripcion"), activa: bool(f, "activa"), ingredientes, ...(codigo ? { codigo } : {}) };
        onGuardar(r ? { id: r.id, body } : { body });
      }}
    >
      <Field name="nombre" label="Nombre" defaultValue={r?.nombre ?? ""} maxLength={120} autoFocus />
      <Field name="codigo" label="Código interno" defaultValue={r?.codigo ?? ""} maxLength={30} placeholder="Automático (REC-0001)" />
      <TextArea name="descripcion" label="Descripción" defaultValue={r?.descripcion ?? ""} maxLength={2000} />
      <fieldset className="flex flex-col gap-3">
        <legend className="eyebrow pb-2">Ingredientes por porción</legend>
        {filas.map((fila) => {
          const unidad = insumos.data?.find((i) => String(i.id) === fila.insumo_id)?.unidad;
          return (
            <div key={fila.k} className="flex items-end gap-3">
              <select
                aria-label="Insumo"
                value={fila.insumo_id}
                onChange={(e) => setFilas((fs) => fs.map((x) => (x.k === fila.k ? { ...x, insumo_id: e.target.value } : x)))}
                className="h-11 min-w-0 flex-1 border-b border-line-strong bg-transparent text-base outline-none focus:border-paper [&>option]:bg-overlay"
              >
                <option value="">Elige insumo…</option>
                {insumos.data?.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.nombre}
                  </option>
                ))}
              </select>
              <input
                aria-label="Cantidad"
                inputMode="decimal"
                value={fila.cantidad}
                onChange={(e) => setFilas((fs) => fs.map((x) => (x.k === fila.k ? { ...x, cantidad: e.target.value } : x)))}
                placeholder="150"
                className="h-11 w-20 border-b border-line-strong bg-transparent text-right text-base tabular outline-none focus:border-paper"
              />
              {unidad && un.sub(unidad) ? (
                <select
                  aria-label="Unidad"
                  value={fila.sub ? "sub" : "base"}
                  onChange={(e) => setFilas((fs) => fs.map((x) => (x.k === fila.k ? { ...x, sub: e.target.value === "sub" } : x)))}
                  className="h-11 w-14 border-b border-line-strong bg-transparent text-sm outline-none focus:border-paper [&>option]:bg-overlay"
                >
                  <option value="base">{un.abrev(unidad)}</option>
                  <option value="sub">{un.sub(unidad)?.abrev}</option>
                </select>
              ) : (
                <span className="w-6 pb-3 text-sm text-fg-3">{unidad ? un.abrev(unidad) : ""}</span>
              )}
              <label className="mb-2.5 flex items-center gap-1.5 text-xs text-fg-3" title="El cliente puede pedir el plato sin este ingrediente">
                <input type="checkbox" checked={fila.removible} onChange={(e) => setFilas((fs) => fs.map((x) => (x.k === fila.k ? { ...x, removible: e.target.checked } : x)))} />
                Quitable
              </label>
              <button type="button" aria-label="Quitar ingrediente" onClick={() => setFilas((fs) => fs.filter((x) => x.k !== fila.k))} className="mb-1.5 grid size-8 place-items-center rounded-md text-fg-3 hover:bg-wash hover:text-fg">
                <X size={16} strokeWidth={1.5} />
              </button>
            </div>
          );
        })}
        <Button
          size="sm"
          variant="ghost"
          className="self-start px-0"
          onClick={() => {
            setFilas((fs) => [...fs, { k: seq, insumo_id: "", cantidad: "", removible: true, sub: false }]);
            setSeq((s) => s + 1);
          }}
        >
          <Plus size={14} strokeWidth={1.5} aria-hidden /> Ingrediente
        </Button>
      </fieldset>
      <Toggle name="activa" label="Activa" defaultChecked={r?.activa ?? true} />
    </FormSheet>
  );
}
