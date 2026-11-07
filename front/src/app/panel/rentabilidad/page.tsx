"use client";

import { useQuery } from "@tanstack/react-query";
import Big from "big.js";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Money } from "@/components/ui/Money";
import { Segmented } from "@/components/ui/Segmented";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { can, useMe } from "@/features/auth/useMe";
import { principalDe, useMonedas } from "@/features/comandas/queries";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import { RentabilidadOut, type Rentabilidad } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

type Orden = "margen" | "costo_pct" | "nombre";

/** Referencia habitual de food cost en restaurantes: hasta ~35 % es sano. */
const FOOD_COST_ALTO = 35;

export default function RentabilidadPage() {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const { data: monedas } = useMonedas(actual?.id);
  const simbolo = principalDe(monedas)?.simbolo;
  const [q, setQ] = useState("");
  const busqueda = useDeferredValue(q.trim());
  const [orden, setOrden] = useState<Orden>("margen");
  const lista = useQuery({
    queryKey: ["rentabilidad", actual?.id, busqueda],
    queryFn: () => api("/rentabilidad", { query: { sucursal_id: actual!.id, q: busqueda || undefined }, schema: z.array(RentabilidadOut) }),
    enabled: !!actual && can(me, "ventas"),
  });

  if (!can(me, "ventas")) return <SinAcceso />;
  const filas = [...(lista.data ?? [])].sort(ordenar(orden));
  const conCosto = filas.filter((f) => f.costo !== null);
  const sinCosto = filas.filter((f) => f.costo === null && !f.sin_receta);

  return (
    <>
      <PageHeader eyebrow={actual?.nombre} title="Rentabilidad" />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">
        Cuánto te cuesta cada plato según su receta y el último costo de cada insumo (lo actualizan las{" "}
        <Link href="/panel/compras" className="underline underline-offset-4">
          compras
        </Link>
        ), contra su precio sin IVA.
      </p>

      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="eyebrow">Buscar</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Plato o código" className="h-11 w-64 border-b border-line-strong bg-transparent text-base outline-none placeholder:text-fg-4 focus:border-paper" />
        </label>
        <Segmented
          label="Ordenar"
          size="sm"
          value={orden}
          onChange={setOrden}
          options={[
            { value: "margen", label: "Menor margen" },
            { value: "costo_pct", label: "Mayor food cost" },
            { value: "nombre", label: "Nombre" },
          ]}
        />
      </div>

      {sinCosto.length > 0 && (
        <p className="mb-8 rounded-control border border-warn/50 bg-warn/10 px-4 py-3 text-sm">
          {sinCosto.length} {sinCosto.length === 1 ? "plato no tiene" : "platos no tienen"} costo porque faltan costos de insumos:{" "}
          {[...new Set(sinCosto.flatMap((f) => f.insumos_sin_costo))].join(", ")}. Cárgalos en{" "}
          <Link href="/panel/insumos" className="underline underline-offset-4">
            Insumos
          </Link>{" "}
          o registra una compra.
        </p>
      )}

      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : filas.length === 0 ? (
        <EmptyState title="Sin platos" description="No hay productos activos con ese nombre." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Plato</Th>
              <Th align="right">Precio sin IVA</Th>
              <Th align="right">Costo</Th>
              <Th align="right">Margen</Th>
              <Th>Food cost</Th>
            </tr>
          </thead>
          <tbody>
            {[...conCosto, ...filas.filter((f) => f.costo === null)].map((f) => (
              <Tr key={f.producto_id}>
                <Td>
                  <span className="flex flex-col">
                    <span className="font-medium">{f.producto}</span>
                    <span className="text-sm text-fg-3">
                      {f.codigo}
                      {f.categoria && ` · ${f.categoria}`}
                    </span>
                  </span>
                </Td>
                <Td align="right">
                  <Money value={f.precio_sin_iva} simbolo={simbolo} />
                </Td>
                <Td align="right" className="text-fg-2">
                  {f.costo !== null ? <Money value={f.costo} simbolo={simbolo} /> : <span className="text-sm text-fg-4">{f.sin_receta ? "Sin control de stock" : "Falta costo"}</span>}
                </Td>
                <Td align="right">
                  {f.margen !== null && (
                    <span className={cn(new Big(f.margen).lt(0) && "text-err")}>
                      <Money value={f.margen} simbolo={simbolo} />
                      <span className="block text-sm text-fg-3">{f.margen_pct} %</span>
                    </span>
                  )}
                </Td>
                <Td>{f.costo_pct !== null && <BarraCosto pct={Number(f.costo_pct)} />}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}

function BarraCosto({ pct }: { pct: number }) {
  const alto = pct > FOOD_COST_ALTO;
  return (
    <span className="flex items-center gap-3">
      <span aria-hidden className="block h-1.5 w-24 overflow-hidden rounded-full bg-wash-strong">
        <span className={cn("block h-full rounded-full", pct > 100 ? "bg-err" : alto ? "bg-warn" : "bg-ok")} style={{ width: `${Math.min(pct, 100)}%` }} />
      </span>
      <span className={cn("text-sm tabular", alto ? "text-fg" : "text-fg-2")}>{pct.toFixed(1).replace(".", ",")} %</span>
    </span>
  );
}

function ordenar(o: Orden) {
  return (a: Rentabilidad, b: Rentabilidad) => {
    if (o === "nombre") return a.producto.localeCompare(b.producto);
    const va = o === "margen" ? a.margen_pct : a.costo_pct;
    const vb = o === "margen" ? b.margen_pct : b.costo_pct;
    if (va === null) return 1;
    if (vb === null) return -1;
    return o === "margen" ? Number(va) - Number(vb) : Number(vb) - Number(va);
  };
}
