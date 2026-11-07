"use client";

import { useParams } from "next/navigation";
import { SinAcceso } from "@/components/layout/Estados";
import { EmptyState } from "@/components/ui/EmptyState";
import { can, useMe } from "@/features/auth/useMe";
import { Facturar } from "@/features/facturacion/Facturar";

export default function FacturarPage() {
  const { id } = useParams<{ id: string }>();
  const { data: me } = useMe();
  const n = Number(id);
  if (!can(me, "ventas")) return <SinAcceso />;
  if (!Number.isInteger(n) || n <= 0) return <EmptyState title="No existe" description="Ese número de venta no es válido." />;
  return <Facturar key={n} id={n} />;
}
