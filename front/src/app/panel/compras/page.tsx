"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Big from "big.js";
import { Plus, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Money } from "@/components/ui/Money";
import { Select } from "@/components/ui/Select";
import { Sheet } from "@/components/ui/Sheet";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { useMonedas } from "@/features/comandas/queries";
import { cantidad } from "@/features/inventario/unidad";
import { useUnidades } from "@/features/inventario/useUnidades";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { CompraOut, InsumoOut, Pagina, ProveedorOut, type Compra } from "@/lib/api/schemas";
import { parseAmountInput } from "@/lib/money";

const fecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", year: "numeric" });

export default function ComprasPage() {
  const { data: me } = useMe();
  const { abrev } = useUnidades();
  const { actual } = useSucursal();
  const [nueva, setNueva] = useState(false);
  const [detalle, setDetalle] = useState<Compra | null>(null);
  const lista = useQuery({
    queryKey: ["compras", actual?.id],
    queryFn: () => api("/compras", { query: { sucursal_id: actual!.id, limite: 100 }, schema: Pagina(CompraOut) }),
    enabled: !!actual && can(me, "compras"),
    placeholderData: keepPreviousData,
  });

  if (!can(me, "compras")) return <SinAcceso />;
  return (
    <>
      <PageHeader
        eyebrow={actual?.nombre}
        title="Compras"
        actions={
          <>
            <Link href="/panel/proveedores" className="inline-flex h-10 items-center rounded-control px-4 text-base text-fg-2 hover:bg-wash hover:text-fg">
              Proveedores
            </Link>
            {can(me, "compras", "crear") && <Button onClick={() => setNueva(true)}>Registrar compra</Button>}
          </>
        }
      />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">Cada compra suma el stock de sus insumos en esta sucursal y actualiza su costo, que alimenta el margen de cada plato.</p>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.items.length === 0 ? (
        <EmptyState title="Sin compras" description="Registra lo que te llega de tus proveedores para llevar stock y costos al día." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Compra</Th>
              <Th>Fecha</Th>
              <Th>Proveedor</Th>
              <Th align="right">Insumos</Th>
              <Th align="right">Total</Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.items.map((c) => (
              <Tr key={c.id} className="cursor-pointer" onClick={() => setDetalle(c)}>
                <Td className="font-medium">
                  #{c.id}
                  {c.numero_documento && <span className="ml-2 text-sm text-fg-3">{c.numero_documento}</span>}
                </Td>
                <Td className="text-fg-2">{fecha.format(new Date(`${c.fecha}T12:00:00`))}</Td>
                <Td className="text-fg-2">{c.proveedor ?? "—"}</Td>
                <Td align="right">{c.items.length}</Td>
                <Td align="right">
                  <Money value={c.total} simbolo={c.simbolo} />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
      {actual && <NuevaCompra open={nueva} onOpenChange={setNueva} sucursalId={actual.id} />}
      <Sheet open={detalle !== null} onOpenChange={(o) => !o && setDetalle(null)} side="right" title={detalle ? `Compra #${detalle.id}` : "Compra"} description={detalle?.proveedor ?? undefined}>
        {detalle && (
          <div className="flex flex-col gap-6">
            <Money value={detalle.total} simbolo={detalle.simbolo} size="l" />
            <ul className="flex flex-col">
              {detalle.items.map((i) => (
                <li key={i.insumo_id} className="flex items-baseline justify-between gap-4 border-t border-line py-3">
                  <span className="flex flex-col">
                    <span>{i.insumo}</span>
                    <span className="text-sm text-fg-3">
                      {i.codigo} · {cantidad(i.cantidad)} {abrev(i.unidad)}
                    </span>
                  </span>
                  <Money value={i.subtotal} simbolo={detalle.simbolo} />
                </li>
              ))}
            </ul>
            {detalle.notas && <p className="text-sm text-fg-2">{detalle.notas}</p>}
          </div>
        )}
      </Sheet>
    </>
  );
}

interface Linea {
  insumo_id: string;
  cantidad: string;
  /** Vacío = la cantidad está en la unidad del insumo; si no, es la presentación (cajas, sacos) */
  presentacion_id?: string;
  subtotal: string;
}

function NuevaCompra({ open, onOpenChange, sucursalId }: { open: boolean; onOpenChange: (o: boolean) => void; sucursalId: number }) {
  const qc = useQueryClient();
  const { data: monedas } = useMonedas(sucursalId);
  const insumos = useQuery({ queryKey: ["insumos"], queryFn: () => api("/insumos", { schema: z.array(InsumoOut) }), enabled: open });
  const proveedores = useQuery({ queryKey: ["proveedores"], queryFn: () => api("/proveedores", { schema: z.array(ProveedorOut) }), enabled: open });
  const [lineas, setLineas] = useState<Linea[]>([{ insumo_id: "", cantidad: "", subtotal: "" }]);
  const [cab, setCab] = useState({ proveedor_id: "", moneda_id: "", numero_documento: "", fecha: "" });
  const [error, setError] = useState<ErrorView | null>(null);
  const moneda = monedas?.find((m) => String(m.id) === cab.moneda_id) ?? monedas?.find((m) => m.es_principal);
  const total = lineas.reduce((t, l) => t.plus(parseAmountInput(l.subtotal) ?? "0"), new Big(0)).toFixed(2);

  const registrar = useMutation({
    mutationFn: () =>
      api("/compras", {
        method: "POST",
        body: {
          sucursal_id: sucursalId,
          proveedor_id: cab.proveedor_id ? Number(cab.proveedor_id) : null,
          moneda_id: moneda?.id,
          numero_documento: cab.numero_documento.trim() || null,
          fecha: cab.fecha || null,
          items: lineas.map((l) => ({ insumo_id: Number(l.insumo_id), cantidad: parseAmountInput(l.cantidad), presentacion_id: l.presentacion_id ? Number(l.presentacion_id) : null, subtotal: parseAmountInput(l.subtotal) ?? "0" })),
        },
        schema: CompraOut,
      }),
    onSuccess: (c) => {
      toast({ title: `Compra #${c.id} registrada`, description: "Stock y costos actualizados.", tone: "ok" });
      void qc.invalidateQueries({ queryKey: ["compras"] });
      void qc.invalidateQueries({ queryKey: ["inventario"] });
      void qc.invalidateQueries({ queryKey: ["insumos"] });
      setLineas([{ insumo_id: "", cantidad: "", subtotal: "" }]);
      setCab({ proveedor_id: "", moneda_id: "", numero_documento: "", fecha: "" });
      onOpenChange(false);
    },
    onError: (e) => setError(describeError(e)),
  });

  const set = (i: number, campo: keyof Linea, v: string) => setLineas((ls) => ls.map((l, j) => (j === i ? { ...l, [campo]: v } : l)));
  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="right" title="Registrar compra" description="Lo que llegó y cuánto costó cada línea.">
      <form
        noValidate
        className="flex flex-col gap-7 pt-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (lineas.some((l) => !l.insumo_id || !parseAmountInput(l.cantidad))) return setError({ title: "Completa insumo y cantidad en cada línea", tone: "warn" });
          registrar.mutate();
        }}
      >
        <Select label="Proveedor" value={cab.proveedor_id} onChange={(e) => setCab((c) => ({ ...c, proveedor_id: e.target.value }))}>
          <option value="">Sin proveedor</option>
          {proveedores.data
            ?.filter((p) => p.activo)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
        </Select>
        <div className="grid grid-cols-2 gap-4">
          <Field label="N° de factura" value={cab.numero_documento} onChange={(e) => setCab((c) => ({ ...c, numero_documento: e.target.value }))} maxLength={60} placeholder="Opcional" />
          <Field label="Fecha" type="date" value={cab.fecha} onChange={(e) => setCab((c) => ({ ...c, fecha: e.target.value }))} className="[&_input]:[color-scheme:dark]" />
        </div>
        <Select label="Moneda en que pagaste" value={String(moneda?.id ?? "")} onChange={(e) => setCab((c) => ({ ...c, moneda_id: e.target.value }))}>
          {monedas
            ?.filter((m) => m.activa)
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.codigo} · {m.nombre}
              </option>
            ))}
        </Select>

        <fieldset className="flex flex-col gap-4">
          <legend className="eyebrow pb-2">Insumos</legend>
          {lineas.map((l, i) => {
            const insumo = insumos.data?.find((x) => String(x.id) === l.insumo_id);
            const pres = insumo?.presentaciones.find((p) => String(p.id) === l.presentacion_id);
            const medida = pres ? pres.nombre : insumo?.unidad_abreviatura;
            return (
              <div key={i} className="flex flex-col gap-2">
              <div className="grid grid-cols-[1fr_6rem_7rem_auto] items-end gap-3">
                <Select label={i === 0 ? "Insumo" : ""} aria-label="Insumo" value={l.insumo_id} onChange={(e) => setLineas((ls) => ls.map((x, j) => (j === i ? { ...x, insumo_id: e.target.value, presentacion_id: "" } : x)))}>
                  <option value="">Elige…</option>
                  {insumos.data
                    ?.filter((x) => x.activo)
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.nombre} · {x.codigo}
                      </option>
                    ))}
                </Select>
                <Field label={i === 0 ? "Cantidad" : ""} aria-label="Cantidad" inputMode="decimal" value={l.cantidad} onChange={(e) => set(i, "cantidad", e.target.value)} placeholder={medida ?? ""} />
                <Field label={i === 0 ? `Costo (${moneda?.simbolo ?? ""})` : ""} aria-label="Costo de la línea" inputMode="decimal" value={l.subtotal} onChange={(e) => set(i, "subtotal", e.target.value)} />
                <button
                  type="button"
                  aria-label="Quitar línea"
                  disabled={lineas.length === 1}
                  onClick={() => setLineas((ls) => ls.filter((_, j) => j !== i))}
                  className="mb-1 grid size-9 place-items-center rounded-full text-fg-3 hover:bg-wash hover:text-fg disabled:opacity-30"
                >
                  <X size={16} strokeWidth={1.5} />
                </button>
              </div>
              {insumo && insumo.presentaciones.length > 0 && (
                <Select label="" aria-label="Se cuenta en" value={l.presentacion_id ?? ""} onChange={(e) => set(i, "presentacion_id", e.target.value)}>
                  <option value="">Cantidad en {insumo.unidad_abreviatura}</option>
                  {insumo.presentaciones.map((p) => (
                    <option key={p.id} value={p.id}>
                      Por {p.nombre} ({cantidad(p.cantidad)} {insumo.unidad_abreviatura} c/u)
                    </option>
                  ))}
                </Select>
              )}
              </div>
            );
          })}
          <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setLineas((ls) => [...ls, { insumo_id: "", cantidad: "", subtotal: "" }])}>
            <Plus size={14} strokeWidth={1.5} aria-hidden /> Agregar insumo
          </Button>
        </fieldset>

        <div className="flex items-baseline justify-between border-t border-line pt-4">
          <span className="eyebrow">Total</span>
          <Money value={total} simbolo={moneda?.simbolo} size="l" />
        </div>
        {error && <ErrorBox error={error} onClose={() => setError(null)} />}
        <Button type="submit" size="lg" loading={registrar.isPending}>
          Registrar compra
        </Button>
      </form>
    </Sheet>
  );
}
