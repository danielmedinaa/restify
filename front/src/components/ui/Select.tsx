import { forwardRef, useId } from "react";
import { cn } from "@/lib/cn";

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  error?: string | null;
}

/** Select nativo con el mismo trazo que Field (accesible y cómodo en móvil). */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ label, hint, error, className, id, children, ...props }, ref) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={selectId} className="eyebrow">
        {label}
      </label>
      <select
        ref={ref}
        id={selectId}
        aria-invalid={error ? true : undefined}
        className={cn(
          "h-11 w-full border-b bg-transparent text-lead text-fg outline-none transition-colors focus-visible:outline-none [&>option]:bg-overlay",
          error ? "border-err" : "border-line-strong focus:border-paper",
        )}
        {...props}
      >
        {children}
      </select>
      {error ? <p className="text-sm text-err">{error}</p> : hint ? <p className="text-sm text-fg-3">{hint}</p> : null}
    </div>
  );
});
