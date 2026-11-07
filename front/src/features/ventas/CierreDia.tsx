"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ListError, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { can, useMe } from "@/features/auth/useMe";
import { METODO } from "@/features/comandas/ComandaDetalle";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import { CierreDiaOut, type CierreDia as Cierre } from "@/lib/api/schemas";
import { formatAmount } from "@/lib/money";

const sinSuscripcion = () => () => {};
const hoy = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD en la hora local del equipo
const fechaLarga = new Intl.DateTimeFormat("es-VE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

/** Resumen del día para imprimir al cerrar: ventas, IVA por alícuota, IGTF, métodos de pago y pendientes. */
export function CierreDia() {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const [dia, setDia] = useState(hoy);
  const montado = useSyncExternalStore(sinSuscripcion, () => true, () => false);
  const cierre = useQuery({
    queryKey: ["ventas", "cierre", actual?.id, dia],
    queryFn: () => api("/ventas/cierre-dia", { query: { dia, sucursal_id: actual?.id }, schema: CierreDiaOut }),
    enabled: !!actual && !!dia && can(me, "ventas"),
  });
  if (!can(me, "ventas")) return <SinAcceso />;
  const c = cierre.data;

  return (
    <>
      <PageHeader
        eyebrow={
          <Link href="/panel/ventas" className="hover:text-fg">
            ← Ventas
          </Link>
        }
        title="Cierre del día"
        actions={
          <>
            <input
              type="date"
              value={dia}
              max={hoy()}
              onChange={(e) => e.target.value && setDia(e.target.value)}
              aria-label="Día"
              className="h-10 rounded-control bg-wash px-3 text-base text-fg outline-none [color-scheme:dark]"
            />
            <Button onClick={() => window.print()} disabled={!c}>
              Imprimir
            </Button>
          </>
        }
      />
      {cierre.isError ? (
        <ListError error={cierre.error} />
      ) : !c ? (
        <Skeleton className="h-[30rem] w-full max-w-[190mm]" />
      ) : (
        <div className="flex justify-center rounded-sheet bg-wash/60 px-4 py-10">
          <div className="shadow-[0_30px_80px_-30px_rgba(0,0,0,0.7)]">
            <Papel c={c} />
          </div>
        </div>
      )}
      {montado &&
        c &&
        createPortal(
          <div className="print-portal" data-formato="carta">
            <Papel c={c} />
          </div>,
          document.body,
        )}
    </>
  );
}

function Papel({ c }: { c: Cierre }) {
  const m = (v: string) => formatAmount(v);
  const fecha = fechaLarga.format(new Date(`${c.dia}T12:00:00`));
  return (
    <article className="doc-fiscal w-full max-w-[190mm] bg-[#ffffff] p-[12mm] text-[12.5px] leading-normal text-[#1a1819] [font-feature-settings:'tnum']">
      <p className="mb-6 border border-[#1a1819] py-1.5 text-center text-[11px] font-semibold uppercase tracking-[0.06em]">{c.leyenda}</p>
      <header className="mb-6">
        <h2 className="font-display text-[28px] leading-none">Cierre del día</h2>
        <p className="mt-2 font-semibold">{c.emisor.razon_social ?? c.emisor.nombre_comercial}</p>
        <p>RIF {c.emisor.rif ?? "—"} · {c.sucursal}</p>
        <p className="capitalize text-[#55504f]">{fecha}</p>
      </header>

      <Bloque titulo="Ventas">
        <Fila a="Ventas del día" b={String(c.ventas)} />
        <Fila a={`Total con IVA (${c.moneda})`} b={m(c.total)} fuerte />
        {Number(c.exento) > 0 && <Fila a="Ventas exentas" b={m(c.exento)} />}
        {c.iva.map((r) => (
          <div key={r.etiqueta} className="mt-1">
            <Fila a={`Base imponible · ${r.etiqueta}`} b={m(r.base_imponible)} />
            <Fila a={`IVA ${Number(r.alicuota_iva)} %`} b={m(r.iva)} />
          </div>
        ))}
        {Number(c.igtf) > 0 && <Fila a="IGTF cobrado" b={m(c.igtf)} />}
        {Number(c.descuentos) > 0 && <Fila a="Descuentos otorgados" b={`-${m(c.descuentos)}`} />}
        {Number(c.propinas) > 0 && <Fila a="Propinas (no son venta)" b={m(c.propinas)} />}
      </Bloque>

      <Bloque titulo={`Cobros por método (${c.moneda})`}>
        {c.por_metodo.length === 0 ? <p className="text-[#55504f]">Sin cobros.</p> : c.por_metodo.map((x) => <Fila key={x.metodo} a={METODO[x.metodo as keyof typeof METODO] ?? x.metodo} b={m(x.monto)} />)}
      </Bloque>

      <Bloque titulo="Facturación">
        <Fila a="Ventas facturadas" b={String(c.facturadas)} />
        <Fila a="Pendientes por facturar" b={String(c.pendientes_facturar)} fuerte={c.pendientes_facturar > 0} />
        <Fila a="Facturas anuladas (nota de crédito)" b={`${c.anuladas}${c.anuladas ? ` · ${m(c.anuladas_total)}` : ""}`} />
        {c.cortesias > 0 && <Fila a="Platos de cortesía" b={String(c.cortesias)} />}
      </Bloque>

      <footer className="mt-10 grid grid-cols-2 gap-12 text-center text-[11px] text-[#55504f]">
        <p className="border-t border-[#1a1819] pt-1">Cajero</p>
        <p className="border-t border-[#1a1819] pt-1">Supervisor</p>
      </footer>
    </article>
  );
}

function Bloque({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="mb-5 border-t border-dashed border-[#1a1819]/60 pt-3">
      <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#55504f]">{titulo}</h3>
      <div className="flex flex-col gap-0.5">{children}</div>
    </section>
  );
}

function Fila({ a, b, fuerte }: { a: string; b: string; fuerte?: boolean }) {
  return (
    <p className={`flex justify-between gap-6 ${fuerte ? "font-semibold" : ""}`}>
      <span>{a}</span>
      <span>{b}</span>
    </p>
  );
}
