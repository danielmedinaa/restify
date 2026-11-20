"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { StatusDot } from "@/components/ui/Status";
import { TextArea } from "@/components/ui/TextArea";
import { toast } from "@/components/ui/Toast";
import { useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { PosOut, SucursalOut, type Pos } from "@/lib/api/schemas";

const KEY = ["pos"];

interface Secreto {
  nombre: string;
  valor: string;
}
interface Form {
  id: number | null;
  nombre: string;
  sucursal_id: string;
  tipo: "manual" | "api";
  activo: boolean;
  base_url: string;
  cabeceras: string;
  crear_metodo: "POST" | "PUT" | "PATCH" | "GET";
  crear_ruta: string;
  crear_cuerpo: string;
  id_path: string;
  url_path: string;
  consultar_ruta: string;
  estado_path: string;
  pagado: string;
  secretos: Secreto[];
  conservados: string[];
}

/** Punto de partida para un proveedor cualquiera: se edita con lo que diga su documentación. */
const EJEMPLO = {
  base_url: "https://api.tu-proveedor.com/v1",
  cabeceras: { Authorization: "Bearer {{secreto.api_key}}", "Content-Type": "application/json" },
  crear_ruta: "/cobros",
  crear_cuerpo: { monto: "{{monto}}", moneda: "{{moneda}}", referencia: "{{referencia}}", descripcion: "{{descripcion}}" },
  id_path: "data.id",
  url_path: "data.payment_url",
  consultar_ruta: "/cobros/{{id}}",
  estado_path: "data.status",
  pagado: "PAID",
};

const vacio = (): Form => ({
  id: null, nombre: "", sucursal_id: "", tipo: "manual", activo: true,
  base_url: "", cabeceras: "{}", crear_metodo: "POST", crear_ruta: "", crear_cuerpo: "{}", id_path: "", url_path: "",
  consultar_ruta: "", estado_path: "", pagado: "", secretos: [], conservados: [],
});

function desde(p: Pos): Form {
  const c = (p.config ?? {}) as Record<string, any>;
  return {
    id: p.id, nombre: p.nombre, sucursal_id: p.sucursal_id ? String(p.sucursal_id) : "", tipo: p.tipo, activo: p.activo,
    base_url: c.base_url ?? "", cabeceras: JSON.stringify(c.cabeceras ?? {}, null, 2),
    crear_metodo: c.crear?.metodo ?? "POST", crear_ruta: c.crear?.ruta ?? "", crear_cuerpo: JSON.stringify(c.crear?.cuerpo ?? {}, null, 2),
    id_path: c.crear?.id_path ?? "", url_path: c.crear?.url_path ?? "",
    consultar_ruta: c.consultar?.ruta ?? "", estado_path: c.consultar?.estado_path ?? "", pagado: (c.consultar?.pagado ?? []).join(", "),
    secretos: [], conservados: p.secretos_configurados,
  };
}

function aBody(f: Form) {
  const json = (t: string, que: string) => {
    try {
      return JSON.parse(t || "{}");
    } catch {
      throw new Error(`${que} no es un JSON válido`);
    }
  };
  const secretos: Record<string, string | null> = {};
  for (const s of f.secretos) if (s.nombre.trim() && s.valor) secretos[s.nombre.trim()] = s.valor;
  const body: Record<string, unknown> = { nombre: f.nombre, sucursal_id: f.sucursal_id ? Number(f.sucursal_id) : null, tipo: f.tipo, activo: f.activo, secretos };
  if (f.tipo === "api") {
    body.config = {
      base_url: f.base_url.trim(),
      cabeceras: json(f.cabeceras, "Las cabeceras"),
      crear: { metodo: f.crear_metodo, ruta: f.crear_ruta.trim(), cuerpo: json(f.crear_cuerpo, "El cuerpo del cobro"), id_path: f.id_path.trim() || undefined, url_path: f.url_path.trim() || undefined },
      ...(f.consultar_ruta.trim()
        ? { consultar: { metodo: "GET", ruta: f.consultar_ruta.trim(), estado_path: f.estado_path.trim() || undefined, pagado: f.pagado.split(",").map((x) => x.trim()).filter(Boolean) } }
        : {}),
    };
  }
  return body;
}

export default function PosPage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const lista = useQuery({ queryKey: KEY, queryFn: () => api("/pos", { schema: z.array(PosOut) }), enabled: !!me?.es_superadmin });
  const sucursales = useQuery({ queryKey: ["sucursales"], queryFn: () => api("/sucursales", { schema: z.array(SucursalOut) }), enabled: !!me?.es_superadmin });
  const [f, setF] = useState<Form | null>(null);
  const [error, setError] = useState<ErrorView | null>(null);
  const [prueba, setPrueba] = useState<string | null>(null);

  const guardar = useMutation({
    mutationFn: (form: Form) => api(form.id ? `/pos/${form.id}` : "/pos", { method: form.id ? "PUT" : "POST", body: aBody(form), schema: PosOut }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
      setF(null);
      setError(null);
      toast({ title: "Punto de cobro guardado", tone: "ok", duration: 3000 });
    },
    onError: (e) => setError(e instanceof Error && !("status" in e) ? { title: e.message, tone: "warn" } : describeError(e)),
  });
  const borrar = useMutation({
    mutationFn: (id: number) => api(`/pos/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
    onError: (e) => setError(describeError(e)),
  });
  const probar = useMutation({
    mutationFn: (id: number) => api(`/pos/${id}/cobro-prueba`, { method: "POST", body: {} }),
    onSuccess: (r) => {
      setError(null);
      setPrueba(JSON.stringify(r, null, 2));
    },
    onError: (e) => {
      setPrueba(null);
      setError(describeError(e));
    },
  });

  if (!me?.es_superadmin) return <SinAcceso />;
  const set = (p: Partial<Form>) => setF((x) => (x ? { ...x, ...p } : x));

  return (
    <>
      <PageHeader eyebrow="Solo superadmin" title="Puntos de cobro" actions={!f && <Button onClick={() => { setF(vacio()); setPrueba(null); }}>Nuevo punto de cobro</Button>} />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">
        Conecta los datáfonos o pasarelas de pago de tu restaurante. <strong>Manual</strong>: el cajero cobra y registra el pago. <strong>Por API</strong>: describes cómo habla tu proveedor
        (cualquiera con HTTP y JSON) y RESTIFY crea los cobros por ti. Las llaves se guardan cifradas y no se vuelven a mostrar.
      </p>
      {error && (
        <div className="mb-8 max-w-2xl">
          <ErrorBox error={error} onClose={() => setError(null)} />
        </div>
      )}

      {f ? (
        <form
          className="flex max-w-3xl flex-col gap-8"
          onSubmit={(e) => {
            e.preventDefault();
            guardar.mutate(f);
          }}
        >
          <div className="grid gap-6 tablet:grid-cols-2">
            <Field label="Nombre" value={f.nombre} onChange={(e) => set({ nombre: e.target.value })} maxLength={80} required placeholder="Cobrix · Caja principal" />
            <Select label="Sucursal" value={f.sucursal_id} onChange={(e) => set({ sucursal_id: e.target.value })}>
              <option value="">Todas las sucursales</option>
              {(sucursales.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                </option>
              ))}
            </Select>
          </div>
          <Segmented label="Tipo" value={f.tipo} onChange={(tipo) => set({ tipo })} options={[{ value: "manual", label: "Manual" }, { value: "api", label: "Por API" }]} />

          {f.tipo === "api" && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="line"
                  size="sm"
                  onClick={() =>
                    set({
                      base_url: EJEMPLO.base_url, cabeceras: JSON.stringify(EJEMPLO.cabeceras, null, 2), crear_ruta: EJEMPLO.crear_ruta, crear_cuerpo: JSON.stringify(EJEMPLO.crear_cuerpo, null, 2),
                      id_path: EJEMPLO.id_path, url_path: EJEMPLO.url_path, consultar_ruta: EJEMPLO.consultar_ruta, estado_path: EJEMPLO.estado_path, pagado: EJEMPLO.pagado,
                      secretos: f.secretos.length ? f.secretos : [{ nombre: "api_key", valor: "" }],
                    })
                  }
                >
                  Rellenar con un ejemplo
                </Button>
                <span className="text-sm text-fg-3">Variables: {"{{monto}} {{moneda}} {{referencia}} {{nombre}} {{descripcion}} {{id}} {{secreto.nombre}}"}</span>
              </div>
              <Field label="Dirección base del proveedor (https)" value={f.base_url} onChange={(e) => set({ base_url: e.target.value })} placeholder="https://api.proveedor.com/v1" />
              <TextArea label="Cabeceras (JSON)" rows={4} value={f.cabeceras} onChange={(e) => set({ cabeceras: e.target.value })} className="font-mono" />
              <h2 className="font-display text-display-s">Crear un cobro</h2>
              <div className="grid gap-6 tablet:grid-cols-[8rem_1fr]">
                <Select label="Método" value={f.crear_metodo} onChange={(e) => set({ crear_metodo: e.target.value as Form["crear_metodo"] })}>
                  {["POST", "PUT", "PATCH"].map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </Select>
                <Field label="Ruta" value={f.crear_ruta} onChange={(e) => set({ crear_ruta: e.target.value })} placeholder="/cobros" />
              </div>
              <TextArea label="Cuerpo (JSON)" rows={6} value={f.crear_cuerpo} onChange={(e) => set({ crear_cuerpo: e.target.value })} className="font-mono" />
              <div className="grid gap-6 tablet:grid-cols-2">
                <Field label="¿Dónde viene el id del cobro?" value={f.id_path} onChange={(e) => set({ id_path: e.target.value })} placeholder="data.id" hint="Ruta en la respuesta, con puntos." />
                <Field label="¿Dónde viene el enlace de pago?" value={f.url_path} onChange={(e) => set({ url_path: e.target.value })} placeholder="data.payment_url" />
              </div>
              <h2 className="font-display text-display-s">Consultar si ya pagó (opcional)</h2>
              <Field label="Ruta" value={f.consultar_ruta} onChange={(e) => set({ consultar_ruta: e.target.value })} placeholder="/cobros/{{id}}" />
              <div className="grid gap-6 tablet:grid-cols-2">
                <Field label="¿Dónde viene el estado?" value={f.estado_path} onChange={(e) => set({ estado_path: e.target.value })} placeholder="data.status" />
                <Field label="Valores que significan “pagado”" value={f.pagado} onChange={(e) => set({ pagado: e.target.value })} placeholder="PAID, CONCILIATED" hint="Separados por coma." />
              </div>
              <h2 className="font-display text-display-s">Llaves y claves</h2>
              {f.conservados.length > 0 && <p className="text-sm text-fg-3">Ya guardadas: {f.conservados.join(", ")}. Déjalas vacías para conservarlas.</p>}
              {f.secretos.map((s, i) => (
                <div key={i} className="grid items-end gap-4 tablet:grid-cols-[12rem_1fr_auto]">
                  <Field label="Nombre" value={s.nombre} onChange={(e) => set({ secretos: f.secretos.map((x, j) => (j === i ? { ...x, nombre: e.target.value } : x)) })} placeholder="api_key" />
                  <Field label="Valor" type="password" autoComplete="off" value={s.valor} onChange={(e) => set({ secretos: f.secretos.map((x, j) => (j === i ? { ...x, valor: e.target.value } : x)) })} />
                  <Button variant="ghost" onClick={() => set({ secretos: f.secretos.filter((_, j) => j !== i) })}>
                    Quitar
                  </Button>
                </div>
              ))}
              <div>
                <Button variant="line" size="sm" onClick={() => set({ secretos: [...f.secretos, { nombre: "", valor: "" }] })}>
                  Agregar llave
                </Button>
              </div>
            </>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" loading={guardar.isPending}>
              Guardar
            </Button>
            {f.id && f.tipo === "api" && (
              <Button variant="line" loading={probar.isPending} onClick={() => probar.mutate(f.id!)}>
                Probar con un cobro de 14 Bs
              </Button>
            )}
            <Button variant="ghost" onClick={() => { setF(null); setPrueba(null); setError(null); }}>
              Cancelar
            </Button>
          </div>
          {prueba && (
            <pre className="max-h-80 overflow-auto border border-line p-4 text-sm text-fg-2">{prueba}</pre>
          )}
        </form>
      ) : lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.length === 0 ? (
        <p className="text-base text-fg-2">Aún no hay puntos de cobro. Crea el primero con “Nuevo punto de cobro”.</p>
      ) : (
        <ul className="max-w-3xl">
          {lista.data.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-4 border-t border-line py-4">
              <div className="flex flex-col gap-1">
                <span className="text-title font-medium">{p.nombre}</span>
                <span className="flex gap-4 text-sm text-fg-3">
                  <StatusDot tone={p.activo ? "ok" : "muted"}>{p.activo ? "Activo" : "Inactivo"}</StatusDot>
                  <span>{p.tipo === "api" ? "Por API" : "Manual"}</span>
                  <span>{(sucursales.data ?? []).find((s) => s.id === p.sucursal_id)?.nombre ?? "Todas las sucursales"}</span>
                </span>
              </div>
              <div className="flex gap-2">
                <Button variant="line" size="sm" onClick={() => { setF(desde(p)); setPrueba(null); }}>
                  Editar
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => {
                    if (window.confirm(`¿Eliminar “${p.nombre}”?`)) borrar.mutate(p.id);
                  }}
                >
                  Eliminar
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
