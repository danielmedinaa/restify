"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useDeferredValue, useMemo, useState } from "react";
import { CommandPalette, type CommandItem } from "@/components/ui/CommandPalette";
import { can } from "@/features/auth/useMe";
import { tituloComanda } from "@/features/comandas/estado";
import { useComandasAbiertas, useMesas } from "@/features/comandas/queries";
import { api } from "@/lib/api/client";
import { ClienteOut, Pagina, type Me } from "@/lib/api/schemas";
import type { NavGroup } from "./nav";

/**
 * ⌘K del panel: navegación, comandas abiertas (abrir y cobrar), mesas y búsqueda
 * remota de clientes. Las comandas y mesas salen del caché vivo, sin pedir nada.
 */
export function PanelCommands({
  open,
  onOpenChange,
  me,
  groups,
  sucursalId,
  onLogout,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  me: Me;
  groups: NavGroup[];
  sucursalId: number | undefined;
  onLogout: () => void;
}) {
  const router = useRouter();
  const abiertas = useComandasAbiertas(sucursalId);
  const mesas = useMesas(sucursalId);
  const [q, setQ] = useState("");
  const term = useDeferredValue(q.trim());
  const clientes = useQuery({
    queryKey: ["clientes", "buscar", term],
    queryFn: () => api("/clientes", { query: { q: term, limite: 5 }, schema: Pagina(ClienteOut) }),
    enabled: open && term.length >= 2 && can(me, "clientes"),
    staleTime: 30_000,
  });

  const items: CommandItem[] = useMemo(() => {
    const go = (href: string) => () => router.push(href);
    const out: CommandItem[] = [];
    for (const c of abiertas.data ?? []) {
      const t = tituloComanda(c);
      out.push({ id: `c-${c.id}`, label: `${t} · comanda ${c.id}`, group: "Comandas abiertas", keywords: [String(c.id), c.nombre_cliente ?? ""], onSelect: go(`/panel/comandas/${c.id}`) });
      if (can(me, "caja")) out.push({ id: `cobrar-${c.id}`, label: `Cobrar ${t}`, group: "Acciones", keywords: ["pagar", "caja", String(c.id)], onSelect: go(`/panel/caja/${c.id}`) });
    }
    for (const m of mesas.data ?? []) {
      const comanda = m.comanda_abierta_id;
      out.push({
        id: `m-${m.id}`,
        label: /^\d+$/.test(m.nombre) ? `Mesa ${m.nombre}` : m.nombre,
        hint: comanda ? "Ocupada" : "Libre",
        group: "Mesas",
        onSelect: go(comanda ? `/panel/comandas/${comanda}` : "/panel"),
      });
    }
    for (const c of clientes.data?.items ?? []) {
      out.push({ id: `cl-${c.id}`, label: c.nombre, hint: c.documento ?? c.telefono ?? undefined, group: "Clientes", keywords: [term], onSelect: go(`/panel/clientes?${new URLSearchParams({ q: c.nombre })}`) });
    }
    for (const g of groups) {
      for (const i of g.items) out.push({ id: i.href, label: i.label, group: "Ir a", keywords: i.keywords, onSelect: go(i.href) });
    }
    out.push({ id: "cuenta", label: "Mi cuenta", group: "Cuenta", keywords: ["contraseña", "perfil"], onSelect: go("/panel/cuenta") });
    out.push({ id: "salir", label: "Salir", group: "Cuenta", keywords: ["cerrar sesión"], onSelect: onLogout });
    return out;
  }, [abiertas.data, mesas.data, clientes.data, groups, me, router, onLogout, term]);

  return (
    <CommandPalette
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setQ("");
      }}
      items={items}
      onQueryChange={setQ}
    />
  );
}
