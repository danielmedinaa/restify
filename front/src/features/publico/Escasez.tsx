import { cn } from "@/lib/cn";

const UMBRAL = 5;

/**
 * Indicador de escasez: cinco trazos finos que se van apagando y una palabra.
 * Solo aparece cuando de verdad quedan pocas porciones.
 */
export function Escasez({ porciones, className }: { porciones: number | null; className?: string }) {
  if (porciones === null || porciones > UMBRAL) return null;
  const texto = porciones <= 0 ? "Agotado" : porciones === 1 ? "Último" : `Quedan ${porciones}`;
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm text-warn", className)}>
      <span aria-hidden className="flex items-end gap-[3px]">
        {Array.from({ length: UMBRAL }, (_, i) => (
          <span key={i} className={cn("w-[3px] rounded-full", i < porciones ? "bg-warn" : "bg-line-strong")} style={{ height: 6 + i * 2 }} />
        ))}
      </span>
      {texto}
    </span>
  );
}
