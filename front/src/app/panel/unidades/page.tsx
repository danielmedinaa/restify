"use client";

import { useState } from "react";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { cantidad } from "@/features/inventario/unidad";
import { useUnidades } from "@/features/inventario/useUnidades";
import type { ErrorView } from "@/lib/api/errors";
import type { UnidadMedida } from "@/lib/api/schemas";

/** "Caja de 24" -> "caja_de_24": el código interno que se genera del nombre. */
function codigoDe(nombre: string): string {
  return nombre
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 20);
}

export default function UnidadesPage() {
  const { data: me } = useMe();
  const un = useUnidades();
  const form = useFormSheet<UnidadMedida>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [borrar, setBorrar] = useState<UnidadMedida | null>(null);
  const inv = [["unidades"], ["insumos"]];
  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/unidades/${v.id}` : "/unidades"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: inv,
    ok: (v) => (v.id ? "Unidad actualizada" : "Unidad creada"),
    onDone: form.cerrar,
    onError: setError,
  });
  const eliminar = useApiMutation<UnidadMedida>({ path: (u) => `/unidades/${u.id}`, method: "DELETE", body: () => undefined, invalidate: inv, ok: "Unidad eliminada", onDone: () => setBorrar(null) });

  if (!can(me, "insumos")) return <SinAcceso />;
  const u0 = form.state?.item ?? null;
  return (
    <>
      <PageHeader title="Unidades de medida" actions={can(me, "insumos", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nueva unidad</Button>} />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">
        En qué se mide cada insumo. Ya vienen gramos, kilos, mililitros, litros y unidades; agrega las que uses (cajas, botellas, porciones, libras…). Si una unidad no admite decimales, el stock y las recetas se cuentan en enteros.
      </p>
      {un.cargando ? (
        <ListLoading />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Unidad</Th>
              <Th>Abreviatura</Th>
              <Th>Cantidades</Th>
              <Th>Equivalencia</Th>
              <Th align="right">Insumos</Th>
              <Th>Estado</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {un.lista.map((u) => (
              <Tr key={u.id} className={u.activa ? "" : "opacity-50"}>
                <Td>
                  <button type="button" disabled={!can(me, "insumos", "editar")} onClick={() => (setError(null), form.abrir(u))} className="font-medium capitalize hover:underline disabled:hover:no-underline">
                    {u.nombre}
                  </button>
                  {u.es_base && <span className="ml-2 text-sm text-fg-4">de fábrica</span>}
                </Td>
                <Td className="tabular text-fg-2">{u.abreviatura}</Td>
                <Td className="text-fg-2">{u.permite_decimales ? "Con decimales" : "Solo enteras"}</Td>
                <Td className="tabular text-fg-2">{u.subunidad_abreviatura && u.factor_subunidad ? `1 ${u.abreviatura} = ${cantidad(u.factor_subunidad)} ${u.subunidad_abreviatura}` : <span className="text-fg-4">—</span>}</Td>
                <Td align="right" className="tabular text-fg-2">
                  {u.en_uso}
                </Td>
                <Td>
                  <StatusDot tone={u.activa ? "ok" : "muted"}>{u.activa ? "Activa" : "Inactiva"}</StatusDot>
                </Td>
                <Td align="right">
                  {!u.es_base && u.en_uso === 0 && can(me, "insumos", "eliminar") && (
                    <Button size="sm" variant="danger" onClick={() => setBorrar(u)}>
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
          title={u0 ? u0.nombre : "Nueva unidad de medida"}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const nombre = txt(f, "nombre");
            const abreviatura = txt(f, "abreviatura");
            if (!nombre || !abreviatura) return setError({ title: "Escribe el nombre y la abreviatura", tone: "warn" });
            const sub = txt(f, "subunidad_abreviatura");
            const factor = (txt(f, "factor_subunidad") ?? "").replace(",", ".");
            if (!!sub !== !!factor) return setError({ title: "La equivalencia necesita la unidad menor y cuántas caben (o deja ambas vacías)", tone: "warn" });
            if (factor && !(/^\d+(\.\d{1,3})?$/.test(factor) && Number(factor) > 1)) return setError({ title: "La equivalencia debe ser un número mayor que 1", tone: "warn" });
            const datos = { nombre, abreviatura, permite_decimales: bool(f, "permite_decimales"), subunidad_abreviatura: sub, factor_subunidad: factor || null, activa: bool(f, "activa") };
            if (u0) return guardar.mutate({ id: u0.id, body: datos });
            const codigo = codigoDe(nombre);
            if (!codigo) return setError({ title: "El nombre necesita letras o números", tone: "warn" });
            guardar.mutate({ body: { ...datos, codigo } });
          }}
        >
          <Field name="nombre" label="Nombre (plural)" defaultValue={u0?.nombre ?? ""} maxLength={60} placeholder="cajas, botellas, libras…" autoFocus />
          <Field name="abreviatura" label="Abreviatura" defaultValue={u0?.abreviatura ?? ""} maxLength={12} placeholder="caja, bot, lb…" hint="Es la que se ve junto a las cantidades." />
          <Toggle name="permite_decimales" label="Admite decimales" hint="Apágalo para cosas que se cuentan enteras (botellas, cajas, porciones)." defaultChecked={u0?.permite_decimales ?? true} />
          <fieldset className="flex flex-col gap-3">
            <legend className="eyebrow pb-1">Unidad menor (opcional)</legend>
            <p className="text-sm text-fg-3">Para escribir cantidades chicas en las recetas: si el insumo está en kilos, la receta puede decir 150 g (1 kg = 1000 g).</p>
            <div className="grid grid-cols-2 gap-4">
              <Field name="subunidad_abreviatura" label="Unidad menor" defaultValue={u0?.subunidad_abreviatura ?? ""} maxLength={12} placeholder="g" />
              <Field name="factor_subunidad" label={`Cuántas caben en 1 ${u0?.abreviatura ?? "unidad"}`} inputMode="decimal" defaultValue={u0?.factor_subunidad ? cantidad(u0.factor_subunidad).replace(/\./g, "") : ""} placeholder="1000" />
            </div>
          </fieldset>
          {u0 && <Toggle name="activa" label="Activa" hint="Las inactivas no se ofrecen al crear insumos." defaultChecked={u0.activa} />}
        </FormSheet>
      )}
      <Confirmar
        open={borrar !== null}
        onOpenChange={(o) => !o && setBorrar(null)}
        title={`¿Eliminar ${borrar?.nombre ?? ""}?`}
        description="Ningún insumo la usa, así que se puede quitar sin afectar nada."
        accion="Eliminar"
        pending={eliminar.isPending}
        onConfirm={() => borrar && eliminar.mutate(borrar)}
      />
    </>
  );
}
