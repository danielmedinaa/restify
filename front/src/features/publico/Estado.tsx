import { Logo } from "@/components/ui/Logo";

/** Pantalla completa para estados del cliente: mesa ocupada, QR inválido, etc. */
export function EstadoPublico({ eyebrow, titulo, children }: { eyebrow?: string; titulo: string; children: React.ReactNode }) {
  return (
    <main className="grain mx-auto flex min-h-dvh max-w-2xl flex-col justify-between gap-12 px-6 py-10">
      <Logo size={72} />
      <div className="flex flex-col gap-6">
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1 className="font-display text-display-l leading-[0.9] tablet:text-display-xl">{titulo}</h1>
        <div className="flex flex-col gap-4 text-lead text-fg-2">{children}</div>
      </div>
      <span className="text-sm text-fg-3">Restify</span>
    </main>
  );
}

export function MenuSkeleton() {
  return (
    <div className="mx-auto max-w-2xl px-5 pt-6" role="status" aria-busy>
      <span className="sr-only">Cargando el menú</span>
      <span className="block h-3 w-24 skeleton" />
      <span className="mt-3 block h-8 w-40 skeleton" />
      <div className="mt-16 flex flex-col gap-8">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="flex gap-4 border-t border-line pt-5">
            <div className="flex flex-1 flex-col gap-2">
              <span className="block h-5 w-40 skeleton" />
              <span className="block h-4 w-full skeleton" />
              <span className="block h-4 w-20 skeleton" />
            </div>
            <span className="block size-24 skeleton" />
          </div>
        ))}
      </div>
    </div>
  );
}
