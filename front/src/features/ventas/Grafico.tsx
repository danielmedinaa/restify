"use client";

import { useState } from "react";
import { formatAmount } from "@/lib/money";

export interface Barra {
  periodo: string;
  etiqueta: string;
  total: string;
  cantidad: number;
}

const ALTO = 220;
const PIE = 28;
const GAP = 2;
/** Espacios mínimos: con pocos periodos las barras siguen finas en vez de llenar todo. */
const MIN_SLOTS = 12;

/**
 * Barras de una sola serie (ventas por periodo). Sin leyenda: el título la
 * nombra. Ejes recesivos, puntas redondeadas ancladas a la base, tooltip por
 * barra y una tabla equivalente para lectores de pantalla.
 * Los números en pantalla salen tal cual del backend; float solo para dibujar.
 */
export function GraficoVentas({ barras, simbolo, titulo }: { barras: Barra[]; simbolo?: string; titulo: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...barras.map((b) => Number(b.total)), 0);
  const tope = max > 0 ? escalaBonita(max) : 1;
  const ancho = 100 / Math.max(barras.length, MIN_SLOTS);
  const marcas = [0, 0.5, 1].map((f) => tope * f);
  const activa = hover !== null ? barras[hover] : null;
  const etiquetas = barras.length <= 12 ? 1 : Math.ceil(barras.length / 8);

  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="eyebrow">{titulo}</figcaption>
      <div className="relative mt-6" style={{ height: ALTO + PIE }} onPointerLeave={() => setHover(null)}>
        {/* Grilla recesiva con tres marcas */}
        {marcas.map((m) => (
          <div key={m} aria-hidden className="absolute inset-x-0 flex items-end gap-2 border-t border-line" style={{ bottom: PIE + (m / tope) * ALTO }}>
            <span className="ml-auto -translate-y-full pb-1 text-sm tabular text-fg-3">{formatAmount(String(Math.round(m)), 0)}</span>
          </div>
        ))}
        <svg aria-hidden className="absolute inset-x-0 top-0 h-full w-full overflow-visible" viewBox={`0 0 100 ${ALTO + PIE}`} preserveAspectRatio="none">
          {barras.map((b, i) => {
            const h = tope > 0 ? (Number(b.total) / tope) * ALTO : 0;
            const x = i * ancho;
            return (
              <rect
                key={b.periodo}
                x={x + GAP / 4}
                y={ALTO - h}
                width={Math.max(ancho - GAP / 2, 0.4)}
                height={Math.max(h, 0)}
                rx={0.6}
                className={hover === null || hover === i ? "fill-fg-2 transition-[fill]" : "fill-fg-4 transition-[fill]"}
              />
            );
          })}
        </svg>
        {/* Zonas de hover más anchas que la barra */}
        <div className="absolute inset-x-0 top-0 flex" style={{ height: ALTO }}>
          {barras.map((b, i) => (
            <div key={b.periodo} className="h-full shrink-0" style={{ width: `${ancho}%` }} onPointerEnter={() => setHover(i)} />
          ))}
        </div>
        <div aria-hidden className="absolute inset-x-0 bottom-0 flex" style={{ height: PIE }}>
          {barras.map((b, i) => (
            <span key={b.periodo} className="shrink-0 truncate pt-2 text-center text-sm text-fg-3" style={{ width: `${ancho}%` }}>
              {i % etiquetas === 0 ? b.etiqueta : ""}
            </span>
          ))}
        </div>
        {activa && hover !== null && (
          <div
            role="status"
            className="pointer-events-none absolute z-10 flex -translate-x-1/2 flex-col gap-0.5 rounded-control bg-overlay/95 px-3 py-2 text-sm shadow-float backdrop-blur-xl"
            style={{ left: `${Math.min(92, Math.max(8, (hover + 0.5) * ancho))}%`, top: 0 }}
          >
            <span className="text-fg-3">{activa.etiqueta}</span>
            <span className="font-medium tabular">
              {simbolo} {formatAmount(activa.total)}
            </span>
            <span className="text-fg-3">
              {activa.cantidad} {activa.cantidad === 1 ? "venta" : "ventas"}
            </span>
          </div>
        )}
      </div>
      <table className="sr-only">
        <caption>{titulo}</caption>
        <thead>
          <tr>
            <th>Periodo</th>
            <th>Total</th>
            <th>Ventas</th>
          </tr>
        </thead>
        <tbody>
          {barras.map((b) => (
            <tr key={b.periodo}>
              <td>{b.etiqueta}</td>
              <td>
                {simbolo} {formatAmount(b.total)}
              </td>
              <td>{b.cantidad}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** Tope del eje: 1, 2 o 5 por la potencia de 10 que cubra el máximo. */
function escalaBonita(max: number): number {
  const p = 10 ** Math.floor(Math.log10(max));
  for (const m of [1, 2, 5, 10]) if (m * p >= max) return m * p;
  return 10 * p;
}
