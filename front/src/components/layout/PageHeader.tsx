import { cn } from "@/lib/cn";

/** Encabezado de pantalla: etiqueta, título en Gagalin y acciones a la derecha. */
export function PageHeader({
  eyebrow,
  title,
  actions,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("mb-10 flex flex-wrap items-end justify-between gap-6 desk:mb-14", className)}>
      <div className="flex flex-col gap-3">
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1 className="font-display text-display-m tablet:text-display-l">{title}</h1>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
