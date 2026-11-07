"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { TextArea } from "@/components/ui/TextArea";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, cambios, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { ProveedorOut, type Proveedor } from "@/lib/api/schemas";
import { formatoRif } from "@/lib/fiscal";

export default function ProveedoresPage() {
  const { data: me } = useMe();
  const lista = useQuery({ queryKey: ["proveedores"], queryFn: () => api("/proveedores", { schema: z.array(ProveedorOut) }), enabled: can(me, "compras") });
  const form = useFormSheet<Proveedor>();
  const [error, setError] = useState<ErrorView | null>(null);
  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/proveedores/${v.id}` : "/proveedores"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: [["proveedores"]],
    ok: (v) => (v.id ? "Proveedor actualizado" : "Proveedor registrado"),
    onDone: form.cerrar,
    onError: setError,
  });

  if (!can(me, "compras")) return <SinAcceso />;
  return (
    <>
      <PageHeader title="Proveedores" actions={can(me, "compras", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nuevo proveedor</Button>} />
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.length === 0 ? (
        <EmptyState title="Sin proveedores" description="Registra a quien te vende la carne, el pan, las bebidas…" />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Proveedor</Th>
              <Th>RIF</Th>
              <Th>Contacto</Th>
              <Th>Estado</Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.map((p) => (
              <Tr key={p.id} className={p.activo ? "" : "opacity-50"}>
                <Td>
                  <button type="button" disabled={!can(me, "compras", "editar")} onClick={() => (setError(null), form.abrir(p))} className="font-medium hover:underline disabled:hover:no-underline">
                    {p.nombre}
                  </button>
                </Td>
                <Td className="tabular text-fg-2">{p.rif ? formatoRif(p.rif) : "—"}</Td>
                <Td className="text-fg-2">{[p.contacto, p.telefono].filter(Boolean).join(" · ") || "—"}</Td>
                <Td>
                  <StatusDot tone={p.activo ? "ok" : "muted"}>{p.activo ? "Activo" : "Inactivo"}</StatusDot>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
      {form.state && (
        <FormSheet
          key={form.state.key}
          open={form.state.open}
          onOpenChange={form.onOpenChange}
          title={form.state.item ? form.state.item.nombre : "Nuevo proveedor"}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const datos = {
              nombre: txt(f, "nombre"),
              rif: txt(f, "rif")?.toUpperCase().replace(/[\s.-]/g, "") ?? null,
              contacto: txt(f, "contacto"),
              telefono: txt(f, "telefono"),
              email: txt(f, "email"),
              notas: txt(f, "notas"),
              activo: bool(f, "activo"),
            };
            if (!datos.nombre) return setError({ title: "Escribe el nombre del proveedor", tone: "warn" });
            const p = form.state?.item ?? null;
            guardar.mutate(p ? { id: p.id, body: cambios(p, datos) } : { body: datos });
          }}
        >
          <Field name="nombre" label="Nombre" defaultValue={form.state.item?.nombre ?? ""} maxLength={160} autoFocus />
          <Field name="rif" label="RIF" defaultValue={form.state.item?.rif ? formatoRif(form.state.item.rif) : ""} maxLength={20} placeholder="J-12345678-9" />
          <div className="grid grid-cols-2 gap-4">
            <Field name="contacto" label="Contacto" defaultValue={form.state.item?.contacto ?? ""} maxLength={120} />
            <Field name="telefono" label="Teléfono" type="tel" defaultValue={form.state.item?.telefono ?? ""} maxLength={40} />
          </div>
          <Field name="email" label="Correo" type="email" defaultValue={form.state.item?.email ?? ""} maxLength={255} />
          <TextArea name="notas" label="Notas" defaultValue={form.state.item?.notas ?? ""} maxLength={2000} placeholder="Días de entrega, condiciones…" />
          <Toggle name="activo" label="Activo" defaultChecked={form.state.item?.activo ?? true} />
        </FormSheet>
      )}
    </>
  );
}
