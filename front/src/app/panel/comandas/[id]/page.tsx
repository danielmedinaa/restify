"use client";

import { useParams } from "next/navigation";
import { EmptyState } from "@/components/ui/EmptyState";
import { ComandaDetalle } from "@/features/comandas/ComandaDetalle";

export default function ComandaPage() {
  const { id } = useParams<{ id: string }>();
  const n = Number(id);
  if (!Number.isInteger(n) || n <= 0) return <EmptyState title="No existe" description="Ese número de comanda no es válido." />;
  // key: al navegar entre comandas se reinicia el estado local (selección, sheets)
  return <ComandaDetalle key={n} id={n} />;
}
