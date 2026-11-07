import { forwardRef, useId } from "react";
import { cn } from "@/lib/cn";

export const TextArea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }>(function TextArea(
  { label, className, id, rows = 3, ...props },
  ref,
) {
  const autoId = useId();
  const areaId = id ?? autoId;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={areaId} className="eyebrow">
        {label}
      </label>
      <textarea
        ref={ref}
        id={areaId}
        rows={rows}
        className="resize-none border-b border-line-strong bg-transparent py-2 text-base outline-none placeholder:text-fg-4 focus:border-paper focus-visible:outline-none"
        {...props}
      />
    </div>
  );
});
