"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { EstadoPublico, MenuSkeleton } from "@/features/publico/Estado";
import { MenuView } from "@/features/publico/MenuView";
import { pedidoKey, useMenuSucursal, usePedido } from "@/features/publico/queries";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { PedidoPublicoOut } from "@/lib/api/schemas";

/** El cliente agrega platos a su pedido abierto (quedan por aprobar en caja). */
export default function AgregarPage() {
  const { tracking } = useParams<{ tracking: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const pedido = usePedido(tracking);
  const menu = useMenuSucursal(pedido.data?.sucursal_id, pedido.data?.estado === "abierta");
  const [error, setError] = useState<ErrorView | null>(null);

  if (pedido.isPending || (pedido.data?.estado === "abierta" && menu.isPending)) return <MenuSkeleton />;
  if (pedido.isError) return <EstadoPublico titulo={describeError(pedido.error).title}>{null}</EstadoPublico>;
  if (pedido.data.estado !== "abierta") {
    return (
      <EstadoPublico titulo="Este pedido ya cerró">
        <p>Para pedir de nuevo, escanea el QR de tu mesa.</p>
      </EstadoPublico>
    );
  }
  if (menu.isError) return <EstadoPublico titulo={describeError(menu.error).title}>{null}</EstadoPublico>;
  if (!menu.data) return <MenuSkeleton />;

  return (
    <MenuView
      menu={menu.data}
      eyebrow="Pedir algo más"
      titulo={pedido.data.mesa ? (/^\d+$/.test(pedido.data.mesa) ? `Mesa ${pedido.data.mesa}` : pedido.data.mesa) : pedido.data.sucursal}
      pedido={{
        scope: `agregar:${tracking}`,
        conDatos: false,
        accion: "Agregar a mi pedido",
        error,
        limpiarError: () => setError(null),
        enviar: async ({ items }) => {
          setError(null);
          try {
            const actualizado = await api(`/public/pedidos/${tracking}/items`, { app: "public", method: "POST", body: { items }, schema: PedidoPublicoOut });
            qc.setQueryData(pedidoKey(tracking), actualizado);
            router.push(`/pedido/${tracking}`);
          } catch (err) {
            setError(describeError(err));
            void menu.refetch();
            throw err;
          }
        },
      }}
    />
  );
}
