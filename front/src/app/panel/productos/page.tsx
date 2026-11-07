"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDeferredValue, useState } from "react";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Money } from "@/components/ui/Money";
import { StatusDot } from "@/components/ui/Status";
import { can, useMe } from "@/features/auth/useMe";
import { useApiMutation, useFormSheet } from "@/features/crud/crud";
import { ProductoForm } from "@/features/productos/ProductoForm";
import { Medio } from "@/features/publico/Medio";
import { portada } from "@/features/publico/precio";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { Pagina, ProductoOut, type Producto } from "@/lib/api/schemas";

export default function ProductosPage() {
  const { data: me } = useMe();
  const router = useRouter();
  const [q, setQ] = useState("");
  const termino = useDeferredValue(q.trim());
  const lista = useQuery({
    queryKey: ["productos", termino],
    queryFn: () => api("/productos", { query: { q: termino, limite: 100 }, schema: Pagina(ProductoOut) }),
    enabled: can(me, "productos"),
    placeholderData: keepPreviousData,
  });
  const form = useFormSheet<Producto>();
  const [error, setError] = useState<ErrorView | null>(null);
  const crear = useApiMutation<{ body: Record<string, unknown> }>({
    path: () => "/productos",
    method: "POST",
    body: (v) => v.body,
    invalidate: [["productos"], ["menu"]],
    ok: "Producto creado. Agrégale fotos.",
    onError: setError,
  });

  if (!can(me, "productos")) return <SinAcceso />;
  const grupos = new Map<string, Producto[]>();
  for (const p of lista.data?.items ?? []) {
    const k = p.categoria?.nombre ?? "Otros";
    grupos.set(k, [...(grupos.get(k) ?? []), p]);
  }

  return (
    <>
      <PageHeader title="Productos" actions={can(me, "productos", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nuevo producto</Button>} />
      <label className="mb-10 flex max-w-md items-center gap-3 border-b border-line-strong focus-within:border-paper">
        <Search size={18} strokeWidth={1.5} className="text-fg-3" aria-hidden />
        <span className="sr-only">Buscar producto</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar producto" className="h-12 w-full bg-transparent text-lead outline-none placeholder:text-fg-4 focus-visible:outline-none" />
      </label>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.items.length === 0 ? (
        <EmptyState title={termino ? "Nada así" : "Sin productos"} description={termino ? "Ningún producto coincide." : "Crea tu primer plato con su precio, foto y receta."} />
      ) : (
        <div className="flex flex-col gap-12">
          {[...grupos.entries()].map(([cat, ps]) => (
            <section key={cat} className="flex flex-col">
              <h2 className="pb-3 font-display text-display-s">{cat}</h2>
              <ul className="flex flex-col">
                {ps.map((p) => {
                  const media = portada({ ...p, precio: p.precio_base, precios: [], precio_sin_iva: p.precio_base, porciones_disponibles: null, ingredientes: [] });
                  return (
                    <li key={p.id}>
                      <Link href={`/panel/productos/${p.id}`} className={`-mx-3 flex items-center gap-4 rounded-control border-t border-line px-3 py-3 transition-colors hover:bg-wash ${p.activo ? "" : "opacity-50"}`}>
                        <span className="size-14 shrink-0 overflow-hidden rounded-control bg-raised">{media && <Medio medio={media} alt={p.nombre} />}</span>
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="truncate text-title font-medium">{p.nombre}</span>
                          <span className="truncate text-sm text-fg-3">
                            {p.codigo} · {p.control_stock === "receta" ? "Con receta" : p.control_stock === "directo" ? "Directo" : "Sin stock"} · {p.medios.length} {p.medios.length === 1 ? "foto/video" : "fotos/videos"}
                          </span>
                        </span>
                        {!p.activo && <StatusDot tone="muted">Inactivo</StatusDot>}
                        <Money value={p.precio_base} className="text-base" />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
      {form.state && (
        <ProductoForm
          state={form.state}
          onOpenChange={form.onOpenChange}
          pending={crear.isPending}
          error={error}
          setError={setError}
          onGuardar={(v) =>
            crear.mutate(v, {
              onSuccess: (p) => {
                form.cerrar();
                const id = ProductoOut.safeParse(p).data?.id;
                if (id) router.push(`/panel/productos/${id}`);
              },
            })
          }
        />
      )}
    </>
  );
}
