"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { StatusDot } from "@/components/ui/Status";
import { toast } from "@/components/ui/Toast";
import { useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { OpcionConfigOut, type OpcionConfig } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

const ZONAS = ["America/Caracas", "America/Bogota", "America/Panama", "America/Lima", "America/Santo_Domingo", "America/Mexico_City", "America/New_York", "Europe/Madrid", "UTC"];
const ORDEN_GRUPOS = ["Impuestos", "Pedidos por QR", "Integraciones", "Seguridad", "Archivos", "Regional"];
const KEY = ["configuracion"];

/** Valores que antes solo se cambiaban en el .env. Lo del panel manda; "Restablecer" vuelve al .env. */
export default function ConfiguracionPage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const lista = useQuery({ queryKey: KEY, queryFn: () => api("/configuracion", { schema: z.array(OpcionConfigOut) }), enabled: !!me?.es_superadmin });
  // Solo lo que el usuario tocó: clave -> nuevo valor (null = volver al .env)
  const [cambios, setCambios] = useState<Record<string, string | null>>({});
  const [error, setError] = useState<ErrorView | null>(null);
  const guardar = useMutation({
    mutationFn: (valores: Record<string, string | null>) => api("/configuracion", { method: "PUT", body: { valores }, schema: z.array(OpcionConfigOut) }),
    onSuccess: (d) => {
      qc.setQueryData(KEY, d);
      setCambios({});
      setError(null);
      toast({ title: "Configuración guardada", description: "Se aplica en todo el sistema en unos segundos.", tone: "ok", duration: 3500 });
    },
    onError: (e) => setError(describeError(e)),
  });

  if (!me?.es_superadmin) return <SinAcceso />;
  const grupos = new Map<string, OpcionConfig[]>();
  for (const o of lista.data ?? []) grupos.set(o.grupo, [...(grupos.get(o.grupo) ?? []), o]);
  const pendientes = Object.keys(cambios).length;

  return (
    <>
      <PageHeader
        eyebrow="Solo superadmin"
        title="Configuración"
        actions={
          pendientes > 0 && (
            <>
              <Button variant="ghost" onClick={() => setCambios({})}>
                Descartar
              </Button>
              <Button loading={guardar.isPending} onClick={() => guardar.mutate(cambios)}>
                Guardar {pendientes} {pendientes === 1 ? "cambio" : "cambios"}
              </Button>
            </>
          )
        }
      />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">
        Lo que antes solo se cambiaba en el archivo .env. Lo que guardes aquí manda sobre el .env; “Restablecer” vuelve a su valor. La base de datos, Redis y las claves de cifrado no
        se cambian desde aquí por seguridad.
      </p>
      {error && (
        <div className="mb-8 max-w-2xl">
          <ErrorBox error={error} onClose={() => setError(null)} />
        </div>
      )}
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : (
        <div className="flex max-w-3xl flex-col gap-14">
          {[...grupos.entries()]
            .sort(([a], [b]) => ORDEN_GRUPOS.indexOf(a) - ORDEN_GRUPOS.indexOf(b))
            .map(([grupo, opciones]) => (
              <section key={grupo} className="flex flex-col">
                <h2 className="pb-3 font-display text-display-s">{grupo}</h2>
                {opciones.map((o) => (
                  <Campo
                    key={o.clave}
                    o={o}
                    valor={o.clave in cambios ? cambios[o.clave]! : undefined}
                    onCambio={(v) => setCambios((c) => ({ ...c, [o.clave]: v }))}
                    onDeshacer={() =>
                      setCambios((c) => {
                        const n = { ...c };
                        delete n[o.clave];
                        return n;
                      })
                    }
                  />
                ))}
              </section>
            ))}
        </div>
      )}
    </>
  );
}

function Campo({ o, valor, onCambio, onDeshacer }: { o: OpcionConfig; valor: string | null | undefined; onCambio: (v: string | null) => void; onDeshacer: () => void }) {
  const tocado = valor !== undefined;
  const secreto = o.tipo === "secreto";
  const mostrado = tocado ? (valor ?? "") : secreto ? "" : (o.valor ?? "");
  const id = `cfg-${o.clave}`;
  const clase = "h-11 w-full border-b border-line-strong bg-transparent text-base outline-none placeholder:text-fg-4 focus:border-paper";

  return (
    <div className={cn("grid gap-3 border-t border-line py-5 tablet:grid-cols-[1fr_18rem] tablet:gap-8", tocado && "bg-wash/40")}>
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className="font-medium">
          {o.etiqueta}
        </label>
        <p className="text-sm text-fg-3">{o.descripcion}</p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-sm">
          {secreto ? (
            <StatusDot tone={o.configurado ? "ok" : "muted"}>{o.configurado ? "Configurado" : "Sin configurar"}</StatusDot>
          ) : (
            <StatusDot tone={o.origen === "panel" ? "ok" : "muted"}>{o.origen === "panel" ? "Cambiado en el panel" : "Del archivo .env"}</StatusDot>
          )}
          {o.origen === "panel" && !secreto && o.por_defecto !== null && <span className="text-fg-4">.env: {o.por_defecto}</span>}
          {tocado && <span className="text-warn">Sin guardar</span>}
        </p>
      </div>
      <div className="flex flex-col gap-2 tablet:pt-1">
        {o.tipo === "zona_horaria" ? (
          <select id={id} value={mostrado} onChange={(e) => onCambio(e.target.value)} className={cn(clase, "[color-scheme:dark]")}>
            {[...new Set([mostrado, ...ZONAS])].filter(Boolean).map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            type={secreto ? "password" : o.tipo === "url" ? "url" : "text"}
            inputMode={o.tipo === "entero" ? "numeric" : o.tipo === "decimal" ? "decimal" : undefined}
            autoComplete={secreto ? "new-password" : "off"}
            value={mostrado}
            onChange={(e) => onCambio(e.target.value)}
            placeholder={secreto ? (o.configurado ? "•••••••• (escribe para reemplazar)" : "Pega aquí el token") : (o.por_defecto ?? "")}
            className={clase}
          />
        )}
        {(o.minimo !== null || o.maximo !== null) && (
          <span className="text-xs text-fg-4">
            Entre {o.minimo ?? "—"} y {o.maximo ?? "—"}
          </span>
        )}
        <div className="flex gap-3 text-sm">
          {tocado && (
            <button type="button" onClick={onDeshacer} className="text-fg-3 underline-offset-4 hover:text-fg hover:underline">
              Deshacer
            </button>
          )}
          {!tocado && (o.origen === "panel" || (secreto && o.configurado)) && (
            <button type="button" onClick={() => onCambio(null)} className="text-fg-3 underline-offset-4 hover:text-fg hover:underline">
              {secreto ? "Quitar" : "Restablecer al .env"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
