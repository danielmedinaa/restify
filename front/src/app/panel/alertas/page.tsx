"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Segmented } from "@/components/ui/Segmented";
import { StatusDot } from "@/components/ui/Status";
import { can, useMe } from "@/features/auth/useMe";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import { AlertaOut, Pagina } from "@/lib/api/schemas";

const fecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Centro de alertas de stock. Las nuevas llegan también como toast en vivo. */
export default function AlertasPage() {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const [estado, setEstado] = useState<"activa" | "resuelta">("activa");
  const lista = useQuery({
    queryKey: ["alertas", actual?.id, estado],
    queryFn: () => api("/alertas", { query: { sucursal_id: actual?.id, estado, limite: 100 }, schema: Pagina(AlertaOut) }),
    enabled: !!actual && can(me, "inventario"),
    placeholderData: keepPreviousData,
  });
  if (!can(me, "inventario")) return <SinAcceso />;
  return (
    <>
      <PageHeader
        eyebrow={actual?.nombre}
        title="Alertas"
        actions={
          <Segmented
            label="Estado"
            value={estado}
            onChange={setEstado}
            options={[
              { value: "activa", label: "Activas" },
              { value: "resuelta", label: "Resueltas" },
            ]}
          />
        }
      />
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.items.length === 0 ? (
        <EmptyState
          title={estado === "activa" ? "Todo en orden" : "Sin historial"}
          description={estado === "activa" ? "Ningún insumo está en su mínimo. Si alguno llega, te avisamos al instante." : "Aquí quedan las alertas que se resolvieron al reponer stock."}
        />
      ) : (
        <ul className="flex flex-col">
          {lista.data.items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-4 border-t border-line py-5">
              <div className="flex flex-col gap-1">
                <StatusDot tone={a.estado === "activa" ? "warn" : "ok"}>{a.estado === "activa" ? "Stock bajo" : "Resuelta"}</StatusDot>
                <p className="text-title font-medium">{a.mensaje}</p>
                <p className="text-sm text-fg-3">
                  {fecha.format(new Date(a.created_at))}
                  {a.resuelta_en ? ` · resuelta ${fecha.format(new Date(a.resuelta_en))}` : ""}
                </p>
              </div>
              {a.estado === "activa" && (
                <Link href="/panel/inventario" className="text-sm text-fg underline underline-offset-4">
                  Reponer en existencias
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
