"use client";

import { ChatPanel } from "@/features/chat/ChatPanel";
import { useChatPublico } from "@/features/chat/queries";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { Money } from "@/components/ui/Money";
import { Segmented } from "@/components/ui/Segmented";
import { StatusDot } from "@/components/ui/Status";
import type { EstadoItem, PedidoPublico } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { smooth, snappy } from "@/lib/motion";
import type { ConexionPedido } from "./queries";
import { monedaStore } from "./stores";

const ETIQUETA: Record<EstadoItem, string> = {
  pendiente: "Esperando confirmación",
  en_cocina: "En cocina",
  preparando: "Preparándose",
  listo: "Listo",
  entregado: "En tu mesa",
  cancelado: "Cancelado",
};

function titular(p: PedidoPublico, listos: number, vigentes: number): string {
  if (p.estado === "cerrada") return "¡Gracias por venir!";
  if (p.estado === "cancelada") return "Pedido cancelado";
  if (vigentes === 0) return "Tu pedido";
  if (listos === vigentes) return "Todo listo";
  if (p.items.every((i) => i.estado === "pendiente" || i.estado === "cancelado")) return "Recibimos tu pedido";
  return "Está en marcha";
}

export function PedidoView({ pedido, tracking, conexion }: { pedido: PedidoPublico; tracking: string; conexion: ConexionPedido }) {
  const elegida = monedaStore.use();
  const vigentes = pedido.items.filter((i) => i.estado !== "cancelado");
  const listos = vigentes.filter((i) => i.estado === "listo" || i.estado === "entregado").length;
  const abierta = pedido.estado === "abierta";
  const total = pedido.total_monedas.find((m) => m.moneda === elegida) ?? pedido.total_monedas.find((m) => m.monto === pedido.total) ?? pedido.total_monedas[0];
  const hayPendientes = pedido.items.some((i) => i.estado === "pendiente");

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-5 pb-36 pt-8">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span className="eyebrow">{pedido.sucursal}</span>
          <span className="text-lead text-fg-2">{pedido.mesa ? (/^\d+$/.test(pedido.mesa) ? `Mesa ${pedido.mesa}` : pedido.mesa) : "Para llevar"}</span>
        </div>
        {abierta && (
          <StatusDot tone={conexion === "en_vivo" ? "ok" : conexion === "reconectando" ? "warn" : "muted"}>
            {conexion === "en_vivo" ? "En vivo" : conexion === "reconectando" ? "Reconectando…" : "Conectando…"}
          </StatusDot>
        )}
      </header>

      <section aria-live="polite" className="flex flex-col gap-3 pb-12 pt-14">
        <motion.h1 key={titular(pedido, listos, vigentes.length)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={smooth} className="font-display text-display-l leading-[0.9]">
          {titular(pedido, listos, vigentes.length)}
        </motion.h1>
        {vigentes.length > 0 && abierta && (
          <p className="text-lead text-fg-2">
            <span className="font-display text-display-s text-fg tabular">
              {listos} de {vigentes.length}
            </span>{" "}
            {vigentes.length === 1 ? "plato listo" : "platos listos"}
          </p>
        )}
        {hayPendientes && abierta && (
          <>
            <p className="text-base text-fg-3">El mesero confirma tu pedido y lo pasa a cocina. Te avisamos aquí, no hace falta recargar.</p>
            <p className="border-l border-warn/60 pl-4 text-sm text-fg-2">
              Podemos escribirte o llamarte para confirmar. Si no respondes en 15 minutos, tu orden será cancelada.
            </p>
          </>
        )}
      </section>

      <ol aria-label="Tus platos" className="relative flex flex-col">
        {/* La línea de tiempo: un trazo fino que une los platos */}
        <span aria-hidden className="absolute bottom-6 left-[7px] top-6 w-px bg-line-strong" />
        {pedido.items.map((i) => (
          <PlatoNodo key={i.id} nombre={i.nombre} estado={i.estado} notas={i.notas} />
        ))}
      </ol>

      {total && (
        <section className="mt-12 flex flex-col gap-4 border-t border-line pt-6">
          <div className="flex items-baseline justify-between gap-4">
            <span className="eyebrow">Total</span>
            {pedido.total_monedas.length > 1 && (
              <Segmented
                label="Moneda"
                size="sm"
                value={total.moneda}
                onChange={(v) => monedaStore.set(() => v)}
                options={pedido.total_monedas.map((m) => ({ value: m.moneda, label: m.moneda }))}
              />
            )}
          </div>
          <Money value={total.monto} simbolo={total.simbolo} size="m" roll />
          <p className="text-sm text-fg-3">El pago se hace con el mesero o en caja.</p>
        </section>
      )}

      {abierta && <ChatMesa tracking={tracking} />}

      {abierta && (
        <div className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-2xl bg-canvas/70 px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 backdrop-blur-xl">
          <Link
            href={`/pedido/${tracking}/agregar`}
            className="flex h-14 items-center justify-center rounded-sheet border border-line-strong text-lead font-medium transition-colors hover:bg-wash"
          >
            Pedir algo más
          </Link>
        </div>
      )}
    </main>
  );
}

