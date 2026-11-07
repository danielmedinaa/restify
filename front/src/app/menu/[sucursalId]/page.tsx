"use client";

import { useParams } from "next/navigation";
import { EstadoPublico, MenuSkeleton } from "@/features/publico/Estado";
import { MenuView } from "@/features/publico/MenuView";
import { useMenuSucursal } from "@/features/publico/queries";
import { describeError } from "@/lib/api/errors";

/** Menú digital de una sucursal, solo para mirar (web, redes). */
export default function MenuPage() {
  const { sucursalId } = useParams<{ sucursalId: string }>();
  const id = Number(sucursalId);
  const menu = useMenuSucursal(Number.isInteger(id) ? id : undefined);
  if (!Number.isInteger(id)) return <EstadoPublico titulo="Menú no encontrado">{null}</EstadoPublico>;
  if (menu.isPending) return <MenuSkeleton />;
  if (menu.isError) return <EstadoPublico titulo={describeError(menu.error).title}>{null}</EstadoPublico>;
  return <MenuView menu={menu.data} eyebrow="Menú" titulo={menu.data.sucursal} />;
}
