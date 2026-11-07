"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { Pagina, RolOut, SucursalOut, UsuarioOut, type Usuario } from "@/lib/api/schemas";

const fecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** Mismas reglas que el backend (app/schemas/usuarios.py). */
function problemaPassword(p: string): string | null {
  if (p.length < 10) return "La contraseña necesita al menos 10 caracteres.";
  if (p.toLowerCase() === p || p.toUpperCase() === p || !/\d/.test(p)) return "Combina mayúsculas, minúsculas y números.";
  return null;
}

export default function UsuariosPage() {
  const { data: me } = useMe();
  const [q, setQ] = useState("");
  const termino = useDeferredValue(q.trim());
  const lista = useQuery({
    queryKey: ["usuarios", termino],
    queryFn: () => api("/usuarios", { query: { q: termino, limite: 100 }, schema: Pagina(UsuarioOut) }),
    enabled: can(me, "usuarios"),
    placeholderData: keepPreviousData,
  });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api("/roles", { schema: z.array(RolOut) }), enabled: can(me, "roles") });
  const sucursales = useQuery({ queryKey: ["sucursales"], queryFn: () => api("/sucursales", { schema: z.array(SucursalOut) }), enabled: can(me, "sucursales") });
  const form = useFormSheet<Usuario>();
  const [error, setError] = useState<ErrorView | null>(null);
  const [baja, setBaja] = useState<Usuario | null>(null);

  const guardar = useApiMutation<{ id?: number; body: Record<string, unknown> }>({
    path: (v) => (v.id ? `/usuarios/${v.id}` : "/usuarios"),
    method: (v) => (v.id ? "PATCH" : "POST"),
    body: (v) => v.body,
    invalidate: [["usuarios"]],
    ok: (v) => (v.id ? "Usuario actualizado" : "Usuario creado"),
    onDone: form.cerrar,
    onError: setError,
  });
  const desactivar = useApiMutation<Usuario>({ path: (u) => `/usuarios/${u.id}`, method: "DELETE", body: () => undefined, invalidate: [["usuarios"]], ok: "Usuario desactivado; sus sesiones se cerraron", onDone: () => setBaja(null) });

  if (!can(me, "usuarios")) return <SinAcceso />;
  const opcionesSucursal = sucursales.data?.map((s) => ({ id: s.id, nombre: s.nombre })) ?? me?.sucursales ?? [];

  return (
    <>
      <PageHeader title="Usuarios" actions={can(me, "usuarios", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nuevo usuario</Button>} />
      <label className="mb-10 flex max-w-md items-center gap-3 border-b border-line-strong focus-within:border-paper">
        <Search size={18} strokeWidth={1.5} className="text-fg-3" aria-hidden />
        <span className="sr-only">Buscar usuario</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre o correo" className="h-12 w-full bg-transparent text-lead outline-none placeholder:text-fg-4 focus-visible:outline-none" />
      </label>
      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : lista.data.items.length === 0 ? (
        <EmptyState title="Nadie así" description="No hay usuarios con ese nombre o correo." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Persona</Th>
              <Th>Rol</Th>
              <Th>Sucursales</Th>
              <Th>Último acceso</Th>
              <Th>
                <span className="sr-only">Acciones</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.items.map((u) => (
              <Tr key={u.id} className={u.activo ? "" : "opacity-50"}>
                <Td>
                  <button type="button" disabled={!can(me, "usuarios", "editar") || u.id === me?.id} onClick={() => (setError(null), form.abrir(u))} className="flex flex-col text-left hover:underline disabled:hover:no-underline">
                    <span className="font-medium">{u.nombre}</span>
                    <span className="text-sm text-fg-3">{u.email}</span>
                  </button>
                </Td>
                <Td className="text-fg-2">{u.es_superadmin ? "Superadmin" : (u.rol?.nombre ?? "Sin rol")}</Td>
                <Td className="text-fg-2">{u.es_superadmin ? "Todas" : u.sucursales.map((s) => s.nombre).join(", ") || "—"}</Td>
                <Td className="text-sm text-fg-3">{u.ultimo_login ? fecha.format(new Date(u.ultimo_login)) : "Nunca"}</Td>
                <Td align="right">
                  {u.activo ? (
                    can(me, "usuarios", "eliminar") &&
                    u.id !== me?.id && (
                      <Button size="sm" variant="danger" onClick={() => setBaja(u)}>
                        Desactivar
                      </Button>
                    )
                  ) : (
                    <StatusDot tone="muted">Inactivo</StatusDot>
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
          title={form.state.item ? form.state.item.nombre : "Nuevo usuario"}
          description={form.state.item ? "Cambiar la contraseña, el rol o desactivarlo cierra sus sesiones al instante." : undefined}
          pending={guardar.isPending}
          error={error}
          onClearError={() => setError(null)}
          onSubmit={(f) => {
            const u = form.state?.item ?? null;
            const password = String(f.get("password") ?? "");
            const rol = txt(f, "rol_id");
            const body: Record<string, unknown> = {
              nombre: txt(f, "nombre"),
              email: txt(f, "email"),
              rol_id: rol ? Number(rol) : null,
              sucursal_ids: f.getAll("sucursal_ids").map(Number),
              activo: bool(f, "activo"),
            };
            if (me?.es_superadmin) body.es_superadmin = bool(f, "es_superadmin");
            if (!body.nombre || !body.email) return setError({ title: "Completa nombre y correo", tone: "warn" });
            if (!u || password) {
              const p = problemaPassword(password);
              if (p) return setError({ title: p, tone: "warn" });
              body.password = password;
            }
            if (u) {
              // PATCH solo con lo que cambió
              if (body.nombre === u.nombre) delete body.nombre;
              if (body.email === u.email) delete body.email;
              if (body.rol_id === (u.rol?.id ?? null)) delete body.rol_id;
              if (body.activo === u.activo) delete body.activo;
              if (body.es_superadmin === u.es_superadmin) delete body.es_superadmin;
              const antes = u.sucursales.map((s) => s.id).sort().join();
              if ((body.sucursal_ids as number[]).sort().join() === antes) delete body.sucursal_ids;
            }
            guardar.mutate(u ? { id: u.id, body } : { body });
          }}
        >
          <Field name="nombre" label="Nombre" defaultValue={form.state.item?.nombre ?? ""} maxLength={120} autoFocus />
          <Field name="email" label="Correo" type="email" defaultValue={form.state.item?.email ?? ""} autoComplete="off" />
          <Field
            name="password"
            label={form.state.item ? "Nueva contraseña (opcional)" : "Contraseña"}
            type="password"
            autoComplete="new-password"
            hint="10 caracteres o más, con mayúsculas, minúsculas y números."
          />
          {can(me, "roles") && (
            <Select name="rol_id" label="Rol" defaultValue={form.state.item?.rol?.id ?? ""}>
              <option value="">Sin rol</option>
              {roles.data?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.nombre}
                </option>
              ))}
            </Select>
          )}
          <fieldset className="flex flex-col gap-2">
            <legend className="eyebrow pb-2">Sucursales</legend>
            {opcionesSucursal.map((s) => (
              <label key={s.id} className="flex items-center gap-3 text-base">
                <input type="checkbox" name="sucursal_ids" value={s.id} defaultChecked={form.state?.item?.sucursales.some((x) => x.id === s.id)} className="size-4 accent-[var(--color-paper)]" />
                {s.nombre}
              </label>
            ))}
          </fieldset>
          {me?.es_superadmin && <Toggle name="es_superadmin" label="Superadmin" hint="Ve y hace todo, en todas las sucursales." defaultChecked={form.state.item?.es_superadmin ?? false} />}
          <Toggle name="activo" label="Activo" defaultChecked={form.state.item?.activo ?? true} />
        </FormSheet>
      )}
      <Confirmar
        open={baja !== null}
        onOpenChange={(o) => !o && setBaja(null)}
        title={`¿Desactivar a ${baja?.nombre ?? ""}?`}
        description="No podrá entrar y sus sesiones se cierran al instante. Puedes reactivarlo después."
        accion="Desactivar"
        pending={desactivar.isPending}
        onConfirm={() => baja && desactivar.mutate(baja)}
      />
    </>
  );
}
