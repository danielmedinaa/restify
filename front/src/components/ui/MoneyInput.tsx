"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/cn";
import { parseAmountInput } from "@/lib/money";

export interface MoneyInputProps {
  label: string;
  simbolo: string;
  /** Recibe el monto normalizado ("1234.5") o null si está vacío o es inválido. */
  onValueChange: (value: string | null) => void;
  defaultValue?: string;
  autoFocus?: boolean;
  className?: string;
}

/** Se escribe en Gagalin, grande: en caja el monto es lo único que importa. */
export function MoneyInput({ label, simbolo, onValueChange, defaultValue = "", autoFocus, className }: MoneyInputProps) {
  const id = useId();
  const [text, setText] = useState(defaultValue);
  const invalid = text !== "" && parseAmountInput(text) === null;
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <label htmlFor={id} className="eyebrow">
        {label}
      </label>
      <div
        className={cn(
          "flex items-baseline gap-3 border-b pb-2 transition-colors",
          invalid ? "border-err" : "border-line-strong focus-within:border-paper",
        )}
      >
        <span className="text-title font-medium text-fg-3">{simbolo}</span>
        <input
          id={id}
          inputMode="decimal"
          autoComplete="off"
          autoFocus={autoFocus}
          value={text}
          placeholder="0,00"
          aria-invalid={invalid || undefined}
          onChange={(e) => {
            setText(e.target.value);
            onValueChange(parseAmountInput(e.target.value));
          }}
          className="w-full min-w-0 bg-transparent font-display text-display-m text-fg outline-none placeholder:text-fg-4 focus-visible:outline-none"
        />
      </div>
    </div>
  );
}
