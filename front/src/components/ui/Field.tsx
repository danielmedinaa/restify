"use client";

import { forwardRef, useId } from "react";
import { cn } from "@/lib/cn";

export interface FieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string | null;
}

/** Etiqueta arriba, línea inferior y un error de una línea. Sin cajas. */
export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, hint, error, className, id, ...props },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;
  return (
    <div className={cn("group flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className="eyebrow">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          "h-11 w-full border-b bg-transparent text-lead text-fg outline-none transition-colors placeholder:text-fg-4",
          "focus-visible:rounded-none focus-visible:outline-none",
          error ? "border-err" : "border-line-strong focus:border-paper",
        )}
        {...props}
      />
      {error ? (
        <p id={`${inputId}-error`} className="text-sm text-err">
          {error}
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-sm text-fg-3">
          {hint}
        </p>
      ) : null}
    </div>
  );
});
