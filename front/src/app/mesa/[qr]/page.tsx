"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { EstadoPublico, MenuSkeleton } from "@/features/publico/Estado";
import { MenuView } from "@/features/publico/MenuView";
import { useMesaPublica } from "@/features/publico/queries";
import { misPedidosStore } from "@/features/publico/stores";
import { api } from "@/lib/api/client";
import { ApiError, describeError, type ErrorView } from "@/lib/api/errors";
import { PedidoCreadoOut } from "@/lib/api/schemas";

const nombreMesa = (m: string) => (/^\d+$/.test(m) ? `Mesa ${m}` : m);

export default function MesaPage() {
  const { qr } = useParams<{ qr: string }>();
  const router = useRouter();
  const mesa = useMesaPublica(qr);
  const misPedidos = misPedidosStore.use();
  const [error, setError] = useState<ErrorView | null>(null);
  const [soloMirar, setSoloMirar] = useState(false);

  if (mesa.isPending) return <MenuSkeleton />;
  if (mesa.isError) {
    const err = mesa.error;
    if (err instanceof ApiError && err.status === 404) {
      return (
        <EstadoPublico titulo="Este QR no funciona">
          <p>Puede que lo hayan cambiado o que la mesa esté cerrada. Pídele al mesero el código nuevo.</p>
        </EstadoPublico>
      );
    }
    const e = describeError(err);
    return (
      <EstadoPublico titulo={e.title}>
        <p>{e.description ?? "Intenta de nuevo en un momento."}</p>
        <button type="button" onClick={() => void mesa.refetch()} className="self-start text-fg underline underline-offset-4">
          Reintentar
        </button>
      </EstadoPublico>
    );
  }

  const { menu } = mesa.data;
  const titulo = nombreMesa(mesa.data.mesa);
  const miPedido = misPedidos[qr];

  // 423: la mesa ya tiene una comanda abierta
  if (mesa.data.ocupada && !soloMirar) {
    return (
      <EstadoPublico eyebrow={mesa.data.sucursal} titulo={titulo}>
        {miPedido ? (
          <>
            <p>Tu pedido está en curso. Desde ahí ves cada plato y puedes pedir algo más.</p>
            <Link href={`/pedido/${miPedido}`} className="mt-2 inline-flex h-14 items-center justify-center rounded-control bg-paper px-6 text-lead font-medium text-ink">
              Ver mi pedido
            </Link>
          </>
        ) : (
          <>
            <p>Esta mesa ya tiene un pedido abierto, así que el QR no acepta uno nuevo.</p>
            <p>Si el pedido es tuyo, abre el enlace de seguimiento que recibiste. Si no, avísale al mesero y lo resuelve en un momento.</p>
          </>
        )}
        <button type="button" onClick={() => setSoloMirar(true)} className="self-start pt-2 text-base text-fg underline underline-offset-4">
          Ver el menú
        </button>
      </EstadoPublico>
    );
  }

  return (
    <MenuView
      menu={menu}
      eyebrow={mesa.data.sucursal}
      titulo={titulo}
      pedido={
        mesa.data.ocupada
          ? undefined
          : {
              scope: qr,
              conDatos: true,
              accion: "Enviar pedido",
              error,
              limpiarError: () => setError(null),
              enviar: async (p) => {
                setError(null);
                try {
                  const creado = await api(`/public/mesas/${qr}/comandas`, { app: "public", method: "POST", body: p, schema: PedidoCreadoOut });
                  misPedidosStore.set((m) => ({ ...m, [qr]: creado.tracking_token }));
                  router.push(`/pedido/${creado.tracking_token}`);
                } catch (err) {
                  setError(describeError(err));
                  // Mesa tomada o porciones cambiaron: se vuelve a pedir el estado real
                  if (err instanceof ApiError && (err.status === 423 || err.status === 409)) void mesa.refetch();
                  throw err;
                }
              },
            }
      }
    />
  );
}
