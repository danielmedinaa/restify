"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { can, useMe } from "@/features/auth/useMe";
import { Confirmar, FormSheet, txt, useApiMutation, useFormSheet } from "@/features/crud/crud";
import { api } from "@/lib/api/client";
import type { ErrorView } from "@/lib/api/errors";
import { ACCIONES, MODULOS, RolOut, type Accion, type Modulo, type Rol } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { snappy } from "@/lib/motion";

const NOMBRE_MODULO: Record<Modulo, string> = {
  usuarios: "Usuarios",
  roles: "Roles",
  sucursales: "Sucursales",
  monedas: "Monedas",
  insumos: "Insumos",
  inventario: "Inventario",
  recetas: "Recetas",
  categorias: "Categorías",
  productos: "Productos",
  clientes: "Clientes",
  mesas: "Mesas",
  comandas: "Comandas",
  caja: "Caja",
  cocina: "Cocina",
  ventas: "Ventas",
  bitacora: "Bitácora",
  compras: "Compras y proveedores",
};
const NOMBRE_ACCION: Record<Accion, string> = { crear: "Crear", leer: "Ver", editar: "Editar", eliminar: "Eliminar" };

type Matriz = Record<Modulo, Record<Accion, boolean>>;

function matrizDe(rol: Rol): Matriz {
  const m = Object.fromEntries(MODULOS.map((mod) => [mod, { crear: false, leer: false, editar: false, eliminar: false }])) as Matriz;
  for (const p of rol.permisos) if (p.modulo in m) m[p.modulo as Modulo] = { crear: p.crear, leer: p.leer, editar: p.editar, eliminar: p.eliminar };
  return m;
}

export default function RolesPage() {
  const { data: me } = useMe();
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api("/roles", { schema: z.array(RolOut) }), enabled: can(me, "roles") });
  const [elegido, setElegido] = useState<number | null>(null);
  const form = useFormSheet<null>();
  const [error, setError] = useState<ErrorView | null>(null);
  const crear = useApiMutation<{ nombre: string; descripcion: string | null }>({
    path: () => "/roles",
    method: "POST",
    body: (v) => ({ ...v, permisos: [] }),
    invalidate: [["roles"]],
    ok: "Rol creado. Ahora pinta sus permisos.",
    onDone: form.cerrar,
    onError: setError,
  });

  if (!can(me, "roles")) return <SinAcceso />;
  const lista = roles.data ?? [];
  const rol = lista.find((r) => r.id === elegido) ?? lista[0];

  return (
    <>
      <PageHeader title="Roles" actions={can(me, "roles", "crear") && <Button onClick={() => (setError(null), form.abrir(null))}>Nuevo rol</Button>} />
      {roles.isPending ? (
        <ListLoading />
      ) : roles.isError ? (
        <ListError error={roles.error} />
      ) : lista.length === 0 ? (
        <p className="text-lead text-fg-2">Todavía no hay roles. Crea uno (Caja, Mesero, Cocina…) y pinta lo que puede hacer.</p>
      ) : (
        <div className="grid gap-12 desk:grid-cols-[220px_1fr]">
          <nav aria-label="Roles" className="flex gap-1 overflow-x-auto desk:flex-col">
            {lista.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setElegido(r.id)}
                aria-current={r.id === rol?.id ? "true" : undefined}
                className={cn(
                  "whitespace-nowrap rounded-control px-3 py-2.5 text-left text-base transition-colors",
                  r.id === rol?.id ? "bg-wash-strong text-fg" : "text-fg-2 hover:bg-wash hover:text-fg",
                )}
              >
                {r.nombre}
              </button>
            ))}
          </nav>
          {rol && <EditorRol key={rol.id} rol={rol} />}
        </div>
      )}
      {form.state && (
        <FormSheet
          key={form.state.key}
          open={form.state.open}
          onOpenChange={form.onOpenChange}
          title="Nuevo rol"
          pending={crear.isPending}
          error={error}
          onClearError={() => setError(null)}
          submitLabel="Crear rol"
          onSubmit={(f) => {
            const nombre = txt(f, "nombre");
            if (!nombre) return setError({ title: "Ponle un nombre al rol", tone: "warn" });
            crear.mutate({ nombre, descripcion: txt(f, "descripcion") });
          }}
        >
          <Field name="nombre" label="Nombre" maxLength={120} placeholder="Caja, Mesero, Cocina…" autoFocus />
          <Field name="descripcion" label="Descripción" maxLength={255} />
        </FormSheet>
      )}
    </>
  );
}

