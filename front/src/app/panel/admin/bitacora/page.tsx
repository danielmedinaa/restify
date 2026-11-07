"use client";

import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  Armchair,
  BookOpen,
  ChefHat,
  Coins,
  FileText,
  History,
  Package,
  ReceiptText,
  ShieldCheck,
  Store,
  UserCog,
  Users,
  UtensilsCrossed,
  Wallet,
  Wheat,
  type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";
import { useDeferredValue, useState } from "react";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select } from "@/components/ui/Select";
import { can, useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { BitacoraOut, Pagina, UsuarioOut, type EntradaBitacora } from "@/lib/api/schemas";
import { smooth } from "@/lib/motion";

const MODULOS: Record<string, { label: string; icon: LucideIcon }> = {
  inventario: { label: "Inventario", icon: Package },
  caja: { label: "Caja", icon: Wallet },
  comandas: { label: "Comandas", icon: ReceiptText },
  cocina: { label: "Cocina", icon: ChefHat },
  ventas: { label: "Facturación", icon: FileText },
  productos: { label: "Productos", icon: UtensilsCrossed },
  insumos: { label: "Insumos", icon: Wheat },
  recetas: { label: "Recetas", icon: BookOpen },
  monedas: { label: "Monedas", icon: Coins },
  clientes: { label: "Clientes", icon: Users },
  mesas: { label: "Mesas", icon: Armchair },
  usuarios: { label: "Usuarios", icon: UserCog },
  roles: { label: "Roles", icon: ShieldCheck },
  sucursales: { label: "Sucursales", icon: Store },
};

const PAGINA = 50;
const dia = new Intl.DateTimeFormat("es", { weekday: "long", day: "numeric", month: "long" });
const hora = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" });

/** "Hoy", "Ayer" o "jueves 23 de octubre". */
function etiquetaDia(fecha: Date): string {
  const hoy = new Date();
  const ayer = new Date();
  ayer.setDate(hoy.getDate() - 1);
  if (fecha.toDateString() === hoy.toDateString()) return "Hoy";
  if (fecha.toDateString() === ayer.toDateString()) return "Ayer";
  const t = dia.format(fecha);
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function iniciales(nombre: string): string {
  return nombre
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export default function BitacoraPage() {
  const { data: me } = useMe();
  const [q, setQ] = useState("");
  const busqueda = useDeferredValue(q.trim());
  const [modulo, setModulo] = useState("");
  const [usuarioId, setUsuarioId] = useState("");
  const [rango, setRango] = useState({ desde: "", hasta: "" });
  const habilitado = can(me, "bitacora");

  const usuarios = useQuery({
    queryKey: ["usuarios", "todos"],
    queryFn: () => api("/usuarios", { query: { limite: 100 }, schema: Pagina(UsuarioOut) }),
    enabled: habilitado && can(me, "usuarios"),
  });
  const filtros = { q: busqueda || undefined, modulo: modulo || undefined, usuario_id: usuarioId || undefined, desde: rango.desde || undefined, hasta: rango.hasta || undefined };
  const lista = useInfiniteQuery({
    queryKey: ["bitacora", filtros],
    queryFn: ({ pageParam }) => api("/bitacora", { query: { ...filtros, limite: PAGINA, offset: pageParam }, schema: Pagina(BitacoraOut) }),
    initialPageParam: 0,
    getNextPageParam: (ultima) => (ultima.offset + ultima.limite < ultima.total ? ultima.offset + ultima.limite : undefined),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  });

  if (!habilitado) return <SinAcceso />;
  const entradas = lista.data?.pages.flatMap((p) => p.items) ?? [];
  const porDia = new Map<string, EntradaBitacora[]>();
  for (const e of entradas) {
    const k = etiquetaDia(new Date(e.created_at));
    porDia.set(k, [...(porDia.get(k) ?? []), e]);
  }
  const hayFiltros = q || modulo || usuarioId || rango.desde || rango.hasta;

  return (
    <>
      <PageHeader eyebrow="Administración" title="Bitácora" />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">Quién hizo qué y cuándo: reposiciones, cobros, cambios de precio y de tasa, usuarios y más.</p>

      <div className="mb-12 grid gap-6 tablet:grid-cols-2 desk:grid-cols-[2fr_1fr_1fr_auto_auto]">
        <label className="flex flex-col gap-1.5">
          <span className="eyebrow">Buscar</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Carne, comanda #12, tasa…"
            className="h-11 border-b border-line-strong bg-transparent text-base outline-none placeholder:text-fg-4 focus:border-paper"
          />
        </label>
        <Select label="Módulo" value={modulo} onChange={(e) => setModulo(e.target.value)}>
          <option value="">Todos</option>
          {Object.entries(MODULOS).map(([k, m]) => (
            <option key={k} value={k}>
              {m.label}
            </option>
          ))}
        </Select>
        <Select label="Persona" value={usuarioId} onChange={(e) => setUsuarioId(e.target.value)} disabled={!usuarios.data}>
          <option value="">Todas</option>
          {usuarios.data?.items.map((u) => (
            <option key={u.id} value={u.id}>
              {u.nombre}
            </option>
          ))}
        </Select>
        {(["desde", "hasta"] as const).map((k) => (
          <label key={k} className="flex flex-col gap-1.5">
            <span className="eyebrow">{k === "desde" ? "Desde" : "Hasta"}</span>
            <input
              type="date"
              value={rango[k]}
              onChange={(e) => setRango((r) => ({ ...r, [k]: e.target.value }))}
              className="h-11 border-b border-line-strong bg-transparent text-base outline-none [color-scheme:dark] focus:border-paper"
            />
          </label>
        ))}
      </div>

      {lista.isPending ? (
        <ListLoading />
      ) : lista.isError ? (
        <ListError error={lista.error} />
      ) : entradas.length === 0 ? (
        <EmptyState
          title={hayFiltros ? "Nada con esos filtros" : "Aún no hay actividad"}
          description={hayFiltros ? "Prueba con otras fechas o quita algún filtro." : "Aquí aparecerá cada cambio que haga tu equipo."}
        />
      ) : (
        <div className="flex flex-col gap-12">
          {[...porDia.entries()].map(([d, lista]) => (
            <section key={d} aria-label={d} className="flex flex-col">
              <h2 className="sticky top-0 z-[1] -mx-2 mb-2 bg-canvas/80 px-2 py-2 font-display text-display-s backdrop-blur-xl">{d}</h2>
              <ol className="relative flex flex-col">
                <span aria-hidden className="absolute bottom-4 left-[19px] top-4 w-px bg-line" />
                {lista.map((e) => (
                  <Entrada key={e.id} e={e} />
                ))}
              </ol>
            </section>
          ))}
          {lista.hasNextPage && (
            <Button variant="line" className="self-center" loading={lista.isFetchingNextPage} onClick={() => void lista.fetchNextPage()}>
              Ver más
            </Button>
          )}
        </div>
      )}
    </>
  );
}

function Entrada({ e }: { e: EntradaBitacora }) {
  const m = MODULOS[e.modulo] ?? { label: e.modulo, icon: History };
  const Icono = m.icon;
  // "Repuso 300 g…" -> "Daniel repuso 300 g…"
  const accion = e.descripcion.charAt(0).toLowerCase() + e.descripcion.slice(1);
  return (
    <motion.li layout="position" transition={smooth} className="relative flex gap-4 py-3">
      <span
        aria-hidden
        className="z-[1] grid size-10 shrink-0 place-items-center rounded-full bg-raised text-sm font-medium ring-4 ring-canvas"
        title={e.usuario_nombre}
      >
        {iniciales(e.usuario_nombre)}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5 pt-1">
        <p className="text-base leading-snug">
          <span className="font-semibold">{e.usuario_nombre}</span> <span className="text-fg-2">{accion}</span>
        </p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-3">
          <span className="inline-flex items-center gap-1.5">
            <Icono size={14} strokeWidth={1.5} aria-hidden />
            {m.label}
          </span>
          <span className="tabular">{hora.format(new Date(e.created_at))}</span>
          {e.sucursal && <span>{e.sucursal}</span>}
        </p>
      </div>
    </motion.li>
  );
}