function PlatoNodo({ nombre, estado, notas }: { nombre: string; estado: EstadoItem; notas: string | null }) {
  // Cuenta los cambios de estado (estado derivado del render anterior, patrón de React)
  // para que el nodo "salte" cuando llega una actualización, pero no al cargar.
  const [previo, setPrevio] = useState(estado);
  const [cambios, setCambios] = useState(0);
  if (previo !== estado) {
    setPrevio(estado);
    setCambios((c) => c + 1);
  }
  const enMarcha = estado === "en_cocina" || estado === "preparando";

  return (
    <li className="relative flex items-start gap-5 py-4">
      <span className="relative z-10 mt-1.5 grid size-[15px] shrink-0 place-items-center rounded-full bg-canvas">
        <motion.span
          key={cambios}
          initial={cambios > 0 ? { scale: 1.8 } : false}
          animate={{ scale: 1 }}
          transition={snappy}
          className={cn(
            "block rounded-full",
            estado === "listo" && "size-[15px] bg-ok",
            estado === "entregado" && "size-[11px] bg-fg-3",
            estado === "preparando" && "size-[11px] animate-pulse bg-paper",
            estado === "en_cocina" && "size-[11px] border border-fg-2",
            estado === "pendiente" && "size-[11px] border border-line-strong",
            estado === "cancelado" && "size-[7px] bg-line-strong",
          )}
        />
        {enMarcha && <span aria-hidden className="absolute inset-0 animate-ping rounded-full border border-fg-4 [animation-duration:2.4s]" />}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className={cn("text-title font-medium", estado === "cancelado" && "text-fg-3 line-through decoration-1", estado === "entregado" && "text-fg-2")}>
          {nombre}
        </span>
        {notas && <span className="text-sm text-fg-3">“{notas}”</span>}
      </div>
      <span className="relative h-6 min-w-[9rem] text-right text-base">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={estado}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={smooth}
            className={cn("absolute right-0 whitespace-nowrap", estado === "listo" ? "font-medium text-ok" : "text-fg-2")}
          >
            {ETIQUETA[estado]}
          </motion.span>
        </AnimatePresence>
      </span>
    </li>
  );
}

function ChatMesa({ tracking }: { tracking: string }) {
  const { lista, enviar } = useChatPublico(tracking);
  return (
    <section className="mt-10 flex flex-col gap-3 border-t border-line pt-6">
      <h2 className="eyebrow">Chat con caja</h2>
      <ChatPanel
        mensajes={lista.data ?? []}
        yo="cliente"
        onEnviar={(t) => enviar.mutate(t)}
        enviando={enviar.isPending}
        vacio="¿Necesitas algo? Escríbele a caja desde aquí."
      />
    </section>
  );
}
