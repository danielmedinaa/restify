"use client";

import { useParams } from "next/navigation";
import { EmptyState } from "@/components/ui/EmptyState";
import { Dividir } from "@/features/caja/Dividir";

export default function DividirPage() {
  const { id } = useParams<{ id: string }>();
  const n = Number(id);
  if (!Number.isInteger(n) || n <= 0) return <EmptyState title="No existe" description="Ese número de comanda no es válido." />;
  return <Dividir key={n} id={n} />;
}
