"use client";

import { useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import type { Comanda } from "@/lib/api/schemas";
import { formatAmount, isPositive } from "@/lib/money";

const sinSuscripcion = () => () => {};
const fechaHora = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

/**
 * Tickets de 80 mm que se imprimen con el diálogo del navegador (impresora térmica o la que
 * sea). Se montan fuera del layout y solo se ven al imprimir (.print-portal en globals.css).
 * Para imprimir sin diálogo en cocina: Chrome con --kiosk-printing.
 */
export function TicketPortal({ children }: { children: React.ReactNode }) {
  const montado = useSyncExternalStore(sinSuscripcion, () => true, () => false);
  if (!montado) return null;
  return createPortal(<div className="print-portal" data-formato="ticket">{children}</div>, document.body);
}

const linea = "flex justify-between gap-3";

/** Pre-cuenta para el cliente: lo consumido y el total, sin validez fiscal. */
export function PreCuenta({ c, simbolo, sucursal }: { c: Comanda; simbolo: string; sucursal?: string }) {
  const vigentes = c.items.filter((i) => i.estado !== "cancelado");
  const t = c.totales;
  return (
    <article className="doc-fiscal w-[72mm] bg-white px-1 py-2 text-[12px] leading-snug text-[#1a1819] [font-feature-settings:'tnum']">
      <p className="text-center font-display text-[20px] leading-none">{sucursal ?? "RESTIFY"}</p>
      <p className="mt-1 text-center text-[10px] uppercase tracking-[0.06em]">Pre-cuenta · no es factura</p>
      <p className="mt-2 border-y border-dashed border-[#1a1819]/60 py-1 text-center">
        {c.mesa ? (/^\d+$/.test(c.mesa) ? `Mesa ${c.mesa}` : c.mesa) : "Para llevar"} · Comanda #{c.id} · {fechaHora.format(new Date())}
      </p>
      <ul className="my-2 flex flex-col gap-0.5">
        {vigentes.map((i) => (
          <li key={i.id} className={linea}>
            <span>
              {i.nombre}
              {i.cortesia && " (cortesía)"}
            </span>
            <span>{i.cortesia ? "0,00" : formatAmount(i.precio_unitario)}</span>
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-0.5 border-t border-[#1a1819] pt-1">
        <p className={linea}>
          <span>Subtotal</span>
          <span>{formatAmount(t.subtotal)}</span>
        </p>
        {isPositive(t.descuento) && (
          <p className={linea}>
            <span>Descuento</span>
            <span>-{formatAmount(t.descuento)}</span>
          </p>
        )}
        {isPositive(t.propina) && (
          <p className={linea}>
            <span>Propina</span>
            <span>{formatAmount(t.propina)}</span>
          </p>
        )}
        <p className={`${linea} mt-1 text-[15px] font-semibold`}>
          <span>Total</span>
          <span>
            {simbolo} {formatAmount(t.total)}
          </span>
        </p>
        {t.total_monedas
          .filter((m) => m.simbolo !== simbolo)
          .map((m) => (
            <p key={m.moneda} className={linea}>
              <span>En {m.moneda}</span>
              <span>
                {m.simbolo} {formatAmount(m.monto)}
              </span>
            </p>
          ))}
      </div>
      {c.igtf_porcentaje && <p className="mt-2 text-center text-[10px]">Pagos en divisas: + IGTF {Number(c.igtf_porcentaje)} %</p>}
      <p className="mt-2 text-center text-[10px] uppercase tracking-[0.06em]">Gracias por su visita</p>
    </article>
  );
}

/** Comanda para cocina: platos con su nota, en letra grande. */
export function TicketCocina({ comandaId, mesa, nombreCliente, notas, items }: { comandaId: number; mesa: string | null; nombreCliente: string | null; notas: string | null; items: { id: number; nombre: string; notas: string | null }[] }) {
  return (
    <article className="doc-fiscal w-[72mm] bg-white px-1 py-2 text-[14px] leading-snug text-[#1a1819]">
      <p className="font-display text-[26px] leading-none">{mesa ? (/^\d+$/.test(mesa) ? `Mesa ${mesa}` : mesa) : "Para llevar"}</p>
      <p className="mt-1 text-[11px]">
        Comanda #{comandaId}
        {nombreCliente && ` · ${nombreCliente}`} · {fechaHora.format(new Date())}
      </p>
      {notas && <p className="mt-1 border border-[#1a1819] px-1 text-[12px] font-semibold">{notas}</p>}
      <ul className="mt-2 flex flex-col gap-1 border-t border-dashed border-[#1a1819]/60 pt-2">
        {items.map((i) => (
          <li key={i.id}>
            <span className="font-semibold">☐ {i.nombre}</span>
            {i.notas && <span className="block pl-4 text-[13px] italic">→ {i.notas}</span>}
          </li>
        ))}
      </ul>
    </article>
  );
}
