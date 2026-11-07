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
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, cambios, Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { EstacionOut, type Estacion } from "@/lib/api/schemas";

export default function EstacionesPage() {
  const { data: me } = useMe();
  const lista = useQuery({ queryKey: ["estaciones"], queryFn: () => api("/estaciones", { schema: z.array(EstacionOut) }), enabled: can(me, "categorias") });
  const form = useFormSheet<Estacion>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [borrar, setBorrar] = useState<Estacion | null>(null);
  const inv = [["estaciones"], ["productos"], ["menu"]];
  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/estaciones/${v.id}` : "/estaciones"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: inv,
    ok: (v) => (v.id ? "Estación actualizada" : "Estación creada"),
    onDone: form.cerrar,
    onError: setError,
  });
  const eliminar = useApiMutation<Estacion>({ path: (c) => `/estaciones/${c.id}`, method: "DELETE", body: () => undefined, invalidate: inv, ok: "Estación eliminada", onDone: () => setBorrar(null) });

  if (!can(me, "categorias")) return <SinAcceso />;
  const ordenadas = [...(lista.data ?? [])].sort((a, b) => a.orden - b.orden || a.nombre.localeCompare(b.nombre));
  return (
    <>
      <PageHeader title="Estaciones" actions={can(me, "categorias", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nueva estación</Button>} />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">Lugares donde se prepara cada producto (Cocina, Barra, Parrilla…). Cada producto se asigna a una y esa pantalla recibe sus platos.</p>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : ordenadas.length === 0 ? (
        <EmptyState title="Sin estaciones" description="Crea Cocina, Barra, Parrilla… y asígnalas a tus productos." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Orden</Th>
              <Th>Estación</Th>
              <Th>Estado</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {ordenadas.map((c) => (
              <Tr key={c.id}>
                <Td className="w-20 tabular text-fg-3">{c.orden}</Td>
                <Td>
                  <button type="button" disabled={!can(me, "categorias", "editar")} onClick={() => (setError(null), form.abrir(c))} className="font-display text-display-s leading-none hover:underline disabled:hover:no-underline">
                    {c.nombre}
                  </button>
                </Td>
                <Td>
                  <StatusDot tone={c.activa ? "ok" : "muted"}>{c.activa ? "Activa" : "Inactiva"}</StatusDot>
                </Td>
                <Td align="right">
                  {can(me, "categorias", "eliminar") && (
                    <Button size="sm" variant="danger" onClick={() => setBorrar(c)}>
                      Eliminar
                    </Button>
                  )}
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
          title={form.state.item ? form.state.item.nombre : "Nueva estación"}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const datos = { nombre: txt(f, "nombre"), orden: Number(txt(f, "orden") ?? 0), activa: bool(f, "activa") };
            if (!datos.nombre) return setError({ title: "Ponle un nombre", tone: "warn" });
            const c = form.state?.item ?? null;
            guardar.mutate(c ? { id: c.id, body: cambios(c, datos) } : { body: datos });
          }}
        >
          <Field name="nombre" label="Nombre" defaultValue={form.state.item?.nombre ?? ""} maxLength={80} autoFocus />
          <Field name="orden" label="Orden" type="number" defaultValue={form.state.item?.orden ?? 0} />
          <Toggle name="activa" label="Activa" defaultChecked={form.state.item?.activa ?? true} />
        </FormSheet>
      )}
      <Confirmar
        open={borrar !== null}
        onOpenChange={(o) => !o && setBorrar(null)}
        title={`¿Eliminar ${borrar?.nombre ?? ""}?`}
        description="Sus productos quedan sin estación y se verán en todas las pantallas de preparación."
        accion="Eliminar"
        pending={eliminar.isPending}
        onConfirm={() => borrar && eliminar.mutate(borrar)}
      />
    </>
  );
}
