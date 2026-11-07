import { useId } from "react";

/** Switch para formularios: es un checkbox nativo (funciona con FormData y teclado). */
export function Toggle({ name, label, defaultChecked, hint }: { name: string; label: string; defaultChecked?: boolean; hint?: string }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-6">
      <label htmlFor={id} className="flex flex-col gap-0.5">
        <span className="text-base">{label}</span>
        {hint && <span className="text-sm text-fg-3">{hint}</span>}
      </label>
      <input
        id={id}
        name={name}
        type="checkbox"
        role="switch"
        defaultChecked={defaultChecked}
        className="relative h-6 w-10 shrink-0 cursor-pointer appearance-none rounded-full bg-wash-strong transition-colors before:absolute before:left-0.5 before:top-0.5 before:size-5 before:rounded-full before:bg-fg-2 before:transition-transform checked:bg-paper checked:before:translate-x-4 checked:before:bg-ink"
      />
    </div>
  );
}
