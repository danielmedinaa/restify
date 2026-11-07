"use client";

import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { UnidadMedidaOut, type UnidadMedida } from "@/lib/api/schemas";

/** Las unidades de fábrica: se usan mientras carga el catálogo (o si no se puede leer). */
const DE_FABRICA: UnidadMedida[] = [
  { id: 1, codigo: "g", nombre: "gramos", abreviatura: "g", permite_decimales: true, subunidad_abreviatura: null, factor_subunidad: null, es_base: true, activa: true, en_uso: 0 },
  { id: 2, codigo: "kg", nombre: "kilos", abreviatura: "kg", permite_decimales: true, subunidad_abreviatura: "g", factor_subunidad: "1000", es_base: true, activa: true, en_uso: 0 },
  { id: 3, codigo: "ml", nombre: "mililitros", abreviatura: "ml", permite_decimales: true, subunidad_abreviatura: null, factor_subunidad: null, es_base: true, activa: true, en_uso: 0 },
  { id: 4, codigo: "l", nombre: "litros", abreviatura: "L", permite_decimales: true, subunidad_abreviatura: "ml", factor_subunidad: "1000", es_base: true, activa: true, en_uso: 0 },
  { id: 5, codigo: "unidad", nombre: "unidades", abreviatura: "u", permite_decimales: false, subunidad_abreviatura: null, factor_subunidad: null, es_base: true, activa: true, en_uso: 0 },
];

/** Catálogo de unidades de medida (las de fábrica + las que agregó el administrador). */
export function useUnidades() {
  const { data: me } = useMe();
  const q = useQuery({ queryKey: ["unidades"], queryFn: () => api("/unidades", { schema: z.array(UnidadMedidaOut) }), enabled: !!me, staleTime: 60_000 });
  const lista = q.data ?? DE_FABRICA;
  const por = new Map(lista.map((u) => [u.codigo, u]));
  return {
    lista,
    cargando: q.isPending,
    get: (codigo: string) => por.get(codigo),
    abrev: (codigo: string) => por.get(codigo)?.abreviatura ?? codigo,
    nombre: (codigo: string) => por.get(codigo)?.nombre ?? codigo,
    /** kg -> { abrev: "g", factor: "1000" } para escribir cantidades chicas en las recetas. */
    sub: (codigo: string) => {
      const u = por.get(codigo);
      return u?.subunidad_abreviatura && u.factor_subunidad ? { abrev: u.subunidad_abreviatura, factor: u.factor_subunidad } : null;
    },
  };
}

/** Atajos de cantidad para reponer: de a pocas piezas si es entero, redondos si admite decimales. */
export function atajos(permiteDecimales: boolean, codigo: string): string[] {
  if (!permiteDecimales) return ["1", "6", "12", "24"];
  return codigo === "kg" || codigo === "l" ? ["1", "2", "5", "10"] : ["100", "250", "500", "1000"];
}

/** El costo de g y ml se muestra por kg / L, como se piensa en cocina; el resto, por su propia unidad. */
export const FACTOR_COSTO: Record<string, number> = { g: 1000, ml: 1000 };
export const POR_COSTO: Record<string, string> = { g: "kg", ml: "L" };
