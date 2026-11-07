"use client";

import { usePathname } from "next/navigation";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { findNav } from "@/features/panel/nav";

const ETAPAS: Record<number, string> = {
  3: "comandas, caja y mesas",
  4: "pantalla de cocina",
  6: "inventario, catálogo y ventas",
  7: "administración",
};

/** Rutas del menú que aún no se construyen: dicen en qué etapa llegan. */
export default function EnCamino() {
  const item = findNav(usePathname());
  if (!item) {
    return <EmptyState title="No existe" description="Esta pantalla no está en el panel. Revisa la dirección o usa el menú." />;
  }
  return (
    <>
      <PageHeader eyebrow={`Etapa ${item.etapa}`} title={item.label} />
      <EmptyState title="En camino" description={`Esta pantalla llega con la etapa de ${ETAPAS[item.etapa] ?? "próximas mejoras"}.`} className="pt-0" />
    </>
  );
}
