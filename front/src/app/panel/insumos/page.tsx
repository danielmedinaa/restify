"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import Big from "big.js";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, cambios, Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { toast } from "@/components/ui/Toast";
import { FACTOR_COSTO, POR_COSTO, useUnidades } from "@/features/inventario/useUnidades";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { InsumoOut, type Insumo } from "@/lib/api/schemas";
import { formatAmount, parseAmountInput } from "@/lib/money";
import { cantidad } from "@/features/inventario/unidad";

interface FilaPres {
  k: number;
  nombre: string;
  cantidad: string;
}

/** Costo guardado por g/ml/kg/L/unidad -> por kg/L/unidad, como se piensa en cocina. */
function costoVisible(costo: string, unidad: string): string {
  return new Big(costo).times(FACTOR_COSTO[unidad] ?? 1).toFixed(2);
}

export default function InsumosPage() {
  const { data: me } = useMe();
  const lista = useQuery({ queryKey: ["insumos"], queryFn: () => api("/insumos", { schema: z.array(InsumoOut) }), enabled: can(me, "insumos") });
  const form = useFormSheet<Insumo>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [baja, setBaja] = useState<Insumo | null>(null);
  const un = useUnidades();
  const qc = useQueryClient();
  const [pres, setPres] = useState<FilaPres[]>([]);
  const abrirForm = (i: Insumo | null) => {
    setError(null);
    setPres(i ? i.presentaciones.map((p, k) => ({ k, nombre: p.nombre, cantidad: cantidad(p.cantidad).replace(/\./g, "") })) : []);
    form.abrir(i);
  };
  // Guarda el insumo y, si cambió la lista, sus presentaciones de reposición
  const guardar = useMutation({
    mutationFn: async (v: { id?: number; body: Record<string, unknown>; pres: { nombre: string; cantidad: string }[] }) => {
      const ins = await api(v.id ? `/insumos/${v.id}` : "/insumos", { method: v.id ? "PATCH" : "POST", body: v.body, schema: InsumoOut });
      return v.pres.length || (v.id && lista.data?.find((x) => x.id === v.id)?.presentaciones.length)
        ? api(`/insumos/${ins.id}/presentaciones`, { method: "PUT", body: { presentaciones: v.pres }, schema: InsumoOut })
        : ins;
    },
    onSuccess: (_, v) => {
      toast({ title: v.id ? "Insumo actualizado" : "Insumo creado", tone: "ok" });
      void qc.invalidateQueries({ queryKey: ["insumos"] });
      void qc.invalidateQueries({ queryKey: ["inventario"] });
      form.cerrar();
    },
    onError: (e) => setError(describeError(e)),
  });
  const desactivar = useApiMutation<Insumo>({ path: (i) => `/insumos/${i.id}`, method: "DELETE", body: () => undefined, invalidate: [["insumos"]], ok: "Insumo desactivado", onDone: () => setBaja(null) });

  if (!can(me, "insumos")) return <SinAcceso />;
  return (
    <>
      <PageHeader title="Insumos" actions={can(me, "insumos", "crear") && <Button onClick={() => abrirForm(null)}>Nuevo insumo</Button>} />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">La materia prima de las recetas. El stock de cada insumo se lleva por sucursal en Existencias.</p>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.length === 0 ? (
        <EmptyState title="Sin insumos" description="Carga carne, pan, queso… lo que usan tus recetas." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Código</Th>
              <Th>Insumo</Th>
              <Th>Se mide en</Th>
              <Th align="right">Costo</Th>
              <Th>Estado</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.map((i) => (
              <Tr key={i.id} className={i.activo ? "" : "opacity-50"}>
                <Td className="whitespace-nowrap font-mono text-sm text-fg-2">
                  {i.codigo}
                  {i.codigo_barras && <span className="block text-fg-4">{i.codigo_barras}</span>}
                </Td>
                <Td>
                  <button type="button" disabled={!can(me, "insumos", "editar")} onClick={() => abrirForm(i)} className="font-medium hover:underline disabled:hover:no-underline">
                    {i.nombre}
                  </button>
                </Td>
                <Td className="text-fg-2">{un.nombre(i.unidad)}</Td>
                <Td align="right" className="tabular text-fg-2">
                  {i.costo_unitario ? `${formatAmount(costoVisible(i.costo_unitario, i.unidad))} / ${POR_COSTO[i.unidad] ?? un.abrev(i.unidad)}` : <span className="text-fg-4">—</span>}
                </Td>
                <Td>
                  <StatusDot tone={i.activo ? "ok" : "muted"}>{i.activo ? "Activo" : "Inactivo"}</StatusDot>
                </Td>
                <Td align="right" className="whitespace-nowrap">
                  <a
                    href={`/bff/panel/insumos/${i.id}/etiqueta`}
                    target="_blank"
                    rel="noopener"
                    className="inline-flex h-8 items-center rounded-control px-3 text-sm text-fg-2 hover:bg-wash hover:text-fg"
                  >
                    Etiqueta QR
                  </a>
                  {i.activo && can(me, "insumos", "eliminar") && (
                    <Button size="sm" variant="danger" onClick={() => setBaja(i)}>
                      Desactivar
                    </Button>
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
      {form.state && (
        <FormSheet
          key={form.state.key}
          open={form.state.open}
          onOpenChange={form.onOpenChange}
          title={form.state.item ? form.state.item.nombre : "Nuevo insumo"}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const i = form.state?.item ?? null;
            const codigo = txt(f, "codigo")?.toUpperCase() ?? null;
            const datos: Record<string, unknown> = {
              nombre: txt(f, "nombre"),
              unidad: f.get("unidad"),
              activo: bool(f, "activo"),
              codigo_barras: txt(f, "codigo_barras"),
            };
            // El costo se escribe por kg / litro / unidad y se guarda por la unidad del insumo
            const costo = parseAmountInput(txt(f, "costo") ?? "");
            const unidad = String(f.get("unidad") ?? "g");
            if (costo) datos.costo_unitario = new Big(costo).div(FACTOR_COSTO[unidad] ?? 1).toFixed(6);
            const envases = pres.filter((p) => p.nombre.trim() || p.cantidad.trim()).map((p) => ({ nombre: p.nombre.trim(), cantidad: p.cantidad.trim().replace(",", ".") }));
            if (envases.some((p) => !p.nombre || !/^\d+(\.\d{1,3})?$/.test(p.cantidad) || Number(p.cantidad) <= 0)) return setError({ title: "Cada presentación necesita nombre y una cantidad mayor que cero", tone: "warn" });
            if (new Set(envases.map((p) => p.nombre.toLowerCase())).size !== envases.length) return setError({ title: "Hay presentaciones con el mismo nombre", tone: "warn" });
            // Vacío al crear = lo genera el sistema; al editar no se puede dejar sin código
            if (codigo) datos.codigo = codigo;
            if (!datos.nombre) return setError({ title: "Ponle un nombre", tone: "warn" });
            guardar.mutate(i ? { id: i.id, body: cambios(i, datos), pres: envases } : { body: datos, pres: envases });
          }}
        >
          <Field name="nombre" label="Nombre" defaultValue={form.state.item?.nombre ?? ""} maxLength={120} autoFocus />
          <div className="grid grid-cols-2 gap-4">
            <Field
              name="codigo"
              label="Código interno"
              defaultValue={form.state.item?.codigo ?? ""}
              maxLength={30}
              placeholder="Automático"
              hint={form.state.item ? undefined : "Vacío: INS-0001…"}
            />
            <Field name="codigo_barras" label="Código de barras" defaultValue={form.state.item?.codigo_barras ?? ""} maxLength={64} inputMode="numeric" placeholder="Opcional" />
          </div>
          <Select name="unidad" label="Se mide en" defaultValue={form.state.item?.unidad ?? "g"} hint="¿Falta una? Créala en Unidades de medida.">
            {un.lista
              .filter((u) => u.activa || u.codigo === form.state?.item?.unidad)
              .map((u) => (
                <option key={u.codigo} value={u.codigo}>
                  {u.nombre.charAt(0).toUpperCase() + u.nombre.slice(1)} ({u.abreviatura})
                </option>
              ))}
          </Select>
          <Field
            name="costo"
            label="Costo por unidad de medida"
            inputMode="decimal"
            defaultValue={form.state.item?.costo_unitario ? costoVisible(form.state.item.costo_unitario, form.state.item.unidad).replace(".", ",") : ""}
            placeholder="Opcional"
            hint="En la moneda principal (g y ml se escriben por kg y L). Cada compra lo actualiza solo; sirve para el margen."
          />
          <fieldset className="flex flex-col gap-3">
            <legend className="eyebrow pb-1">Presentaciones al reponer</legend>
            <p className="text-sm text-fg-3">Cómo llega el insumo: “Caja x24” = 24, “Saco” = 50… Al reponer o comprar eliges la presentación y cuentas envases, sin hacer la cuenta.</p>
            {pres.map((p) => (
              <div key={p.k} className="flex items-end gap-3">
                <input aria-label="Nombre de la presentación" value={p.nombre} maxLength={80} placeholder="Caja x24" onChange={(e) => setPres((ps) => ps.map((x) => (x.k === p.k ? { ...x, nombre: e.target.value } : x)))} className="h-11 min-w-0 flex-1 border-b border-line-strong bg-transparent text-base outline-none focus:border-paper" />
                <input aria-label="Cantidad que trae" inputMode="decimal" value={p.cantidad} placeholder="24" onChange={(e) => setPres((ps) => ps.map((x) => (x.k === p.k ? { ...x, cantidad: e.target.value } : x)))} className="h-11 w-24 border-b border-line-strong bg-transparent text-right text-base tabular outline-none focus:border-paper" />
                <span className="w-8 pb-3 text-sm text-fg-3">{un.abrev(form.state?.item?.unidad ?? "")}</span>
                <button type="button" aria-label="Quitar presentación" onClick={() => setPres((ps) => ps.filter((x) => x.k !== p.k))} className="mb-1.5 grid size-8 place-items-center rounded-md text-fg-3 hover:bg-wash hover:text-fg">
                  <X size={16} strokeWidth={1.5} />
                </button>
              </div>
            ))}
            <Button type="button" size="sm" variant="ghost" className="self-start px-0" onClick={() => setPres((ps) => [...ps, { k: Math.max(-1, ...ps.map((x) => x.k)) + 1, nombre: "", cantidad: "" }])}>
              <Plus size={14} strokeWidth={1.5} aria-hidden /> Presentación
            </Button>
          </fieldset>
          <Toggle name="activo" label="Activo" defaultChecked={form.state.item?.activo ?? true} />
        </FormSheet>
      )}
      <Confirmar
        open={baja !== null}
        onOpenChange={(o) => !o && setBaja(null)}
        title={`¿Desactivar ${baja?.nombre ?? ""}?`}
        description="Deja de estar disponible para recetas nuevas. El histórico se conserva."
        accion="Desactivar"
        pending={desactivar.isPending}
        onConfirm={() => baja && desactivar.mutate(baja)}
      />
    </>
  );
}