function EditorRol({ rol }: { rol: Rol }) {
  const { data: me } = useMe();
  const original = matrizDe(rol);
  const [matriz, setMatriz] = useState<Matriz>(original);
  const [error, setError] = useState<ErrorView | null>(null);
  const [borrar, setBorrar] = useState(false);
  const pintando = useRef<boolean | null>(null);
  const editable = can(me, "roles", "editar");
  const sucio = JSON.stringify(matriz) !== JSON.stringify(original);

  useEffect(() => {
    const soltar = () => (pintando.current = null);
    window.addEventListener("pointerup", soltar);
    return () => window.removeEventListener("pointerup", soltar);
  }, []);

  const guardar = useApiMutation<void>({
    path: () => `/roles/${rol.id}`,
    method: "PATCH",
    body: () => ({ permisos: MODULOS.map((m) => ({ modulo: m, ...matriz[m] })) }),
    invalidate: [["roles"], ["auth", "me"]],
    ok: `Permisos de ${rol.nombre} guardados`,
    onError: setError,
  });
  const eliminar = useApiMutation<void>({ path: () => `/roles/${rol.id}`, method: "DELETE", body: () => undefined, invalidate: [["roles"]], ok: "Rol eliminado", onDone: () => setBorrar(false) });

  const set = (m: Modulo, a: Accion, v: boolean) => setMatriz((x) => ({ ...x, [m]: { ...x[m], [a]: v } }));
  const fila = (m: Modulo) => {
    const todo = ACCIONES.every((a) => matriz[m][a]);
    setMatriz((x) => ({ ...x, [m]: Object.fromEntries(ACCIONES.map((a) => [a, !todo])) as Record<Accion, boolean> }));
  };
  const columna = (a: Accion) => {
    const todo = MODULOS.every((m) => matriz[m][a]);
    setMatriz((x) => Object.fromEntries(MODULOS.map((m) => [m, { ...x[m], [a]: !todo }])) as Matriz);
  };

  // Navegación con flechas entre celdas (roving tabindex)
  const celdas = useRef(new Map<string, HTMLButtonElement>());
  const [foco, setFoco] = useState("0,0");
  function mover(e: React.KeyboardEvent, r: number, c: number) {
    const d = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
    if (!d) return;
    e.preventDefault();
    const nr = Math.min(MODULOS.length - 1, Math.max(0, r + d[0]!));
    const nc = Math.min(ACCIONES.length - 1, Math.max(0, c + d[1]!));
    setFoco(`${nr},${nc}`);
    celdas.current.get(`${nr},${nc}`)?.focus();
  }

  return (
    <section aria-label={`Permisos de ${rol.nombre}`} className="flex min-w-0 flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="font-display text-display-m leading-none">{rol.nombre}</h2>
          {rol.descripcion && <p className="text-base text-fg-2">{rol.descripcion}</p>}
        </div>
        <div className="flex gap-2">
          {can(me, "roles", "eliminar") && (
            <Button variant="danger" onClick={() => setBorrar(true)}>
              Eliminar rol
            </Button>
          )}
          {editable && (
            <>
              <Button variant="ghost" disabled={!sucio} onClick={() => setMatriz(original)}>
                Descartar
              </Button>
              <Button disabled={!sucio} loading={guardar.isPending} onClick={() => guardar.mutate()}>
                Guardar permisos
              </Button>
            </>
          )}
        </div>
      </header>
      {editable && <p className="text-sm text-fg-3">Haz clic y arrastra para pintar varias celdas. El nombre de una fila o columna la cambia completa. Con teclado: flechas y espacio.</p>}
      {error && <ErrorBox error={error} onClose={() => setError(null)} />}

      <div className="overflow-x-auto">
        <table
          role="grid"
          aria-label="Matriz de permisos"
          className="w-full min-w-[560px] touch-none select-none border-collapse"
          // Pintar arrastrando: se busca la celda bajo el puntero (con captura de puntero
          // activa, las celdas vecinas no reciben pointerenter)
          onPointerMove={(e) => {
            const valor = pintando.current;
            if (valor === null) return;
            const celda = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>("[data-celda]")?.dataset.celda;
            if (!celda) return;
            const [mod, acc] = celda.split(":") as [Modulo, Accion];
            if (matriz[mod][acc] !== valor) set(mod, acc, valor);
          }}
        >
          <thead>
            <tr>
              <th scope="col" className="w-[40%] pb-3 text-left">
                <span className="eyebrow">Módulo</span>
              </th>
              {ACCIONES.map((a) => (
                <th key={a} scope="col" className="pb-3">
                  <button type="button" disabled={!editable} onClick={() => columna(a)} className="eyebrow rounded-md px-2 py-1 hover:bg-wash hover:text-fg disabled:hover:bg-transparent">
                    {NOMBRE_ACCION[a]}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MODULOS.map((m, r) => (
              <tr key={m} className="border-t border-line">
                <th scope="row" className="py-1 text-left font-normal">
                  <button type="button" disabled={!editable} onClick={() => fila(m)} className="rounded-md px-2 py-1.5 text-base hover:bg-wash disabled:hover:bg-transparent">
                    {NOMBRE_MODULO[m]}
                  </button>
                </th>
                {ACCIONES.map((a, c) => {
                  const on = matriz[m][a];
                  const cambiado = on !== original[m][a];
                  return (
                    <td key={a} className="p-1 text-center">
                      <button
                        ref={(el) => {
                          if (el) celdas.current.set(`${r},${c}`, el);
                        }}
                        type="button"
                        role="checkbox"
                        aria-checked={on}
                        aria-label={`${NOMBRE_ACCION[a]} ${NOMBRE_MODULO[m]}`}
                        tabIndex={foco === `${r},${c}` ? 0 : -1}
                        disabled={!editable}
                        onKeyDown={(e) => mover(e, r, c)}
                        onFocus={() => setFoco(`${r},${c}`)}
                        onClick={(e) => {
                          // El click de teclado (detail 0) alterna; el de puntero ya lo pintó en pointerdown
                          if (e.detail === 0) set(m, a, !on);
                        }}
                        data-celda={`${m}:${a}`}
                        onPointerDown={() => {
                          if (!editable) return;
                          pintando.current = !on;
                          set(m, a, !on);
                        }}
                        className="group relative mx-auto grid h-10 w-full max-w-[96px] place-items-center rounded-control transition-colors hover:bg-wash"
                      >
                        <motion.span
                          initial={false}
                          animate={{ scale: on ? 1 : 0.55, opacity: on ? 1 : 0.35 }}
                          transition={snappy}
                          className={cn("block h-2.5 w-8 rounded-full", on ? "bg-paper" : "bg-fg-4")}
                        />
                        {cambiado && <span aria-hidden className="absolute right-2 top-1.5 size-1 rounded-full bg-warn" />}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Confirmar
        open={borrar}
        onOpenChange={setBorrar}
        title={`¿Eliminar el rol ${rol.nombre}?`}
        description="Solo se puede si ningún usuario lo tiene asignado."
        accion="Eliminar"
        pending={eliminar.isPending}
        onConfirm={() => eliminar.mutate()}
      />
    </section>
  );
}
