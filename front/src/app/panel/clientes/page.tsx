"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useDeferredValue, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Loading, Skeleton } from "@/components/ui/Skeleton";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { ClienteForm } from "@/features/clientes/ClienteForm";
import { notifyError } from "@/features/comandas/queries";
import { api } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { ClienteOut, Pagina, type Cliente } from "@/lib/api/schemas";
import { formatoDocumento } from "@/lib/fiscal";

const PAGINA = 50;

export default function ClientesPage() {
  // useSearchParams necesita un límite de Suspense
  return (
    <Suspense>
      <Clientes />
    </Suspense>
  );
}

function Clientes() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  // ⌘K puede llegar aquí con ?q=nombre
  const [q, setQ] = useState(useSearchParams().get("q") ?? "");
  const termino = useDeferredValue(q.trim());
  const [offset, setOffset] = useState(0);
  // open separado del contenido: al cerrar, el sheet conserva su animación de salida
  const [form, setForm] = useState<{ cliente: Cliente | null; key: number; open: boolean } | null>(null);
  const [borrar, setBorrar] = useState<Cliente | null>(null);

  const lista = useQuery({
    queryKey: ["clientes", "lista", termino, offset],
    queryFn: () => api("/clientes", { query: { q: termino, limite: PAGINA, offset }, schema: Pagina(ClienteOut) }),
    enabled: can(me, "clientes"),
    placeholderData: keepPreviousData,
  });
  const eliminar = useMutation({
    mutationFn: (c: Cliente) => api(`/clientes/${c.id}`, { method: "DELETE" }),
    onSuccess: (_, c) => {
      void qc.invalidateQueries({ queryKey: ["clientes"] });
      toast({ title: `${c.nombre} eliminado`, description: "Sus ventas conservan el histórico.", tone: "ok" });
      setBorrar(null);
    },
    onError: notifyError,
  });

  if (!can(me, "clientes")) return <EmptyState title="Sin acceso" description="Tu rol no puede ver clientes." />;
  const abrirForm = (cliente: Cliente | null) => setForm({ cliente, key: Date.now(), open: true });

  return (
    <>
      <PageHeader
        eyebrow={lista.data ? `${lista.data.total} registrados` : undefined}
        title="Clientes"
        actions={can(me, "clientes", "crear") && <Button onClick={() => abrirForm(null)}>Nuevo cliente</Button>}
      />

      <label className="mb-10 flex max-w-md items-center gap-3 border-b border-line-strong focus-within:border-paper">
        <Search size={18} strokeWidth={1.5} className="text-fg-3" aria-hidden />
        <span className="sr-only">Buscar cliente</span>
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          placeholder="Nombre, documento, teléfono o correo"
          className="h-12 w-full bg-transparent text-lead outline-none placeholder:text-fg-4 focus-visible:outline-none"
        />
      </label>

      {lista.isPending ? (
        <Loading label="Cargando clientes">
          <div className="flex flex-col gap-5">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-6 w-full" />
            ))}
          </div>
        </Loading>
      ) : lista.isError ? (
        <EmptyState title={describeError(lista.error).title} description="" />
      ) : lista.data.items.length === 0 ? (
        termino ? (
          <EmptyState title="Nadie así" description={`Ningún cliente coincide con “${termino}”.`} />
        ) : (
          <EmptyState
            title="Sin clientes"
            description="Registra a tus clientes frecuentes para asignarlos a sus comandas y ver lo que piden."
            action={can(me, "clientes", "crear") && <Button onClick={() => abrirForm(null)}>Registrar el primero</Button>}
          />
        )
      ) : (
        <div className="flex flex-col gap-6">
          <Table>
            <thead>
              <tr>
                <Th>Nombre</Th>
                <Th>Documento</Th>
                <Th>Teléfono</Th>
                <Th>Correo</Th>
                <Th>
                  <span className="sr-only">Acciones</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {lista.data.items.map((c) => (
                <Tr key={c.id}>
                  <Td>
                    <button
                      type="button"
                      onClick={() => abrirForm(c)}
                      disabled={!can(me, "clientes", "editar")}
                      className="text-left font-medium hover:underline disabled:hover:no-underline"
                    >
                      {c.nombre}
                    </button>
                    {c.notas && <p className="max-w-xs truncate text-sm text-fg-3">{c.notas}</p>}
                  </Td>
                  <Td className="tabular text-fg-2">{formatoDocumento(c.tipo_documento, c.documento) || "—"}</Td>
                  <Td className="text-fg-2">{c.telefono ?? "—"}</Td>
                  <Td className="text-fg-2">{c.email ?? "—"}</Td>
                  <Td align="right">
                    {can(me, "clientes", "eliminar") && (
                      <Button size="sm" variant="danger" onClick={() => setBorrar(c)}>
                        Eliminar
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          {lista.data.total > PAGINA && (
            <div className="flex items-center justify-between text-sm text-fg-3">
              <span>
                {offset + 1}–{Math.min(offset + PAGINA, lista.data.total)} de {lista.data.total}
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGINA))}>
                  Anteriores
                </Button>
                <Button size="sm" variant="ghost" disabled={offset + PAGINA >= lista.data.total} onClick={() => setOffset((o) => o + PAGINA)}>
                  Siguientes
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {form && <ClienteForm key={form.key} open={form.open} onOpenChange={(o) => setForm((f) => f && { ...f, open: o })} cliente={form.cliente} />}
      <Dialog
        open={borrar !== null}
        onOpenChange={(o) => !o && setBorrar(null)}
        title={`¿Eliminar a ${borrar?.nombre ?? ""}?`}
        description="Sus comandas y ventas se conservan, pero ya no quedarán asociadas a esta ficha."
        actions={
          <>
            <Button variant="ghost" onClick={() => setBorrar(null)}>
              Volver
            </Button>
            <Button loading={eliminar.isPending} onClick={() => borrar && eliminar.mutate(borrar)}>
              Eliminar
            </Button>
          </>
        }
      />
    </>
  );
}
