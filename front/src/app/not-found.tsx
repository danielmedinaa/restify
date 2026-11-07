import Link from "next/link";
import { EmptyState } from "@/components/ui/EmptyState";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col justify-center px-6">
      <span className="eyebrow">404</span>
      <EmptyState
        title="Aquí no hay nada"
        description="Esta dirección no existe o se movió. Revisa el enlace o vuelve al inicio."
        action={
          <Link href="/panel" className="text-fg underline underline-offset-4">
            Ir al panel
          </Link>
        }
        className="pt-4"
      />
    </main>
  );
}
