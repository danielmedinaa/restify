"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { StatusDot } from "@/components/ui/Status";
import { TextArea } from "@/components/ui/TextArea";
import { toast } from "@/components/ui/Toast";
import { useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { InspeccionPlugin, PluginInstaladoOut, PluginOut, type InspeccionPluginT, type PluginT } from "@/lib/api/schemas";

const KEY = ["plugins"];

export default function PluginsPage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const lista = useQuery({ queryKey: KEY, queryFn: () => api("/plugins", { schema: z.array(PluginOut) }), enabled: !!me?.es_superadmin });
  const [texto, setTexto] = useState("");
  const [paquete, setPaquete] = useState<unknown>(null);
  const [revision, setRevision] = useState<InspeccionPluginT | null>(null);
  const [aprobados, setAprobados] = useState<string[]>([]);
  const [token, setToken] = useState<{ nombre: string; valor: string } | null>(null);
  const [error, setError] = useState<ErrorView | null>(null);
  const refrescar = () => void qc.invalidateQueries({ queryKey: KEY });
  const fallo = (e: unknown) => setError(e instanceof Error && !("status" in e) ? { title: e.message, tone: "warn" } : describeError(e));

  const inspeccionar = useMutation({
    mutationFn: async () => {
      let p: unknown;
      try {
        p = JSON.parse(texto);
      } catch {
        throw new Error("Eso no es un paquete válido: pega el contenido del archivo .json firmado.");
      }
      const r = await api("/plugins/inspeccionar", { method: "POST", body: p, schema: InspeccionPlugin });
      return { p, r };
    },
    onSuccess: ({ p, r }) => {
      setError(null);
      setPaquete(p);
      setRevision(r);
      setAprobados(r.permisos.filter((x) => !x.sensible).map((x) => x.permiso)); // lo sensible nunca viene marcado de antemano
    },
    onError: fallo,
  });
  const instalar = useMutation({
    mutationFn: () => api("/plugins", { method: "POST", body: { ...(paquete as object), permisos_aprobados: aprobados }, schema: PluginInstaladoOut }),
    onSuccess: (p) => {
      setToken({ nombre: p.nombre, valor: p.token });
      setRevision(null);
      setPaquete(null);
      setTexto("");
      setError(null);
      refrescar();
    },
    onError: fallo,
  });
  const accion = useMutation({
    mutationFn: ({ ruta, metodo, body }: { ruta: string; metodo: "PUT" | "POST" | "DELETE"; body?: unknown; aviso?: string }) => api(`/plugins/${ruta}`, { method: metodo, body }),
    onSuccess: (r, v) => {
      refrescar();
      if (v.aviso) toast({ title: v.aviso, tone: "ok", duration: 3000 });
      const t = PluginInstaladoOut.safeParse(r);
      if (t.success) setToken({ nombre: t.data.nombre, valor: t.data.token });
    },
    onError: fallo,
  });

  if (!me?.es_superadmin) return <SinAcceso />;

  return (
    <>
      <PageHeader eyebrow="Solo superadmin" title="Plugins" />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">
        Los plugins amplían RESTIFY (pagos, integraciones). Solo se instalan los que RESTIFY firmó, y cada uno recibe únicamente los permisos que tú apruebes. Puedes quitarlos o desinstalar en cualquier momento.
      </p>
      {error && (
        <div className="mb-8 max-w-2xl">
          <ErrorBox error={error} onClose={() => setError(null)} />
        </div>
      )}
      {token && (
        <div className="mb-10 max-w-2xl border border-warn/60 p-4">
          <p className="font-medium">Token de “{token.nombre}”</p>
          <p className="py-2 text-sm text-fg-2">Cópialo ahora y entrégaselo al servicio del plugin. No se vuelve a mostrar.</p>
          <code className="block break-all rounded-control bg-sunken p-3 text-sm">{token.valor}</code>
          <Button variant="line" size="sm" className="mt-3" onClick={() => setToken(null)}>
            Ya lo copié
          </Button>
        </div>
      )}

      <section className="mb-14 flex max-w-3xl flex-col gap-4">
        <h2 className="font-display text-display-s">Instalar un plugin</h2>
        {revision ? (
          <div className="flex flex-col gap-5 border border-line p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-title font-medium">
                {revision.manifiesto.nombre} <span className="text-fg-3">v{revision.manifiesto.version}</span>
              </span>
              {revision.firmado ? (
                <span className="flex items-center gap-1.5 text-sm text-ok">
                  <ShieldCheck className="size-4" aria-hidden /> Firmado por RESTIFY
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-sm text-warn">
                  <ShieldAlert className="size-4" aria-hidden /> Sin firma (solo desarrollo)
                </span>
              )}
            </div>
            <p className="text-sm text-fg-2">
              {revision.manifiesto.autor} · {revision.manifiesto.descripcion || "Sin descripción"}
            </p>
            <p className="text-sm text-fg-3">Huella: {revision.huella.slice(0, 16)}…</p>
            {revision.ya_instalado && <p className="text-sm text-err">Ya hay un plugin con este nombre instalado. Desinstálalo primero.</p>}
            <div>
              <p className="eyebrow pb-2">Permisos que pide</p>
              {revision.permisos.length === 0 && <p className="text-sm text-fg-3">No pide ningún permiso.</p>}
              {revision.permisos.map((p) => (
                <label key={p.permiso} className="flex items-start gap-3 border-t border-line py-2.5">
                  <input
                    type="checkbox"
                    className="mt-1 size-4 accent-[var(--color-paper)]"
                    checked={aprobados.includes(p.permiso)}
                    onChange={(e) => setAprobados((a) => (e.target.checked ? [...a, p.permiso] : a.filter((x) => x !== p.permiso)))}
                  />
                  <span className="flex flex-col">
                    <span className="text-base">{p.descripcion}</span>
                    <span className="text-sm text-fg-3">
                      {p.permiso}
                      {p.sensible && <span className="pl-2 text-warn">Sensible: da acceso a datos delicados</span>}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <div className="flex gap-3">
              <Button loading={instalar.isPending} disabled={revision.ya_instalado} onClick={() => instalar.mutate()}>
                Aprobar e instalar
              </Button>
              <Button variant="ghost" onClick={() => setRevision(null)}>
                Cancelar
              </Button>
            </div>
          </div>
        ) : (
          <>
            <TextArea label="Paquete firmado (contenido del archivo .json)" rows={6} value={texto} onChange={(e) => setTexto(e.target.value)} className="font-mono" placeholder='{"manifiesto": {...}, "firma": "..."}' />
            <div>
              <Button loading={inspeccionar.isPending} disabled={!texto.trim()} onClick={() => inspeccionar.mutate()}>
                Revisar plugin
              </Button>
            </div>
          </>
        )}
      </section>

      <section className="max-w-3xl">
        <h2 className="pb-3 font-display text-display-s">Instalados</h2>
        {lista.isPending ? (
          <ListLoading />
        ) : lista.isError ? (
          <ListError error={lista.error} />
        ) : lista.data.length === 0 ? (
          <p className="text-base text-fg-2">Aún no hay plugins instalados.</p>
        ) : (
          lista.data.map((p) => <PluginFila key={p.id} p={p} onAccion={(a) => accion.mutate(a)} />)
        )}
      </section>
    </>
  );
}

function PluginFila({ p, onAccion }: { p: PluginT; onAccion: (a: { ruta: string; metodo: "PUT" | "POST" | "DELETE"; body?: unknown; aviso?: string }) => void }) {
  const [permisos, setPermisos] = useState(p.permisos_aprobados);
  const cambiado = JSON.stringify([...permisos].sort()) !== JSON.stringify([...p.permisos_aprobados].sort());
  return (
    <div className="flex flex-col gap-3 border-t border-line py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-title font-medium">
            {p.nombre} <span className="text-fg-3">v{p.version}</span>
          </span>
          <span className="flex flex-wrap gap-4 text-sm text-fg-3">
            <StatusDot tone={p.activo ? "ok" : "muted"}>{p.activo ? "Activo" : "Pausado"}</StatusDot>
            <span>{p.firmado ? "Firmado por RESTIFY" : "Sin firma"}</span>
            <span>Token {p.token_prefijo}…</span>
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="line" size="sm" onClick={() => onAccion({ ruta: `${p.id}/activo?activo=${!p.activo}`, metodo: "PUT", aviso: p.activo ? "Plugin pausado" : "Plugin activado" })}>
            {p.activo ? "Pausar" : "Activar"}
          </Button>
          <Button
            variant="line"
            size="sm"
            onClick={() => {
              if (window.confirm("¿Cambiar el token? El actual dejará de funcionar y tendrás que dárselo al plugin.")) onAccion({ ruta: `${p.id}/token`, metodo: "POST" });
            }}
          >
            Nuevo token
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              if (window.confirm(`¿Desinstalar “${p.nombre}”?`)) onAccion({ ruta: String(p.id), metodo: "DELETE", aviso: "Plugin desinstalado" });
            }}
          >
            Desinstalar
          </Button>
        </div>
      </div>
      {p.permisos_pedidos.length > 0 && (
        <div>
          {p.permisos_pedidos.map((x) => (
            <label key={x.permiso} className="flex items-center gap-3 py-1 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-[var(--color-paper)]"
                checked={permisos.includes(x.permiso)}
                onChange={(e) => setPermisos((a) => (e.target.checked ? [...a, x.permiso] : a.filter((y) => y !== x.permiso)))}
              />
              <span>{x.descripcion}</span>
              <span className="text-fg-3">{x.permiso}</span>
              {x.sensible && <span className="text-warn">Sensible</span>}
            </label>
          ))}
          {cambiado && (
            <Button size="sm" className="mt-2" onClick={() => onAccion({ ruta: `${p.id}/permisos`, metodo: "PUT", body: { permisos_aprobados: permisos }, aviso: "Permisos actualizados" })}>
              Guardar permisos
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
