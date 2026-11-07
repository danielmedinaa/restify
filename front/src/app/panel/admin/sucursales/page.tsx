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
import { SucursalOut, type Sucursal } from "@/lib/api/schemas";
import { formatoRif } from "@/lib/fiscal";

export default function SucursalesPage() {
  const { data: me } = useMe();
  const lista = useQuery({ queryKey: ["sucursales"], queryFn: () => api("/sucursales", { schema: z.array(SucursalOut) }), enabled: can(me, "sucursales") });
  const form = useFormSheet<Sucursal>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [baja, setBaja] = useState<Sucursal | null>(null);
  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/sucursales/${v.id}` : "/sucursales"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: [["sucursales"], ["auth", "me"]],
    ok: (v) => (v.id ? "Sucursal actualizada" : "Sucursal creada"),
    onDone: form.cerrar,
    onError: setError,
  });
  const desactivar = useApiMutation<Sucursal>({ path: (s) => `/sucursales/${s.id}`, method: "DELETE", body: () => undefined, invalidate: [["sucursales"]], ok: "Sucursal desactivada", onDone: () => setBaja(null) });

  if (!can(me, "sucursales")) return <SinAcceso />;
  return (
    <>
      <PageHeader title="Sucursales" actions={can(me, "sucursales", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nueva sucursal</Button>} />
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.length === 0 ? (
        <EmptyState title="Sin sucursales" description="Crea la primera para empezar a cargar mesas, inventario y comandas." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Nombre</Th>
              <Th>RIF</Th>
              <Th>Dirección</Th>
              <Th>Teléfono</Th>
              <Th>Estado</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.map((s) => (
              <Tr key={s.id}>
                <Td>
                  <button type="button" disabled={!can(me, "sucursales", "editar")} onClick={() => (setError(null), form.abrir(s))} className="text-title font-medium hover:underline disabled:hover:no-underline">
                    {s.nombre}
                  </button>
                </Td>
                <Td className="tabular text-fg-2">{s.rif ? formatoRif(s.rif) : <span className="text-fg-4">Sin RIF</span>}</Td>
                <Td className="text-fg-2">{s.direccion ?? "—"}</Td>
                <Td className="text-fg-2">{s.telefono ?? "—"}</Td>
                <Td>
                  <StatusDot tone={s.activa ? "ok" : "muted"}>{s.activa ? "Activa" : "Inactiva"}</StatusDot>
                </Td>
                <Td align="right">
                  {s.activa && can(me, "sucursales", "eliminar") && (
                    <Button size="sm" variant="danger" onClick={() => setBaja(s)}>
                      Desactivar
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
          title={form.state.item ? form.state.item.nombre : "Nueva sucursal"}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const datos = {
              nombre: txt(f, "nombre"),
              direccion: txt(f, "direccion"),
              telefono: txt(f, "telefono"),
              activa: bool(f, "activa"),
              rif: txt(f, "rif")?.toUpperCase().replace(/[\s.-]/g, "") ?? null,
              razon_social: txt(f, "razon_social"),
              domicilio_fiscal: txt(f, "domicilio_fiscal"),
              cobra_igtf: bool(f, "cobra_igtf"),
              precios_incluyen_iva: bool(f, "precios_incluyen_iva"),
            };
            if (!datos.nombre) return setError({ title: "El nombre es obligatorio", tone: "warn" });
            const s = form.state?.item ?? null;
            guardar.mutate(s ? { id: s.id, body: cambios(s, datos) } : { body: datos });
          }}
        >
          <Field name="nombre" label="Nombre" defaultValue={form.state.item?.nombre ?? ""} maxLength={120} autoFocus />
          <Field name="direccion" label="Dirección" defaultValue={form.state.item?.direccion ?? ""} maxLength={255} />
          <Field name="telefono" label="Teléfono" type="tel" defaultValue={form.state.item?.telefono ?? ""} maxLength={40} />
          <Toggle name="activa" label="Activa" defaultChecked={form.state.item?.activa ?? true} />
          <fieldset className="flex flex-col gap-7 border-t border-line pt-7">
            <legend className="eyebrow -mb-2">Datos fiscales</legend>
            <p className="text-sm text-fg-3">Aparecen como emisor en el documento para facturar.</p>
            <Field name="rif" label="RIF" defaultValue={form.state.item?.rif ? formatoRif(form.state.item.rif) : ""} maxLength={20} placeholder="J-12345678-9" />
            <Field name="razon_social" label="Razón social" defaultValue={form.state.item?.razon_social ?? ""} maxLength={160} placeholder="Inversiones Restify, C.A." />
            <Field name="domicilio_fiscal" label="Domicilio fiscal" defaultValue={form.state.item?.domicilio_fiscal ?? ""} maxLength={255} hint="Si lo dejas vacío se usa la dirección." />
            <Toggle
              name="precios_incluyen_iva"
              label="Los precios incluyen IVA"
              hint="Apagado: el IVA de cada producto se suma encima del precio al vender (menú y caja muestran el total con IVA)."
              defaultChecked={form.state.item?.precios_incluyen_iva ?? true}
            />
            <Toggle
              name="cobra_igtf"
              label="Cobra IGTF"
              hint="Agente de percepción: se calcula el IGTF (3 %) sobre los pagos en divisas."
              defaultChecked={form.state.item?.cobra_igtf ?? false}
            />
          </fieldset>
        </FormSheet>
      )}
      <Confirmar
        open={baja !== null}
        onOpenChange={(o) => !o && setBaja(null)}
        title={`¿Desactivar ${baja?.nombre ?? ""}?`}
        description="No podrá abrir comandas ni recibir pedidos por QR. Sus datos se conservan."
        accion="Desactivar"
        pending={desactivar.isPending}
        onConfirm={() => baja && desactivar.mutate(baja)}
      />
    </>
  );
}
