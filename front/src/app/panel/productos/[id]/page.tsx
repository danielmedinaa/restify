"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Star, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Money } from "@/components/ui/Money";
import { Select } from "@/components/ui/Select";
import { StatusDot } from "@/components/ui/Status";
import { Switch } from "@/components/ui/Switch";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { Confirmar, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { useSucursal } from "@/features/panel/sucursal";
import { ProductoForm } from "@/features/productos/ProductoForm";
import { Medio } from "@/features/publico/Medio";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { ProductoOut, type Producto } from "@/lib/api/schemas";
import { parseAmountInput } from "@/lib/money";

export default function ProductoPage() {
  const { id } = useParams<{ id: string }>();
  const { data: me } = useMe();
  const producto = useQuery({ queryKey: ["productos", "detalle", Number(id)], queryFn: () => api(`/productos/${id}`, { schema: ProductoOut }), enabled: can(me, "productos") });
  if (!can(me, "productos")) return <SinAcceso />;
  if (producto.isPending) return <ListLoading />;
  if (producto.isError) return <ListError error={producto.error} />;
  return <Ficha p={producto.data} />;
}

function Ficha({ p }: { p: Producto }) {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const form = useFormSheet<Producto>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [baja, setBaja] = useState(false);
  const editar = can(me, "productos", "editar");
  const inv = [["productos"], ["menu"]];
  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: () => `/productos/${p.id}`,
    method: "PATCH",
    body: (v) => v.body,
    invalidate: inv,
    ok: "Producto actualizado",
    onDone: form.cerrar,
    onError: setError,
  });
  const desactivar = useApiMutation<void>({ path: () => `/productos/${p.id}`, method: "DELETE", body: () => undefined, invalidate: inv, ok: "Producto desactivado", onDone: () => setBaja(false) });

  return (
    <>
      <PageHeader
        eyebrow={
          <Link href="/panel/productos" className="hover:text-fg-2">
            ← Productos{p.categoria ? ` · ${p.categoria.nombre}` : ""}
          </Link>
        }
        title={p.nombre}
        actions={
          editar && (
            <>
              {p.activo && can(me, "productos", "eliminar") && (
                <Button variant="danger" onClick={() => setBaja(true)}>
                  Desactivar
                </Button>
              )}
              <Button variant="line" onClick={() => (setError(null), form.abrir(p))}>
                Editar datos
              </Button>
            </>
          )
        }
      />
      <div className="grid gap-16 desk:grid-cols-12">
        <div className="flex flex-col gap-6 desk:col-span-5">
          <div className="flex items-baseline gap-4">
            <Money value={p.precio_base} size="l" />
            <span className="text-sm text-fg-3">precio base</span>
          </div>
          {!p.activo && <StatusDot tone="muted">Inactivo: no se vende en ninguna sucursal</StatusDot>}
          {p.descripcion && <p className="text-lead text-fg-2">{p.descripcion}</p>}
          <p className="text-sm text-fg-3">{p.control_stock === "receta" ? "Tiene receta: el menú limita las porciones según el stock." : p.control_stock === "directo" ? "Producto directo: cada venta descuenta su propio insumo y el menú limita las porciones según el stock." : "No descuenta inventario ni limita las porciones."}</p>
          <EnSucursal key={actual?.id} p={p} editable={editar} />
        </div>
        <Galeria p={p} editable={editar} />
      </div>
      {form.state && <ProductoForm state={form.state} onOpenChange={form.onOpenChange} pending={guardar.isPending} error={error} setError={setError} onGuardar={(v) => guardar.mutate(v)} />}
      <Confirmar
        open={baja}
        onOpenChange={setBaja}
        title={`¿Desactivar ${p.nombre}?`}
        description="Sale del menú en todas las sucursales. Puedes reactivarlo desde Editar datos."
        accion="Desactivar"
        pending={desactivar.isPending}
        onConfirm={() => desactivar.mutate()}
      />
    </>
  );
}

/** Precio propio y disponibilidad del producto en la sucursal activa. */
function EnSucursal({ p, editable }: { p: Producto; editable: boolean }) {
  const { actual } = useSucursal();
  const config = p.sucursales.find((s) => s.sucursal_id === actual?.id);
  const [precio, setPrecio] = useState(config?.precio?.replace(".", ",") ?? "");
  const inv = [["productos"], ["menu"]];
  const guardar = useApiMutation<{ precio: string | null; disponible: boolean }>({
    path: () => `/productos/${p.id}/sucursales/${actual?.id}`,
    method: "PUT",
    invalidate: inv,
    ok: `Guardado para ${actual?.nombre ?? "la sucursal"}`,
  });
  const quitar = useApiMutation<void>({ path: () => `/productos/${p.id}/sucursales/${actual?.id}`, method: "DELETE", body: () => undefined, invalidate: inv, ok: "Vuelve al precio base", onDone: () => setPrecio("") });
  if (!actual) return null;
  const disponible = config?.disponible ?? true;

  return (
    <section className="flex flex-col gap-5 border-t border-line pt-6">
      <h2 className="eyebrow">En {actual.nombre}</h2>
      <Switch
        checked={disponible}
        disabled={!editable || guardar.isPending}
        label={disponible ? "Se vende en esta sucursal" : "No se vende en esta sucursal"}
        onCheckedChange={(v) => guardar.mutate({ precio: config?.precio ?? null, disponible: v })}
      />
      <form
        className="flex items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const val = precio.trim() ? parseAmountInput(precio) : null;
          if (precio.trim() && !val) return toast({ title: "Precio inválido", tone: "warn" });
          guardar.mutate({ precio: val, disponible });
        }}
      >
        <Field
          label="Precio propio"
          inputMode="decimal"
          value={precio}
          onChange={(e) => setPrecio(e.target.value)}
          placeholder={p.precio_base.replace(".", ",")}
          hint="Vacío = usa el precio base."
          disabled={!editable}
          className="flex-1"
        />
        {editable && (
          <Button type="submit" variant="line" loading={guardar.isPending} className="mb-6">
            Guardar
          </Button>
        )}
      </form>
      {editable && config && (
        <Button variant="ghost" size="sm" className="-mt-3 self-start px-0" onClick={() => quitar.mutate()}>
          Quitar configuración de esta sucursal
        </Button>
      )}
    </section>
  );
}

