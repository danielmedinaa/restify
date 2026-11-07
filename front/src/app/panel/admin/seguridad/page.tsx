"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Segmented";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { toast } from "@/components/ui/Toast";
import { useMe } from "@/features/auth/useMe";
import { Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { AlertaSeguridadOut, ApiKeyCreadaOut, ApiKeyOut, AuditoriaOut, Pagina } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

const fecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function SeguridadPage() {
  const { data: me } = useMe();
  const [vista, setVista] = useState<"alertas" | "keys" | "auditoria">("alertas");
  if (!me?.es_superadmin) return <SinAcceso />;
  return (
    <>
      <PageHeader
        eyebrow="Solo superadmin"
        title="Seguridad"
        actions={
          <Segmented
            label="Sección"
            value={vista}
            onChange={setVista}
            options={[
              { value: "alertas", label: "Alertas" },
              { value: "keys", label: "API keys" },
              { value: "auditoria", label: "Auditoría" },
            ]}
          />
        }
      />
      {vista === "alertas" ? <Alertas /> : vista === "keys" ? <ApiKeys /> : <Auditoria />}
    </>
  );
}

const SEVERIDAD = {
  critica: { label: "Crítica", clase: "bg-[#a3212b] text-white" },
  alta: { label: "Alta", clase: "bg-err/25 text-fg" },
  media: { label: "Media", clase: "bg-warn/20 text-fg" },
} as const;

/** Comportamiento sospechoso detectado por el backend (fuerza bruta, robo de sesión, keys falsas…). */
function Alertas() {
  const qc = useQueryClient();
  const lista = useQuery({ queryKey: ["seguridad", "alertas", "todas"], queryFn: () => api("/seguridad/alertas", { query: { limite: 100 }, schema: Pagina(AlertaSeguridadOut) }) });
  const revisar = useMutation({
    mutationFn: (ids?: number[]) => api("/seguridad/alertas/revisar", { method: "POST", body: ids ?? null }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["seguridad"] }),
  });
  const pendientes = lista.data?.items.filter((a) => !a.revisada) ?? [];
  return (
    <>
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <p className="max-w-2xl text-base text-fg-2">
          Intentos de acceso fallidos, cuentas bloqueadas, sesiones reutilizadas (posible robo), API keys falsas y accesos sin permiso repetidos. Las nuevas aparecen en rojo sobre todo el panel.
        </p>
        {pendientes.length > 0 && (
          <Button variant="line" loading={revisar.isPending} onClick={() => revisar.mutate(undefined)}>
            Marcar todas como revisadas
          </Button>
        )}
      </div>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.items.length === 0 ? (
        <EmptyState title="Sin alertas" description="No se ha detectado nada sospechoso." />
      ) : (
        <ul className="flex flex-col">
          {lista.data.items.map((a) => (
            <li key={a.id} className={cn("flex flex-wrap items-start gap-4 border-t border-line py-4", a.revisada && "opacity-55")}>
              <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.06em]", SEVERIDAD[a.severidad].clase)}>{SEVERIDAD[a.severidad].label}</span>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <p className="font-medium">{a.titulo}</p>
                <p className="text-sm text-fg-2">{a.detalle}</p>
                <p className="text-sm text-fg-3">
                  {fechaAlerta.format(new Date(a.created_at))}
                  {a.ip && ` · IP ${a.ip}`}
                  {a.revisada && " · revisada"}
                </p>
              </div>
              {!a.revisada && (
                <Button size="sm" variant="ghost" onClick={() => revisar.mutate([a.id])}>
                  Revisada
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

const fechaAlerta = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function ApiKeys() {
  const lista = useQuery({ queryKey: ["api-keys"], queryFn: () => api("/api-keys", { schema: z.array(ApiKeyOut) }) });
  const form = useFormSheet<null>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [creada, setCreada] = useState<{ nombre: string; clave: string } | null>(null);
  const [revocar, setRevocar] = useState<{ id: number; nombre: string } | null>(null);
  const [creando, setCreando] = useState(false);
  const revocarM = useApiMutation<number>({ path: (id) => `/api-keys/${id}`, method: "DELETE", body: () => undefined, invalidate: [["api-keys"]], ok: "API key revocada", onDone: () => setRevocar(null) });

  return (
    <>
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <p className="max-w-2xl text-base text-fg-2">Una key por app cliente (panel, cocina, menú público). Se guardan cifradas y la clave completa solo se ve al crearla.</p>
        <Button onClick={() => (setError(null), form.abrir(null))}>Nueva API key</Button>
      </div>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Nombre</Th>
              <Th>Prefijo</Th>
              <Th>Último uso</Th>
              <Th>Estado</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.map((k) => (
              <Tr key={k.id} className={k.activa ? "" : "opacity-50"}>
                <Td className="font-medium">{k.nombre}</Td>
                <Td>
                  <code className="text-sm text-fg-2">{k.prefijo}…</code>
                </Td>
                <Td className="text-sm text-fg-3">{k.ultimo_uso ? fecha.format(new Date(k.ultimo_uso)) : "Nunca"}</Td>
                <Td>
                  <StatusDot tone={k.activa ? "ok" : "muted"}>{k.activa ? "Activa" : "Revocada"}</StatusDot>
                </Td>
                <Td align="right">
                  {k.activa && (
                    <Button size="sm" variant="danger" onClick={() => setRevocar(k)}>
                      Revocar
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
          title="Nueva API key"
          pending={creando}
          error={error}
          onClearError={() => setError(null)}
          submitLabel="Crear"
          onSubmit={async (f) => {
            const nombre = txt(f, "nombre");
            if (!nombre) return setError({ title: "Ponle un nombre (para saber qué app la usa)", tone: "warn" });
            setCreando(true);
            try {
              const k = await api("/api-keys", { method: "POST", body: { nombre }, schema: ApiKeyCreadaOut });
              form.cerrar();
              setCreada({ nombre: k.nombre, clave: k.clave });
              void lista.refetch();
            } catch (err) {
              setError(describeError(err));
            } finally {
              setCreando(false);
            }
          }}
        >
          <Field name="nombre" label="Nombre" maxLength={120} placeholder="Panel web, Tablet cocina, Menú QR…" autoFocus />
        </FormSheet>
      )}
      <Dialog
        open={creada !== null}
        onOpenChange={(o) => !o && setCreada(null)}
        title={`Key de ${creada?.nombre ?? ""}`}
        description="Cópiala ahora y guárdala en la variable de entorno del servidor. No se volverá a mostrar."
        actions={
          <Button
            onClick={() =>
              creada &&
              void navigator.clipboard
                .writeText(creada.clave)
                .then(() => toast({ title: "Key copiada", tone: "ok", duration: 2500 }))
                .catch(() => toast({ title: "Cópiala a mano", tone: "warn" }))
            }
          >
            <Copy size={16} strokeWidth={1.5} aria-hidden /> Copiar
          </Button>
        }
      >
        <code className="block break-all rounded-control bg-sunken p-4 text-sm">{creada?.clave}</code>
      </Dialog>
      <Confirmar
        open={revocar !== null}
        onOpenChange={(o) => !o && setRevocar(null)}
        title={`¿Revocar ${revocar?.nombre ?? ""}?`}
        description="La app que la use dejará de funcionar al instante."
        accion="Revocar"
        pending={revocarM.isPending}
        onConfirm={() => revocar && revocarM.mutate(revocar.id)}
      />
    </>
  );
}

function Auditoria() {
  const [offset, setOffset] = useState(0);
  const lista = useQuery({
    queryKey: ["auditoria", offset],
    queryFn: () => api("/auditoria", { query: { limite: 50, offset }, schema: Pagina(AuditoriaOut) }),
    placeholderData: keepPreviousData,
  });
  if (lista.isPending) return <ListLoading />;
  if (lista.isError) return <ListError error={lista.error} />;
  return (
    <div className="flex flex-col gap-6">
      <Table>
        <thead>
          <tr>
            <Th>Cuándo</Th>
            <Th>Acción</Th>
            <Th>Resultado</Th>
            <Th>Usuario</Th>
            <Th>IP</Th>
          </tr>
        </thead>
        <tbody>
          {lista.data.items.map((a) => (
            <Tr key={a.id}>
              <Td className="whitespace-nowrap text-sm text-fg-3">{fecha.format(new Date(a.created_at))}</Td>
              <Td>
                <code className="text-sm">
                  <span className="text-fg-3">{a.metodo}</span> {a.ruta.replace("/api/v1", "")}
                </code>
              </Td>
              <Td>
                <StatusDot tone={a.status_code < 400 ? "ok" : a.status_code < 500 ? "warn" : "err"}>{a.status_code}</StatusDot>
              </Td>
              <Td className="text-fg-2">{a.usuario_id ?? "—"}</Td>
              <Td className="text-sm text-fg-3">{a.ip ?? "—"}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      <div className="flex items-center justify-between text-sm text-fg-3">
        <span>
          {offset + 1}–{Math.min(offset + 50, lista.data.total)} de {lista.data.total}
        </span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - 50))}>
            Más recientes
          </Button>
          <Button size="sm" variant="ghost" disabled={offset + 50 >= lista.data.total} onClick={() => setOffset((o) => o + 50)}>
            Anteriores
          </Button>
        </div>
      </div>
    </div>
  );
}
