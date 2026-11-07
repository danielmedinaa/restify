import { EmptyState } from "@/components/ui/EmptyState";
import { Loading, Skeleton } from "@/components/ui/Skeleton";
import { describeError } from "@/lib/api/errors";

export function ListLoading({ label = "Cargando", rows = 6 }: { label?: string; rows?: number }) {
  return (
    <Loading label={label}>
      <div className="flex flex-col">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="flex items-center justify-between gap-6 border-t border-line py-5">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-4 w-20" />
          </div>
        ))}
      </div>
    </Loading>
  );
}

export function ListError({ error }: { error: unknown }) {
  const e = describeError(error);
  return <EmptyState title={e.title} description={e.description ?? "Intenta de nuevo en un momento."} />;
}

export function SinAcceso() {
  return <EmptyState title="Sin acceso" description="Tu rol no puede ver esta sección. Pídele acceso a un administrador." />;
}
