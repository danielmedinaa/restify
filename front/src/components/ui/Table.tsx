import { cn } from "@/lib/cn";

/** Tabla editorial: filas separadas por línea fina, sin cajas ni zebra. */
export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-left text-base", className)} {...props} />
    </div>
  );
}

export function Th({ className, align, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn("eyebrow border-b border-line-strong pb-3 pr-6 font-medium last:pr-0", align === "right" && "text-right", className)}
      {...props}
    />
  );
}

export function Td({ className, align, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn("border-b border-line py-4 pr-6 align-middle last:pr-0", align === "right" && "text-right tabular", className)}
      {...props}
    />
  );
}

export function Tr({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors hover:bg-wash", className)} {...props} />;
}
