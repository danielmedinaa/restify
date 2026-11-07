import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { setupEstado } from "@/lib/server/setup";
import { RotatingSeal } from "../login/RotatingSeal";
import { SetupWizard } from "./SetupWizard";

export const metadata: Metadata = { title: "Configuración inicial" };
export const dynamic = "force-dynamic";

export default async function ConfigurarPage() {
  const estado = await setupEstado();
  // Ya configurada (o backend caído): no hay nada que hacer aquí
  if (!estado?.pendiente) redirect("/login");
  return (
    <main className="grid min-h-dvh desk:grid-cols-2">
      <section aria-hidden className="grain relative hidden overflow-hidden bg-sunken desk:flex desk:flex-col desk:justify-between desk:p-12">
        <span className="eyebrow">Configuración inicial</span>
        <div className="flex justify-center">
          <RotatingSeal size={440} />
        </div>
        <span className="text-sm text-fg-3">Unos minutos y tu restaurante queda listo.</span>
      </section>
      <section className="flex flex-col justify-center px-6 py-16 tablet:px-16">
        <div className="mx-auto flex w-full max-w-md flex-col gap-10">
          <SetupWizard requiereToken={estado.requiereToken} />
        </div>
      </section>
    </main>
  );
}
