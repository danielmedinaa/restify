import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/money";
import { NumberRoll } from "./NumberRoll";

type Size = "body" | "s" | "m" | "l" | "xl";

const sizes: Record<Size, string> = {
  body: "text-base font-medium tabular",
  s: "font-display text-display-s",
  m: "font-display text-display-m",
  l: "font-display text-display-l",
  xl: "font-display text-display-xl",
};

export interface MoneyProps {
  /** String decimal tal como llega del backend. */
  value: string;
  simbolo?: string;
  size?: Size;
  /** Anima los dígitos cuando cambia el valor (totales, pendiente). */
  roll?: boolean;
  className?: string;
}

export function Money({ value, simbolo, size = "body", roll = false, className }: MoneyProps) {
  const amount = formatAmount(value);
  const display = size !== "body";
  return (
    <span className={cn("inline-flex items-baseline gap-[0.18em] whitespace-nowrap", sizes[size], className)}>
      {simbolo && (
        <span className={cn(display ? "text-[0.42em] font-sans font-medium text-fg-3" : "text-fg-3")}>{simbolo}</span>
      )}
      {roll ? <NumberRoll value={amount} /> : <span className="tabular">{amount}</span>}
    </span>
  );
}
