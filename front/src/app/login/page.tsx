import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { setupEstado } from "@/lib/server/setup";
import { LoginForm } from "./LoginForm";
import { RotatingSeal } from "./RotatingSeal";

export const metadata: Metadata = { title: "Entrar" };

const MOTIVOS: Record<string, string> = {
  expirada: "Tu sesión terminó. Vuelve a entrar para seguir.",
  password: "Cambiaste tu contraseña. Entra con la nueva.",
};

/** Solo rutas internas: evita redirecciones abiertas (?next=https://otro-sitio). */
function safeNext(next: string | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/panel";
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const { next, motivo } = await searchParams;
  // Instancia recién creada: primero la configuración inicial
  if ((await setupEstado())?.pendiente) redirect("/configurar");
  return (
    <main className="grid min-h-dvh desk:grid-cols-2">
      <section aria-hidden className="grain relative hidden overflow-hidden bg-sunken desk:flex desk:flex-col desk:justify-between desk:p-12">
        <span className="eyebrow">Gestión de cocina y restaurante</span>
        <div className="flex justify-center">
          <RotatingSeal size={440} />
        </div>
        <span className="text-sm text-fg-3">Sala, cocina y caja en tiempo real.</span>
      </section>

      <section className="flex flex-col justify-center px-6 py-16 tablet:px-16">
        <div className="mx-auto flex w-full max-w-sm flex-col gap-10">
          <div className="desk:hidden">
            <RotatingSeal size={120} />
          </div>
          <div className="flex flex-col gap-3">
            <span className="eyebrow">Personal</span>
            <h1 className="font-display text-display-l">Entrar</h1>
          </div>
          <LoginForm next={safeNext(next)} notice={motivo ? MOTIVOS[motivo] : undefined} />
        </div>
      </section>
    </main>
  );
}
