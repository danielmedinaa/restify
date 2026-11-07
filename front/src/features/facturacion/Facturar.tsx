"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import Link from "next/link";
import { useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ListError } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/Status";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { useMonedas } from "@/features/comandas/queries";
import { Confirmar, txt } from "@/features/crud/crud";
import { useSucursal } from "@/features/panel/sucursal";
import { createStore } from "@/features/publico/stores";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { ClienteOut, DatosFiscalesOut, Pagina, TIPOS_DOCUMENTO, type Cliente, type DatosFiscales } from "@/lib/api/schemas";
import { consultarCedula } from "@/features/clientes/consulta";
import { formatoDocumento, TIPO_DOCUMENTO_LABEL } from "@/lib/fiscal";
import { smooth } from "@/lib/motion";
import { Documento, type Formato } from "./Documento";

// El formato elegido se recuerda en este equipo (cada caja tiene su impresora)
const formatoGuardado = createStore<Formato>("restify:formato-factura", "ticket");
const sinSuscripcion = () => () => {};
const registrada = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Pantalla para facturar a mano una venta: documento imprimible + registro del número usado. */
export function Facturar({ id }: { id: number }) {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const { data: monedas } = useMonedas(actual?.id);
  const qc = useQueryClient();
  const key = ["ventas", "fiscal", id];
  const datos = useQuery({ queryKey: key, queryFn: () => api(`/ventas/${id}/fiscal`, { schema: DatosFiscalesOut }) });
  const formato = formatoGuardado.use();
  const [editando, setEditando] = useState(false);
  const [quitar, setQuitar] = useState(false);
  const [anular, setAnular] = useState(false);
  const [deshaciendoAnulacion, setDeshaciendoAnulacion] = useState(false);
  const [error, setError] = useState<ErrorView | null>(null);
  // Registrar al receptor como cliente: el cliente que ya existe con esa cédula/RIF, y la
  // factura en espera mientras se pregunta si se registra uno nuevo
  const [existente, setExistente] = useState<Cliente | null>(null);
  const [pregunta, setPregunta] = useState<Record<string, unknown> | null>(null);
  const razonRef = useRef<HTMLInputElement>(null);
  const domicilioRef = useRef<HTMLInputElement>(null);
  const tipoRef = useRef<HTMLSelectElement>(null);
  // El portal de impresión necesita document: solo existe ya hidratado en el navegador
  const montado = useSyncExternalStore(sinSuscripcion, () => true, () => false);
  const elegirFormato = (f: Formato) => formatoGuardado.set(() => f);

  /** Al salir del campo de cédula/RIF: si ya es cliente, se completan sus datos. */
  async function buscarCliente(doc: string) {
    const numero = doc.replace(/[\s.-]/g, "").toUpperCase().replace(/^[VEJGP]/, "");
    if (!/^\d{5,10}$/.test(numero) || !can(me, "clientes")) return setExistente(null);
    try {
      const r = await api("/clientes", { query: { q: numero, limite: 10 }, schema: Pagina(ClienteOut) });
      const tipo = tipoRef.current?.value || null;
      const c = r.items.find((x) => x.documento === numero && (!tipo || x.tipo_documento === tipo)) ?? null;
      setExistente(c);
      if (!c) {
        // No es cliente: si es una persona (V/E), se intenta el nombre en el registro público
        if (razonRef.current && !razonRef.current.value.trim()) {
          const r = await consultarCedula(tipo, numero);
          if (r && razonRef.current && !razonRef.current.value.trim()) razonRef.current.value = r.nombre;
        }
        return;
      }
      if (tipoRef.current && !tipoRef.current.value && c.tipo_documento) tipoRef.current.value = c.tipo_documento;
      if (razonRef.current && !razonRef.current.value) razonRef.current.value = c.nombre;
      if (domicilioRef.current && !domicilioRef.current.value && c.direccion) domicilioRef.current.value = c.direccion;
    } catch {
      setExistente(null);
    }
  }

  const alListo = (d: DatosFiscales, msg: string) => {
    qc.setQueryData(key, d);
    void qc.invalidateQueries({ queryKey: ["ventas"], predicate: (q) => q.queryKey[1] !== "fiscal" });
    toast({ title: msg, tone: "ok", duration: 3000 });
  };
  const registrar = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/ventas/${id}/factura`, { method: "PUT", body, schema: DatosFiscalesOut }),
    onSuccess: (d, body) => {
      setEditando(false);
      setPregunta(null);
      alListo(d, `Factura ${d.numero_factura} registrada${body.guardar_cliente && !existente ? " y cliente guardado" : ""}`);
      if (body.guardar_cliente) void qc.invalidateQueries({ queryKey: ["clientes"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  const deshacer = useMutation({
    mutationFn: () => api(`/ventas/${id}/factura`, { method: "DELETE", schema: DatosFiscalesOut }),
    onSuccess: (d) => {
      setQuitar(false);
      alListo(d, "La venta volvió a pendientes por facturar");
    },
    onError: (e) => setError(describeError(e)),
  });

  const anularFactura = useMutation({
    mutationFn: (body: { nota_credito_numero: string; nota_credito_control: string; motivo: string }) =>
      api(`/ventas/${id}/anulacion`, { method: "PUT", body, schema: DatosFiscalesOut }),
    onSuccess: (d) => {
      setAnular(false);
      setError(null);
      alListo(d, `Factura anulada con la nota de crédito ${d.nota_credito_numero}`);
    },
    onError: (e) => setError(describeError(e)),
  });
  const quitarAnulacion = useMutation({
    mutationFn: () => api(`/ventas/${id}/anulacion`, { method: "DELETE", schema: DatosFiscalesOut }),
    onSuccess: (d) => {
      setDeshaciendoAnulacion(false);
      alListo(d, "Anulación deshecha");
    },
    onError: (e) => setError(describeError(e)),
  });

  const simbolos = Object.fromEntries((monedas ?? []).map((m) => [m.codigo, m.simbolo]));
  const d = datos.data;
  const facturada = !!d?.numero_factura;
  const mostrarForm = !!d && can(me, "ventas", "editar") && (!facturada || editando);

  return (
    <>
      <PageHeader
        eyebrow={
          <Link href="/panel/ventas" className="hover:text-fg">
            Ventas · #{id}
          </Link>
        }
        title="Para facturar"
        actions={
          <>
            <Segmented
              label="Formato de impresión"
              size="sm"
              value={formato}
              onChange={elegirFormato}
              options={[
                { value: "ticket", label: "Ticket 80 mm" },
                { value: "carta", label: "Carta" },
              ]}
            />
            <Button onClick={() => window.print()} disabled={!d}>
              Imprimir
            </Button>
          </>
        }
      />

      {datos.isError ? (
        <ListError error={datos.error} />
      ) : !d ? (
        <div className="grid gap-12 desk:grid-cols-12">
          <Skeleton className="h-[34rem] desk:col-span-7" />
          <Skeleton className="h-72 desk:col-span-5" />
        </div>
      ) : (
        <div className="grid items-start gap-12 desk:grid-cols-12">
          {/* Vista previa: el papel sobre el lienzo oscuro */}
          <div className="flex justify-center rounded-sheet bg-wash/60 px-4 py-10 desk:col-span-7 desk:sticky desk:top-24">
            <motion.div
              key={formato}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={smooth}
              className="shadow-[0_30px_80px_-30px_rgba(0,0,0,0.7)]"
            >
              <Documento d={d} formato={formato} simbolos={simbolos} />
            </motion.div>
          </div>

          <aside className="flex flex-col gap-10 desk:col-span-5">
            <section className="flex flex-col gap-3">
              <StatusDot tone={facturada ? "ok" : "warn"}>{facturada ? "Facturada" : "Pendiente por facturar"}</StatusDot>
              {facturada ? (
                <div className="flex flex-col gap-1">
                  <p className="font-display text-display-s leading-none">N° {d.numero_factura}</p>
                  <p className="text-fg-2">
                    Control {d.numero_control}
                    {d.facturada_en && <span className="text-fg-3"> · {registrada.format(new Date(d.facturada_en))}</span>}
                  </p>
                </div>
              ) : (
                <p className="max-w-md text-base text-fg-2">
                  Imprime este documento, copia los datos en tu talonario o máquina fiscal y registra aquí el número de factura y de control que usaste.
                </p>
              )}
              {d.anulada_en && (
                <div className="flex flex-col gap-1 border-l-2 border-err pl-4">
                  <StatusDot tone="err">Factura anulada</StatusDot>
                  <p className="text-base text-fg-2">
                    Nota de crédito N° {d.nota_credito_numero} · control {d.nota_credito_control}
                  </p>
                  <p className="text-sm text-fg-3">
                    {registrada.format(new Date(d.anulada_en))} · {d.motivo_anulacion}
                  </p>
                  {can(me, "ventas", "eliminar") && (
                    <Button size="sm" variant="ghost" className="mt-1 self-start px-0" onClick={() => setDeshaciendoAnulacion(true)}>
                      Deshacer anulación
                    </Button>
                  )}
                </div>
              )}
              {facturada && !editando && !d.anulada_en && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {can(me, "ventas", "eliminar") && (
                    <Button size="sm" variant="line" onClick={() => (setError(null), setAnular(true))}>
                      Anular con nota de crédito
                    </Button>
                  )}
                  {can(me, "ventas", "editar") && (
                    <Button size="sm" variant="line" onClick={() => (setError(null), setEditando(true))}>
                      Corregir datos
                    </Button>
                  )}
                  {can(me, "ventas", "eliminar") && (
                    <Button size="sm" variant="danger" onClick={() => setQuitar(true)}>
                      Quitar registro
                    </Button>
                  )}
                </div>
              )}
            </section>

            {d.avisos.length > 0 && (
              <ul className="flex flex-col gap-2 border-l border-warn/60 pl-4 text-sm text-fg-2" aria-label="Avisos">
                {d.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}

            {mostrarForm && (
              <form
                noValidate
                className="flex flex-col gap-7"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  const body = {
                    numero_factura: txt(f, "numero_factura"),
                    numero_control: txt(f, "numero_control"),
                    receptor_tipo_documento: txt(f, "receptor_tipo_documento"),
                    receptor_documento: txt(f, "receptor_documento"),
                    receptor_razon_social: txt(f, "receptor_razon_social"),
                    receptor_domicilio: txt(f, "receptor_domicilio"),
                  };
                  if (!body.numero_factura || !body.numero_control) return setError({ title: "Escribe el número de factura y el de control", tone: "warn" });
                  if (body.receptor_documento && !body.receptor_tipo_documento) return setError({ title: "Elige el tipo de documento del cliente", tone: "warn" });
                  setError(null);
                  // Ya es cliente: se asocia a la venta sin preguntar. Si no, se ofrece registrarlo.
                  if (body.receptor_documento && existente) return registrar.mutate({ ...body, guardar_cliente: true });
                  if (body.receptor_documento && !d.cliente_id && can(me, "clientes", "crear")) return setPregunta(body);
                  registrar.mutate(body);
                }}
              >
                <h2 className="eyebrow">{facturada ? "Corregir registro" : "Registrar factura"}</h2>
                <div className="grid grid-cols-2 gap-6">
                  <Field name="numero_factura" label="N° de factura" defaultValue={d.numero_factura ?? ""} maxLength={40} placeholder="000123" autoFocus={!facturada} />
                  <Field name="numero_control" label="N° de control" defaultValue={d.numero_control ?? ""} maxLength={40} placeholder="00-000123" />
                </div>
                <fieldset className="flex flex-col gap-7">
                  <legend className="eyebrow mb-1 text-fg-3">Cliente en la factura · vacío = consumidor final</legend>
                  <Field ref={razonRef} name="receptor_razon_social" label="Nombre o razón social" defaultValue={d.receptor.razon_social ?? ""} maxLength={160} />
                  <div className="grid grid-cols-[8.5rem_1fr] items-end gap-4">
                    <Select ref={tipoRef} name="receptor_tipo_documento" label="Tipo" defaultValue={d.receptor.tipo_documento ?? ""}>
                      <option value="">—</option>
                      {TIPOS_DOCUMENTO.map((t) => (
                        <option key={t} value={t}>
                          {TIPO_DOCUMENTO_LABEL[t]}
                        </option>
                      ))}
                    </Select>
                    <Field
                      name="receptor_documento"
                      label="Cédula o RIF"
                      inputMode="numeric"
                      defaultValue={d.receptor.documento ?? ""}
                      maxLength={20}
                      placeholder="12345678"
                      onBlur={(e) => void buscarCliente(e.currentTarget.value)}
                      onChange={() => existente && setExistente(null)}
                    />
                  </div>
                  {existente && <StatusDot tone="ok">Cliente registrado: {existente.nombre}</StatusDot>}
                  <Field ref={domicilioRef} name="receptor_domicilio" label="Domicilio fiscal" defaultValue={d.receptor.domicilio ?? ""} maxLength={255} />
                </fieldset>
                {error && <ErrorBox error={error} onClose={() => setError(null)} />}
                <div className="flex gap-2">
                  <Button type="submit" size="lg" loading={registrar.isPending} className="flex-1">
                    {facturada ? "Guardar corrección" : "Marcar como facturada"}
                  </Button>
                  {editando && (
                    <Button size="lg" variant="ghost" onClick={() => setEditando(false)}>
                      Cancelar
                    </Button>
                  )}
                </div>
              </form>
            )}

            {facturada && !editando && d.receptor.rif && (
              <p className="text-sm text-fg-3">{`Facturada a ${d.receptor.razon_social} · ${formatoDocumento(d.receptor.tipo_documento, d.receptor.documento)}`}</p>
            )}
          </aside>
        </div>
      )}

      <Dialog
        open={pregunta !== null}
        onOpenChange={(o) => !o && setPregunta(null)}
        title={`¿Registrar a ${String(pregunta?.receptor_razon_social ?? "este cliente")} como cliente?`}
        description="Queda guardado con su cédula o RIF para la próxima factura y se asocia a esta venta."
        actions={
          <>
            <Button variant="ghost" disabled={registrar.isPending} onClick={() => pregunta && registrar.mutate(pregunta)}>
              No, solo facturar
            </Button>
            <Button loading={registrar.isPending} onClick={() => pregunta && registrar.mutate({ ...pregunta, guardar_cliente: true })}>
              Sí, registrar cliente
            </Button>
          </>
        }
      />

      <AnularDialog
        open={anular}
        onOpenChange={setAnular}
        numeroFactura={d?.numero_factura ?? ""}
        pending={anularFactura.isPending}
        error={error}
        onClearError={() => setError(null)}
        onSubmit={(body) => anularFactura.mutate(body)}
      />
      <Confirmar
        open={deshaciendoAnulacion}
        onOpenChange={setDeshaciendoAnulacion}
        title="¿Deshacer la anulación?"
        description="La factura vuelve a estar vigente en el libro de ventas. Úsalo solo si la nota de crédito se cargó por error."
        accion="Deshacer anulación"
        pending={quitarAnulacion.isPending}
        onConfirm={() => quitarAnulacion.mutate()}
      />
      <Confirmar
        open={quitar}
        onOpenChange={setQuitar}
        title="¿Quitar el registro de la factura?"
        description="La venta vuelve a pendientes por facturar y sale del libro de ventas. Úsalo solo si el número se cargó en la venta equivocada."
        accion="Quitar registro"
        pending={deshacer.isPending}
        onConfirm={() => deshacer.mutate()}
      />

      {/* Copia fuera del layout del panel: es lo único que se imprime */}
      {montado &&
        d &&
        createPortal(
          <div className="print-portal" data-formato={formato}>
            <Documento d={d} formato={formato} simbolos={simbolos} />
          </div>,
          document.body,
        )}
    </>
  );
}

/** Registra la nota de crédito (hecha a mano) que anula la factura: queda en el libro de ventas junto a ella. */
function AnularDialog({
  open,
  onOpenChange,
  numeroFactura,
  pending,
  error,
  onClearError,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  numeroFactura: string;
  pending: boolean;
  error: ErrorView | null;
  onClearError: () => void;
  onSubmit: (b: { nota_credito_numero: string; nota_credito_control: string; motivo: string }) => void;
}) {
  const [numero, setNumero] = useState("");
  const [control, setControl] = useState("");
  const [motivo, setMotivo] = useState("");
  const listo = numero.trim() && control.trim() && motivo.trim().length >= 3;
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Anular la factura N° ${numeroFactura}`}
      description="Emite primero la nota de crédito en tu talonario o máquina fiscal y registra aquí sus números. La factura y su nota quedan en el libro de ventas."
      actions={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Volver
          </Button>
          <Button variant="danger" loading={pending} disabled={!listo} onClick={() => onSubmit({ nota_credito_numero: numero.trim(), nota_credito_control: control.trim(), motivo: motivo.trim() })}>
            Anular factura
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-2 gap-4">
          <Field label="N° de nota de crédito" value={numero} onChange={(e) => (onClearError(), setNumero(e.target.value))} maxLength={40} placeholder="000045" autoFocus />
          <Field label="N° de control" value={control} onChange={(e) => (onClearError(), setControl(e.target.value))} maxLength={40} placeholder="00-000045" />
        </div>
        <Field label="Motivo" value={motivo} onChange={(e) => (onClearError(), setMotivo(e.target.value))} maxLength={255} placeholder="Error en el monto, devolución…" />
        {error && <ErrorBox error={error} onClose={onClearError} />}
      </div>
    </Dialog>
  );
}
