import { cn } from "@/lib/cn";

/** Bloque de carga. Tiene la forma del contenido que reemplaza, nunca un spinner. */
export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cn("block skeleton", className)} />;
}

/** Envoltorio para anunciar la carga una sola vez a lectores de pantalla. */
export function Loading({ label = "Cargando", children }: { label?: string; children: React.ReactNode }) {
  return (
    <div role="status" aria-live="polite" aria-busy>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}