function Galeria({ p, editable }: { p: Producto; editable: boolean }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(0);
  const [error, setError] = useState<ErrorView | null>(null);
  const [url, setUrl] = useState("");
  const [tipo, setTipo] = useState<"imagen" | "video">("imagen");
  const refrescar = () => {
    void qc.invalidateQueries({ queryKey: ["productos"] });
    void qc.invalidateQueries({ queryKey: ["menu"] });
  };
  const portada = useApiMutation<number>({ path: (mid) => `/productos/${p.id}/medios/${mid}`, method: "PATCH", body: () => ({ es_portada: true }), invalidate: [["productos"], ["menu"]], ok: "Portada actualizada" });
  const borrar = useApiMutation<number>({ path: (mid) => `/productos/${p.id}/medios/${mid}`, method: "DELETE", body: () => undefined, invalidate: [["productos"], ["menu"]], ok: "Eliminado" });
  const ordenados = [...p.medios].sort((a, b) => Number(b.es_portada) - Number(a.es_portada) || a.orden - b.orden);

  async function subir(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    let sinPortada = p.medios.length === 0;
    for (const file of Array.from(files)) {
      setSubiendo((n) => n + 1);
      const fd = new FormData();
      fd.append("archivo", file);
      fd.append("es_portada", String(sinPortada));
      sinPortada = false;
      try {
        await api(`/productos/${p.id}/medios/archivo`, { method: "POST", body: fd });
      } catch (err) {
        setError({ ...describeError(err), title: `${file.name}: ${describeError(err).title}` });
      } finally {
        setSubiendo((n) => n - 1);
      }
    }
    refrescar();
    if (fileRef.current) fileRef.current.value = "";
  }

  async function agregarUrl(e: React.FormEvent) {
    e.preventDefault();
    if (!/^https?:\/\//.test(url.trim())) return setError({ title: "La URL debe empezar con http:// o https://", tone: "warn" });
    setError(null);
    try {
      await api(`/productos/${p.id}/medios/url`, { method: "POST", body: { tipo, url: url.trim(), es_portada: p.medios.length === 0 } });
      setUrl("");
      refrescar();
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <section aria-labelledby="galeria-t" className="flex flex-col gap-6 desk:col-span-7">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="galeria-t" className="eyebrow">
          Fotos y videos · {p.medios.length}
        </h2>
        {editable && (
          <>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/avif,video/mp4,video/quicktime,video/webm" multiple className="sr-only" id="subir-medio" onChange={(e) => void subir(e.target.files)} />
            <Button size="sm" loading={subiendo > 0} onClick={() => fileRef.current?.click()}>
              <Upload size={14} strokeWidth={1.5} aria-hidden /> Subir
            </Button>
          </>
        )}
      </div>
      {error && <ErrorBox error={error} onClose={() => setError(null)} />}
      {ordenados.length === 0 ? (
        <p className="rounded-sheet border border-dashed border-line-strong p-10 text-center text-base text-fg-3">
          Sin fotos todavía. Una buena foto vende el plato: súbela en vertical, con luz natural.
        </p>
      ) : (
        <ul className="grid grid-cols-2 gap-3 tablet:grid-cols-3">
          {ordenados.map((m) => (
            <li key={m.id} className="group relative aspect-[4/5] overflow-hidden rounded-control bg-raised">
              <Medio medio={m} alt={p.nombre} />
              {m.es_portada && <span className="absolute left-2 top-2 rounded-full bg-canvas/70 px-2 py-0.5 text-sm backdrop-blur-md">Portada</span>}
              {editable && (
                <div className="absolute inset-x-0 bottom-0 flex justify-end gap-1 bg-canvas/60 p-1.5 opacity-100 backdrop-blur-md transition-opacity desk:opacity-0 desk:group-hover:opacity-100 desk:group-focus-within:opacity-100">
                  {!m.es_portada && (
                    <button type="button" onClick={() => portada.mutate(m.id)} aria-label="Usar como portada" className="grid size-8 place-items-center rounded-md hover:bg-wash">
                      <Star size={16} strokeWidth={1.5} />
                    </button>
                  )}
                  <button type="button" onClick={() => borrar.mutate(m.id)} aria-label="Eliminar" className="grid size-8 place-items-center rounded-md hover:bg-wash hover:text-err">
                    <Trash2 size={16} strokeWidth={1.5} />
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && (
        <form onSubmit={(e) => void agregarUrl(e)} className="flex flex-wrap items-end gap-3 border-t border-line pt-6">
          <Field label="O desde una URL" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" className="min-w-60 flex-1" />
          <Select label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as "imagen" | "video")} className="w-32">
            <option value="imagen">Imagen</option>
            <option value="video">Video</option>
          </Select>
          <Button type="submit" variant="line">
            Agregar
          </Button>
        </form>
      )}
    </section>
  );
}
