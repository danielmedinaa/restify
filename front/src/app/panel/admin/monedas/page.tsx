"use client";

import { useQuery } from "@tanstack/react-query";
import Big from "big.js";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, cambios, Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { MonedaOut, type Moneda } from "@/lib/api/schemas";
import { formatAmount } from "@/lib/money";

const fecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** "1 USD = 38,45 Bs" o "1 Bs = 0,026 USD", según la operación. */
function tasaLegible(m: Moneda, principal: Moneda | undefined) {
  if (m.es_principal || !principal) return "Moneda principal";
  const tasa = formatAmount(m.tasa.replace(/0+$/, "").replace(/\.$/, ""), Math.max(2, (m.tasa.split(".")[1] ?? "").replace(/0+$/, "").length));
  return m.operacion === "multiplicar" ? `1 ${principal.codigo} = ${tasa} ${m.codigo}` : `1 ${m.codigo} = ${tasa} ${principal.codigo}`;
}

export default function MonedasPage() {
  const { data: me } = useMe();
  const lista = useQuery({ queryKey: ["monedas"], queryFn: () => api("/monedas", { schema: z.array(MonedaOut) }), enabled: can(me, "monedas") });
  const form = useFormSheet<Moneda>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [principal, setPrincipal] = useState<Moneda | null>(null);
  const inv = [["monedas"], ["menu"], ["comanda"]];
  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/monedas/${v.id}` : "/monedas"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: inv,
    ok: (v) => (v.id ? "Tasa actualizada" : "Moneda creada"),
    onDone: form.cerrar,
    onError: setError,
  });
  const hacerPrincipal = useApiMutation<Moneda>({ path: (m) => `/monedas/${m.id}/principal`, method: "POST", body: () => undefined, invalidate: inv, ok: (m) => `${m.codigo} es ahora la moneda principal`, onDone: () => setPrincipal(null) });

  if (!can(me, "monedas")) return <SinAcceso />;
  const actualPrincipal = lista.data?.find((m) => m.es_principal);
  const editar = can(me, "monedas", "editar");

  return (
    <>
      <PageHeader
        eyebrow={actualPrincipal ? `Principal: ${actualPrincipal.codigo}` : undefined}
        title="Monedas"
        actions={can(me, "monedas", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nueva moneda</Button>}
      />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">
        Los precios se cargan en la moneda principal. Las demás se calculan con su tasa al momento de mostrar y de cobrar; cada pago guarda la tasa que se usó.
      </p>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Moneda</Th>
              <Th>Tasa</Th>
              <Th>Uso fiscal</Th>
              <Th>Actualizada</Th>
              <Th>Estado</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.map((m) => (
              <Tr key={m.id}>
                <Td>
                  <button type="button" disabled={!editar} onClick={() => (setError(null), form.abrir(m))} className="flex items-baseline gap-3 hover:underline disabled:hover:no-underline">
                    <span className="font-display text-display-s leading-none">{m.codigo}</span>
                    <span className="text-fg-2">
                      {m.nombre} · {m.simbolo}
                    </span>
                  </button>
                </Td>
                <Td className="tabular text-fg-2">{tasaLegible(m, actualPrincipal)}</Td>
                <Td className="text-sm text-fg-2">{[m.es_fiscal && "Moneda de la factura", m.es_divisa && "Divisa (IGTF)"].filter(Boolean).join(" · ") || <span className="text-fg-4">—</span>}</Td>
                <Td className="text-sm text-fg-3">{fecha.format(new Date(m.updated_at))}</Td>
                <Td>
                  <StatusDot tone={m.es_principal ? "ok" : m.activa ? "neutral" : "muted"}>{m.es_principal ? "Principal" : m.activa ? "Activa" : "Inactiva"}</StatusDot>
                </Td>
                <Td align="right">
                  {!m.es_principal && editar && (
                    <Button size="sm" variant="ghost" onClick={() => setPrincipal(m)}>
                      Hacer principal
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
          title={form.state.item ? `${form.state.item.codigo} · ${form.state.item.nombre}` : "Nueva moneda"}
          description={actualPrincipal && !form.state.item?.es_principal ? `La tasa se expresa contra ${actualPrincipal.codigo}.` : undefined}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const m = form.state?.item ?? null;
            const tasa = (txt(f, "tasa") ?? "").replace(",", ".");
            const datos: Record<string, unknown> = {
              nombre: txt(f, "nombre"),
              simbolo: txt(f, "simbolo"),
              activa: bool(f, "activa"),
              es_divisa: bool(f, "es_divisa"),
              es_fiscal: bool(f, "es_fiscal"),
            };
            if (!m?.es_principal) Object.assign(datos, { tasa, operacion: f.get("operacion") });
            if (!m) datos.codigo = (txt(f, "codigo") ?? "").toUpperCase();
            if (!datos.nombre || !datos.simbolo || (!m && !datos.codigo)) return setError({ title: "Completa código, nombre y símbolo", tone: "warn" });
            if (!m?.es_principal && !/^\d+(\.\d{1,6})?$/.test(tasa)) return setError({ title: "La tasa debe ser un número (hasta 6 decimales)", tone: "warn" });
            // La tasa llega como "38.450000": se compara como decimal exacto, no como texto
            if (m && typeof datos.tasa === "string" && new Big(datos.tasa).eq(m.tasa)) delete datos.tasa;
            guardar.mutate(m ? { id: m.id, body: cambios(m, datos) } : { body: datos });
          }}
        >
          {!form.state.item && <Field name="codigo" label="Código" maxLength={10} placeholder="VES, COP, EUR…" autoFocus />}
          <Field name="nombre" label="Nombre" defaultValue={form.state.item?.nombre ?? ""} maxLength={60} />
          <Field name="simbolo" label="Símbolo" defaultValue={form.state.item?.simbolo ?? ""} maxLength={8} />
          {!form.state.item?.es_principal && (
            <>
              <Field name="tasa" label="Tasa" inputMode="decimal" defaultValue={form.state.item?.tasa.replace(/0+$/, "").replace(/\.$/, "") ?? ""} placeholder="38,45" />
              <Select name="operacion" label="Cómo se aplica" defaultValue={form.state.item?.operacion ?? "multiplicar"}>
                <option value="multiplicar">1 {actualPrincipal?.codigo ?? "principal"} = tasa en esta moneda</option>
                <option value="dividir">1 de esta moneda = tasa en {actualPrincipal?.codigo ?? "principal"}</option>
              </Select>
            </>
          )}
          <Toggle name="activa" label="Activa" hint="Las inactivas no aparecen en caja ni en el menú." defaultChecked={form.state.item?.activa ?? true} />
          <Toggle name="es_fiscal" label="Moneda de la factura" hint="Los bolívares: el documento para facturar se expresa en esta moneda. Solo puede haber una." defaultChecked={form.state.item?.es_fiscal ?? false} />
          <Toggle name="es_divisa" label="Es divisa" hint="Moneda extranjera: sus pagos generan IGTF en las sucursales que lo cobran." defaultChecked={form.state.item?.es_divisa ?? false} />
        </FormSheet>
      )}
      <Confirmar
        open={principal !== null}
        onOpenChange={(o) => !o && setPrincipal(null)}
        title={`¿${principal?.codigo ?? ""} como moneda principal?`}
        description="Los precios pasan a leerse en esta moneda y su tasa queda en 1. Revisa después las tasas de las demás monedas."
        accion="Cambiar principal"
        pending={hacerPrincipal.isPending}
        onConfirm={() => principal && hacerPrincipal.mutate(principal)}
      />
    </>
  );
}
