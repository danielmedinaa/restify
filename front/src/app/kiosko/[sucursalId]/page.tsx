"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { EstadoPublico, MenuSkeleton } from "@/features/publico/Estado";
import { MenuView } from "@/features/publico/MenuView";
import { carritoStore } from "@/features/publico/stores";
import { LogoCliente } from "@/components/ui/LogoCliente";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { KioskoOut, PedidoCreadoOut } from "@/lib/api/schemas";

const INACTIVIDAD_MS = 120_000; // sin tocar la pantalla: se borra el pedido a medias (privacidad entre clientes)
const CONFIRMACION_S = 20; // la confirmación con el turno vuelve sola al menú

/**
 * Pantalla de autopedido del local (tablet o pantalla vertical): el cliente arma su pedido,
 * deja su nombre y recibe un número de turno. Paga en caja, donde se aprueba el pedido.
 */
export default function KioskoPage() {
  const { sucursalId } = useParams<{ sucursalId: string }>();
  const id = Number(sucursalId);
  const valido = Number.isInteger(id);
  const scope = `kiosko:${sucursalId}`;
  const q = useQuery({
    queryKey: ["publico", "kiosko", id],
    queryFn: () => api(`/public/sucursales/${id}/kiosko`, { app: "public", schema: KioskoOut }),
    enabled: valido,
    retry: false,
    refetchInterval: 30_000,
  });
  const [error, setError] = useState<ErrorView | null>(null);
  const [turno, setTurno] = useState<{ numero: number | null; nombre: string } | null>(null);

  // Pantalla del local: textos más grandes
  useEffect(() => {
    const el = document.documentElement;
    const antes = el.style.fontSize;
    el.style.fontSize = "125%";
    return () => {
      el.style.fontSize = antes;
    };
  }, []);

  // Inactividad: se vacía el carrito para que el siguiente cliente no vea lo del anterior
  const reloj = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => {
    const reiniciar = () => {
      clearTimeout(reloj.current);
      reloj.current = setTimeout(() => carritoStore(scope).set(() => []), INACTIVIDAD_MS);
    };
    reiniciar();
    const eventos = ["pointerdown", "keydown", "scroll"] as const;
    eventos.forEach((e) => window.addEventListener(e, reiniciar, { passive: true }));
    return () => {
      clearTimeout(reloj.current);
      eventos.forEach((e) => window.removeEventListener(e, reiniciar));
    };
  }, [scope]);

  // La confirmación vuelve sola al menú
  useEffect(() => {
    if (!turno) return;
    const t = setTimeout(() => setTurno(null), CONFIRMACION_S * 1000);
    return () => clearTimeout(t);
  }, [turno]);

  if (!valido) return <EstadoPublico titulo="Pantalla no encontrada">{null}</EstadoPublico>;
  if (q.isPending) return <MenuSkeleton />;
  if (q.isError) {
    const e = describeError(q.error);
    return <EstadoPublico titulo={e.title}>{e.description ?? "Pide ayuda al personal."}</EstadoPublico>;
  }
  if (!q.data.disponible) {
    return (
      <EstadoPublico eyebrow={q.data.sucursal} titulo="Autopedido no disponible">
        <p>Por ahora haz tu pedido directamente en caja. ¡Gracias!</p>
      </EstadoPublico>
    );
  }

  if (turno) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-2xl flex-col items-center justify-center gap-8 px-6 text-center">
        <LogoCliente size={72} />
        <span className="eyebrow">{q.data.sucursal}</span>
        <p className="text-lead text-fg-2">{turno.nombre}, tu número de turno es</p>
        <p className="font-display text-[10rem] leading-none">{turno.numero ?? "—"}</p>
        <p className="max-w-md text-lead text-fg-2">Pasa a caja con este número para pagar. Cuando se apruebe, tu pedido entra a cocina.</p>
        <button type="button" onClick={() => setTurno(null)} className="text-base text-fg underline underline-offset-4">
          Hacer otro pedido
        </button>
      </main>
    );
  }

  return (
    <MenuView
      menu={q.data.menu}
      eyebrow="Haz tu pedido aquí"
      titulo={q.data.sucursal}
      pedido={{
        scope,
        conDatos: true,
        kiosko: true,
        accion: "Enviar pedido",
        error,
        limpiarError: () => setError(null),
        enviar: async (p) => {
          setError(null);
          try {
            const creado = await api(`/public/sucursales/${id}/kiosko/pedidos`, { app: "public", method: "POST", body: p, schema: PedidoCreadoOut });
            setTurno({ numero: creado.pedido.turno, nombre: p.nombre_cliente ?? "" });
          } catch (err) {
            setError(describeError(err));
            void q.refetch();
            throw err;
          }
        },
      }}
    />
  );
}
