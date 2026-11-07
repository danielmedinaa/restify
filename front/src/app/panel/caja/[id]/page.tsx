"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Caja } from "@/features/caja/Caja";

export default function CajaPage() {
  const { id } = useParams<{ id: string }>();
  const n = Number(id);
  if (!Number.isInteger(n) || n <= 0) return <EmptyState title="No existe" description="Ese número de comanda no es válido." />;
  // useSearchParams (prefill desde Dividir) necesita un límite de Suspense
  return (
    <Suspense>
      <Caja key={n} id={n} />
    </Suspense>
  );
}
