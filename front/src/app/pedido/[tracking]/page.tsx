"use client";

import { useParams } from "next/navigation";
import { EstadoPublico } from "@/features/publico/Estado";
import { PedidoView } from "@/features/publico/PedidoView";
import { usePedido, usePedidoLive } from "@/features/publico/queries";
import { ApiError, describeError } from "@/lib/api/errors";

export default function PedidoPage() {
  const { tracking } = useParams<{ tracking: string }>();
  const pedido = usePedido(tracking);
  const conexion = usePedidoLive(tracking, pedido.data?.estado === "abierta");

  if (pedido.isPending) {
    return (
      <main className="mx-auto max-w-2xl px-5 pt-8" role="status" aria-busy>
        <span className="sr-only">Cargando tu pedido</span>
        <span className="block h-3 w-28 skeleton" />
        <span className="mt-14 block h-16 w-64 skeleton" />
        <div className="mt-12 flex flex-col gap-6">
          {[0, 1, 2].map((i) => (
            <span key={i} className="block h-6 w-full skeleton" />
          ))}
        </div>
      </main>
    );
  }
  if (pedido.isError) {
    if (pedido.error instanceof ApiError && pedido.error.status === 404) {
      return (
        <EstadoPublico titulo="No encontramos ese pedido">
          <p>Revisa que el enlace esté completo. Si el pedido es de hoy, el mesero te lo puede volver a enviar.</p>
        </EstadoPublico>
      );
    }
    return <EstadoPublico titulo={describeError(pedido.error).title}>{null}</EstadoPublico>;
  }
  return <PedidoView pedido={pedido.data} tracking={tracking} conexion={conexion} />;
}
