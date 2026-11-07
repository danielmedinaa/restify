"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { can } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { SucursalOut, type Me } from "@/lib/api/schemas";
import { z } from "zod";

import { SUCURSAL_COOKIE } from "./constants";

interface SucursalCtx {
  sucursales: { id: number; nombre: string }[];
  actual: { id: number; nombre: string } | null;
  cambiar: (id: number) => void;
  cargando: boolean;
}

const Ctx = createContext<SucursalCtx | null>(null);

/**
 * Sucursal activa del panel. Las queries que dependen de ella llevan su id en la
 * key ([..., "sucursal", id]), así que al cambiarla se piden solas.
 * Se recuerda en una cookie (preferencia, no secreto)
 * para que el servidor la conozca en el primer render y no haya parpadeo.
 */
export function SucursalProvider({ me, initialId, children }: { me: Me; initialId: number | null; children: React.ReactNode }) {
  // Quien puede leer sucursales ve la lista completa (el superadmin, todas);
  // el resto, las que tiene asignadas en su perfil.
  const lista = useQuery({
    queryKey: ["sucursales"],
    queryFn: () => api("/sucursales", { schema: z.array(SucursalOut) }),
    enabled: can(me, "sucursales", "leer"),
  });
  const sucursales = useMemo(
    () => (lista.data ? lista.data.filter((s) => s.activa).map(({ id, nombre }) => ({ id, nombre })) : me.sucursales),
    [lista.data, me.sucursales],
  );

  const [elegida, setElegida] = useState<number | null>(initialId);
  const actual = sucursales.find((s) => s.id === elegida) ?? sucursales[0] ?? null;

  const cambiar = useCallback(
    (id: number) => {
      setElegida(id);
      document.cookie = `${SUCURSAL_COOKIE}=${id}; Path=/; Max-Age=31536000; SameSite=Strict`;
    },
    [],
  );

  return (
    <Ctx.Provider value={{ sucursales, actual, cambiar, cargando: lista.isLoading }}>{children}</Ctx.Provider>
  );
}

export function useSucursal(): SucursalCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSucursal fuera de SucursalProvider");
  return ctx;
}
