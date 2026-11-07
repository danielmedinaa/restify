import { cn } from "@/lib/cn";

export interface EmptyStateProps {
  /** Una o dos palabras, van en Gagalin. */
  title: string;
  description: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex max-w-md flex-col items-start gap-4 py-16", className)}>
      <h2 className="font-display text-display-l text-fg">{title}</h2>
      <p className="text-lead text-fg-2">{description}</p>
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}
