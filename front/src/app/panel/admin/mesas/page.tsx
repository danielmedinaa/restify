"use client";

import { useQuery } from "@tanstack/react-query";
import { Copy, Download, ExternalLink } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Sheet } from "@/components/ui/Sheet";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { toast } from "@/components/ui/Toast";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, cambios, Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { MesaOut, MesaQrOut, type Mesa } from "@/lib/api/schemas";

export default function MesasAdminPage() {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const key = ["mesas", "admin", "sucursal", actual?.id];
  const mesas = useQuery({
    queryKey: key,
    queryFn: () => api("/mesas", { query: { sucursal_id: actual?.id }, schema: z.array(MesaOut) }),
    enabled: !!actual && can(me, "mesas"),
  });
  const form = useFormSheet<Mesa>();
  const [qr, setQr] = useState<Mesa | null>(null);
  const [baja, setBaja] = useState<Mesa | null>(null);
  const [error, setError] = useState<ErrorView | null>(null);
  const invalidate = [["mesas"]];

  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/mesas/${v.id}` : "/mesas"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate,
    ok: (v) => (v.id ? "Mesa actualizada" : "Mesa creada"),
    onDone: form.cerrar,
    onError: setError,
  });
  const toggleQr = useApiMutation<Mesa>({ path: (m) => `/mesas/${m.id}`, method: "PATCH", body: (m) => ({ qr_habilitado: !m.qr_habilitado }), invalidate });
  const desactivar = useApiMutation<Mesa>({ path: (m) => `/mesas/${m.id}`, method: "DELETE", body: () => undefined, invalidate, ok: "Mesa desactivada", onDone: () => setBaja(null) });

  if (!can(me, "mesas")) return <SinAcceso />;
  const editar = can(me, "mesas", "editar");
  const lista = mesas.data ?? [];

  return (
    <>
      <PageHeader
        eyebrow={actual?.nombre}
        title="Mesas y QR"
        actions={can(me, "mesas", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nueva mesa</Button>}
      />
      {mesas.isPending ? (
        <ListLoading label="Cargando mesas" />
      ) : mesas.isError ? (
        <ListError error={mesas.error} />
      ) : lista.length === 0 ? (
        <EmptyState
          title="Sin mesas"
          description="Crea las mesas de esta sucursal. Cada una tiene su QR para que los clientes pidan desde el teléfono."
          action={can(me, "mesas", "crear") && <Button onClick={() => form.abrir(null)}>Crear la primera</Button>}
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Mesa</Th>
              <Th>Capacidad</Th>
              <Th>Estado</Th>
              <Th>Pedidos por QR</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {lista.map((m) => (
              <Tr key={m.id} className={m.activa ? "" : "opacity-50"}>
                <Td>
                  <button type="button" disabled={!editar} onClick={() => (setError(null), form.abrir(m))} className="font-display text-display-s leading-none hover:underline disabled:hover:no-underline">
                    {m.nombre}
                  </button>
                </Td>
                <Td className="text-fg-2">{m.capacidad ? `${m.capacidad} personas` : "—"}</Td>
                <Td>
                  <StatusDot tone={!m.activa ? "muted" : m.ocupada ? "neutral" : "muted"}>{!m.activa ? "Inactiva" : m.ocupada ? "Ocupada" : "Libre"}</StatusDot>
                </Td>
                <Td>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={m.qr_habilitado}
                    aria-label={`Pedidos por QR en ${m.nombre}`}
                    disabled={!editar || toggleQr.isPending}
                    onClick={() => toggleQr.mutate(m)}
                    className={`relative h-6 w-10 rounded-full transition-colors ${m.qr_habilitado ? "bg-paper" : "bg-wash-strong"}`}
                  >
                    <span className={`absolute top-0.5 size-5 rounded-full transition-all ${m.qr_habilitado ? "left-[18px] bg-ink" : "left-0.5 bg-fg-2"}`} />
                  </button>
                </Td>
                <Td align="right">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="line" onClick={() => setQr(m)}>
                      Ver QR
                    </Button>
                    {m.activa && can(me, "mesas", "eliminar") && (
                      <Button size="sm" variant="danger" onClick={() => setBaja(m)}>
                        Desactivar
                      </Button>
                    )}
                  </div>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}

      {form.state && actual && (
        <FormSheet
          key={form.state.key}
          open={form.state.open}
          onOpenChange={form.onOpenChange}
          title={form.state.item ? `Editar ${form.state.item.nombre}` : "Nueva mesa"}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const m = form.state?.item ?? null;
            const capacidad = txt(f, "capacidad");
            const datos = { nombre: txt(f, "nombre"), capacidad: capacidad ? Number(capacidad) : null, qr_habilitado: bool(f, "qr_habilitado"), activa: bool(f, "activa") };
            if (!datos.nombre) return setError({ title: "Ponle un nombre a la mesa", tone: "warn" });
            guardar.mutate(m ? { id: m.id, body: cambios(m, datos) } : { body: { ...datos, sucursal_id: actual.id } });
          }}
        >
          <Field name="nombre" label="Nombre" defaultValue={form.state.item?.nombre ?? ""} maxLength={40} placeholder="1, Barra, Terraza 2…" autoFocus />
          <Field name="capacidad" label="Capacidad" type="number" min={1} max={100} defaultValue={form.state.item?.capacidad ?? ""} />
          <Toggle name="qr_habilitado" label="Pedidos por QR" hint="Si lo apagas, solo caja abre comandas en esta mesa." defaultChecked={form.state.item?.qr_habilitado ?? true} />
          <Toggle name="activa" label="Activa" defaultChecked={form.state.item?.activa ?? true} />
        </FormSheet>
      )}

      <QrSheet mesa={qr} onClose={() => setQr(null)} puedeRegenerar={editar} />
      <Confirmar
        open={baja !== null}
        onOpenChange={(o) => !o && setBaja(null)}
        title={`¿Desactivar ${baja?.nombre ?? ""}?`}
        description="Deja de aparecer en la sala y su QR deja de funcionar. Puedes reactivarla después."
        accion="Desactivar"
        pending={desactivar.isPending}
        onConfirm={() => baja && desactivar.mutate(baja)}
      />
    </>
  );
}

function QrSheet({ mesa, onClose, puedeRegenerar }: { mesa: Mesa | null; onClose: () => void; puedeRegenerar: boolean }) {
  const [ultima, setUltima] = useState(mesa);
  if (mesa && mesa !== ultima) setUltima(mesa);
  const m = mesa ?? ultima;
  const [version, setVersion] = useState(0);
  const [confirmar, setConfirmar] = useState(false);
  const url = useQuery({
    queryKey: ["mesas", "qr-url", m?.id, version],
    queryFn: () => api(`/mesas/${m!.id}/qr-url`, { schema: MesaQrOut }),
    enabled: !!mesa,
  });
  const regenerar = useApiMutation<number>({
    path: (id) => `/mesas/${id}/regenerar-qr`,
    method: "POST",
    body: () => undefined,
    invalidate: [["mesas"]],
    ok: "QR nuevo generado. El anterior ya no funciona.",
    onDone: () => {
      setVersion((v) => v + 1);
      setConfirmar(false);
    },
  });
  if (!m) return null;
  const img = (formato: "svg" | "png", escala = 12) => `/bff/panel/mesas/${m.id}/qr?formato=${formato}&escala=${escala}&v=${version}`;

  return (
    <>
      <Sheet open={mesa !== null} onOpenChange={(o) => !o && onClose()} side="right" title={`QR · ${m.nombre}`} description="Imprímelo y ponlo en la mesa. Al escanearlo, el cliente ve el menú y pide.">
        <div className="flex flex-col gap-6 pt-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- imagen generada por la API vía BFF */}
          <img src={img("svg", 10)} alt={`Código QR de ${m.nombre}`} className="aspect-square w-full rounded-control bg-paper p-4" />
          {!m.qr_habilitado && <p className="text-sm text-warn">Los pedidos por QR están apagados en esta mesa: el código no aceptará pedidos.</p>}
          {url.data && (
            <div className="flex flex-col gap-2">
              <span className="eyebrow">Enlace</span>
              <code className="break-all text-sm text-fg-2">{url.data.url}</code>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  size="sm"
                  variant="line"
                  onClick={() =>
                    void navigator.clipboard
                      .writeText(url.data.url)
                      .then(() => toast({ title: "Enlace copiado", tone: "ok", duration: 2500 }))
                      .catch(() => toast({ title: "No se pudo copiar", tone: "warn" }))
                  }
                >
                  <Copy size={14} strokeWidth={1.5} aria-hidden /> Copiar
                </Button>
                <a href={url.data.url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-control border border-line-strong px-3 text-sm font-medium hover:bg-wash">
                  <ExternalLink size={14} strokeWidth={1.5} aria-hidden /> Abrir menú
                </a>
                <a href={img("png", 20)} download={`qr-${m.nombre}.png`} className="inline-flex h-8 items-center gap-1.5 rounded-control border border-line-strong px-3 text-sm font-medium hover:bg-wash">
                  <Download size={14} strokeWidth={1.5} aria-hidden /> PNG
                </a>
                <a href={img("svg", 10)} download={`qr-${m.nombre}.svg`} className="inline-flex h-8 items-center gap-1.5 rounded-control border border-line-strong px-3 text-sm font-medium hover:bg-wash">
                  <Download size={14} strokeWidth={1.5} aria-hidden /> SVG
                </a>
              </div>
            </div>
          )}
          {puedeRegenerar && (
            <div className="flex flex-col gap-2 border-t border-line pt-6">
              <p className="text-sm text-fg-3">¿Alguien fotografió el QR y hace pedidos falsos? Genera uno nuevo: el anterior deja de funcionar.</p>
              <Button variant="danger" className="self-start px-0" onClick={() => setConfirmar(true)}>
                Regenerar QR
              </Button>
            </div>
          )}
        </div>
      </Sheet>
      <Confirmar
        open={confirmar}
        onOpenChange={setConfirmar}
        title={`¿Regenerar el QR de ${m.nombre}?`}
        description="El código impreso actual dejará de funcionar. Tendrás que imprimir el nuevo."
        accion="Regenerar"
        pending={regenerar.isPending}
        onConfirm={() => regenerar.mutate(m.id)}
      />
    </>
  );
}
