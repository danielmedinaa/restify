"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Money } from "@/components/ui/Money";
import { Segmented } from "@/components/ui/Segmented";
import { Sheet } from "@/components/ui/Sheet";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/Status";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { can, useMe } from "@/features/auth/useMe";
import { METODO } from "@/features/comandas/ComandaDetalle";
import { principalDe, useMonedas } from "@/features/comandas/queries";
import { useSucursal } from "@/features/panel/sucursal";
import { GraficoVentas } from "@/features/ventas/Grafico";
import { api } from "@/lib/api/client";
import { Pagina, ResumenVentasOut, VentaDetalleOut, VentaOut } from "@/lib/api/schemas";
import { isPositive, parseAmountInput } from "@/lib/money";

type Agrupar = "dia" | "mes" | "anio";
type Orden = "fecha_desc" | "fecha_asc" | "monto_desc" | "monto_asc";
type Facturacion = "todas" | "pendientes" | "facturadas";
const PAGINA = 50;
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const hora = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

/** Rango por defecto para cada agrupación: 30 días, 12 meses o todo. */
function rangoPorDefecto(a: Agrupar): { desde: string; hasta: string } {
  const hoy = new Date();
  if (a === "anio") return { desde: "", hasta: "" };
  const desde = new Date(hoy);
  if (a === "dia") desde.setDate(hoy.getDate() - 29);
  else desde.setMonth(hoy.getMonth() - 11, 1);
  return { desde: iso(desde), hasta: iso(hoy) };
}

function etiquetaPeriodo(p: string, a: Agrupar) {
  const [y, m, d] = p.split("-");
  if (a === "dia") return `${Number(d)} ${MESES[Number(m) - 1]}`;
  if (a === "mes") return `${MESES[Number(m) - 1]} ${y?.slice(2)}`;
  return p;
}

export default function VentasPage() {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const { data: monedas } = useMonedas(actual?.id);
  const simbolo = principalDe(monedas)?.simbolo;
  const [agrupar, setAgrupar] = useState<Agrupar>("dia");
  const [rango, setRango] = useState(() => rangoPorDefecto("dia"));
  const [montos, setMontos] = useState({ min: "", max: "" });
  const [orden, setOrden] = useState<Orden>("fecha_desc");
  const [offset, setOffset] = useState(0);
  const [detalle, setDetalle] = useState<number | null>(null);
  const [facturacion, setFacturacion] = useState<Facturacion>("todas");

  const filtros = {
    sucursal_id: actual?.id,
    fecha_desde: rango.desde || undefined,
    fecha_hasta: rango.hasta || undefined,
    monto_min: parseAmountInput(montos.min) ?? undefined,
    monto_max: parseAmountInput(montos.max) ?? undefined,
  };
  const facturada = facturacion === "todas" ? undefined : facturacion === "facturadas";
  // Libro de ventas: CSV con las facturas registradas en el rango elegido (descarga por el BFF)
  const libroQs = new URLSearchParams(
    Object.entries({ sucursal_id: actual?.id, fecha_desde: rango.desde, fecha_hasta: rango.hasta }).filter((e): e is [string, string | number] => !!e[1]).map(([k, v]) => [k, String(v)]),
  );
  const habilitado = !!actual && can(me, "ventas");
  const resumen = useQuery({
    queryKey: ["ventas", "resumen", agrupar, filtros],
    queryFn: () => api("/ventas/resumen", { query: { ...filtros, agrupar }, schema: ResumenVentasOut }),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  });
  const lista = useQuery({
    queryKey: ["ventas", "lista", filtros, orden, offset, facturada],
    queryFn: () => api("/ventas", { query: { ...filtros, facturada, ordenar: orden, limite: PAGINA, offset }, schema: Pagina(VentaOut) }),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  });

  if (!can(me, "ventas")) return <SinAcceso />;
  const r = resumen.data;
  const maxTop = Math.max(...(r?.productos_top.map((p) => p.cantidad) ?? [1]));

  return (
    <>
      <PageHeader
        eyebrow={actual?.nombre}
        title="Ventas"
        actions={
          <>
          <Link href="/panel/ventas/cierre" className="inline-flex h-9 items-center rounded-control px-3 text-sm text-fg-2 hover:bg-wash hover:text-fg">
            Cierre del día
          </Link>
          <Segmented
            label="Agrupar por"
            value={agrupar}
            onChange={(a) => {
              setAgrupar(a);
              setRango(rangoPorDefecto(a));
              setOffset(0);
            }}
            options={[
              { value: "dia", label: "Día" },
              { value: "mes", label: "Mes" },
              { value: "anio", label: "Año" },
            ]}
          />
          </>
        }
      />

      {/* Filtros en una fila, arriba de todo */}
      <div className="mb-12 flex flex-wrap items-end gap-6">
        {(
          [
            ["desde", "Desde"],
            ["hasta", "Hasta"],
          ] as const
        ).map(([k, label]) => (
          <label key={k} className="flex flex-col gap-1.5">
            <span className="eyebrow">{label}</span>
            <input
              type="date"
              value={rango[k]}
              onChange={(e) => {
                setRango((x) => ({ ...x, [k]: e.target.value }));
                setOffset(0);
              }}
              className="h-11 border-b border-line-strong bg-transparent text-base outline-none [color-scheme:dark] focus:border-paper"
            />
          </label>
        ))}
        {(
          [
            ["min", "Monto desde"],
            ["max", "Monto hasta"],
          ] as const
        ).map(([k, label]) => (
          <label key={k} className="flex flex-col gap-1.5">
            <span className="eyebrow">{label}</span>
            <input
              inputMode="decimal"
              value={montos[k]}
              onChange={(e) => {
                setMontos((x) => ({ ...x, [k]: e.target.value }));
                setOffset(0);
              }}
              placeholder={simbolo ?? "0"}
              className="h-11 w-32 border-b border-line-strong bg-transparent text-base tabular outline-none placeholder:text-fg-4 focus:border-paper"
            />
          </label>
        ))}
        {(rango.desde || rango.hasta || montos.min || montos.max) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setRango({ desde: "", hasta: "" });
              setMontos({ min: "", max: "" });
            }}
          >
            Quitar filtros
          </Button>
        )}
      </div>

      {resumen.isError ? (
        <ListError error={resumen.error} />
      ) : !r ? (
        <div className="flex flex-col gap-6">
          <Skeleton className="h-24 w-72" />
          <Skeleton className="h-56 w-full" />
        </div>
      ) : r.cantidad_ventas === 0 ? (
        <EmptyState title="Sin ventas" description="No hay ventas en este rango. Prueba con otras fechas o quita los filtros." />
      ) : (
        <div className="grid gap-16 desk:grid-cols-12">
          <div className="flex flex-col gap-10 desk:col-span-8">
            <div className="flex flex-wrap items-end gap-x-14 gap-y-6">
              <div className="flex flex-col gap-2">
                <span className="eyebrow">Vendido</span>
                <Money value={r.total} simbolo={simbolo} size="xl" />
              </div>
              <dl className="flex gap-10 pb-3">
                <div>
                  <dt className="text-sm text-fg-3">Ventas</dt>
                  <dd className="font-display text-display-s">{r.cantidad_ventas}</dd>
                </div>
                <div>
                  <dt className="text-sm text-fg-3">Ticket promedio</dt>
                  <dd>
                    <Money value={r.ticket_promedio} simbolo={simbolo} size="s" />
                  </dd>
                </div>
              </dl>
            </div>
            <GraficoVentas
              titulo={`Vendido por ${agrupar === "dia" ? "día" : agrupar === "mes" ? "mes" : "año"}`}
              simbolo={simbolo}
              barras={r.por_periodo.map((p) => ({ periodo: p.periodo, etiqueta: etiquetaPeriodo(p.periodo, agrupar), total: p.total, cantidad: p.cantidad_ventas }))}
            />
          </div>
          <section aria-labelledby="top-t" className="flex flex-col gap-4 desk:col-span-4">
            <h2 id="top-t" className="eyebrow">
              Lo más vendido
            </h2>
            <ol className="flex flex-col">
              {r.productos_top.map((p, i) => (
                <li key={p.producto} className="flex flex-col gap-2 border-t border-line py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="truncate text-base">
                      <span className="mr-2 tabular text-fg-3">{i + 1}</span>
                      {p.producto}
                    </span>
                    <span className="shrink-0 text-sm tabular text-fg-2">{p.cantidad} uds</span>
                  </div>
                  <span aria-hidden className="block h-px bg-line">
                    <span className="block h-full bg-fg-3" style={{ width: `${(p.cantidad / maxTop) * 100}%` }} />
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}

      <section aria-labelledby="detalle-t" className="mt-20 flex flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 id="detalle-t" className="font-display text-display-s">
            Cada venta
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <Segmented
              label="Facturación"
              size="sm"
              value={facturacion}
              onChange={(f) => {
                setFacturacion(f);
                setOffset(0);
              }}
              options={[
                { value: "todas", label: "Todas" },
                { value: "pendientes", label: "Por facturar" },
                { value: "facturadas", label: "Facturadas" },
              ]}
            />
            <Segmented
              label="Ordenar"
              size="sm"
              value={orden}
              onChange={(o) => {
                setOrden(o);
                setOffset(0);
              }}
              options={[
                { value: "fecha_desc", label: "Recientes" },
                { value: "fecha_asc", label: "Antiguas" },
                { value: "monto_desc", label: "Mayor monto" },
                { value: "monto_asc", label: "Menor monto" },
              ]}
            />
            {rango.desde || rango.hasta ? (
              <a href={`/bff/panel/ventas/libro?${libroQs}`} download className="inline-flex h-8 items-center rounded-control px-3 text-sm text-fg-2 hover:bg-wash hover:text-fg">
                Libro de ventas ↓
              </a>
            ) : (
              <span className="px-3 text-sm text-fg-4" title="Elige un rango de fechas para descargar el libro">
                Libro de ventas
              </span>
            )}
          </div>
        </div>
        {lista.isPending ? (
          <ListLoading />
        ) : lista.isError ? (
          <ListError error={lista.error} />
        ) : lista.data.items.length === 0 ? (
          facturacion !== "todas" && (
            <EmptyState
              title={facturacion === "pendientes" ? "Todo facturado" : "Sin facturas registradas"}
              description={facturacion === "pendientes" ? "No quedan ventas pendientes por facturar en este rango." : "Registra el número de factura desde el detalle de cada venta."}
            />
          )
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Venta</Th>
                  <Th>Cuándo</Th>
                  <Th>Mesa / cliente</Th>
                  <Th align="right">Platos</Th>
                  <Th>Factura</Th>
                  <Th align="right">Total</Th>
                </tr>
              </thead>
              <tbody>
                {lista.data.items.map((v) => (
                  <Tr key={v.id} className="cursor-pointer" onClick={() => setDetalle(v.id)}>
                    <Td>
                      <button type="button" onClick={() => setDetalle(v.id)} className="font-medium hover:underline">
                        #{v.id}
                      </button>
                    </Td>
                    <Td className="text-sm text-fg-2">{hora.format(new Date(v.created_at))}</Td>
                    <Td className="text-fg-2">{[v.mesa ? (/^\d+$/.test(v.mesa) ? `Mesa ${v.mesa}` : v.mesa) : "Para llevar", v.nombre_cliente].filter(Boolean).join(" · ")}</Td>
                    <Td align="right">{v.cantidad_items}</Td>
                    <Td>{v.anulada_en ? <StatusDot tone="err">Anulada · N° {v.numero_factura}</StatusDot> : v.numero_factura ? <span className="tabular text-fg-2">N° {v.numero_factura}</span> : <StatusDot tone="warn">Pendiente</StatusDot>}</Td>
                    <Td align="right">
                      <Money value={v.total} simbolo={simbolo} />
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            {lista.data.total > PAGINA && (
              <div className="flex items-center justify-between text-sm text-fg-3">
                <span>
                  {offset + 1}–{Math.min(offset + PAGINA, lista.data.total)} de {lista.data.total}
                </span>
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGINA))}>
                    Anteriores
                  </Button>
                  <Button size="sm" variant="ghost" disabled={offset + PAGINA >= lista.data.total} onClick={() => setOffset((o) => o + PAGINA)}>
                    Siguientes
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      <DetalleVenta id={detalle} onClose={() => setDetalle(null)} simbolo={simbolo} />
    </>
  );
}

function DetalleVenta({ id, onClose, simbolo }: { id: number | null; onClose: () => void; simbolo?: string }) {
  const [ultimo, setUltimo] = useState(id);
  if (id !== null && id !== ultimo) setUltimo(id);
  const vid = id ?? ultimo;
  const venta = useQuery({ queryKey: ["ventas", "detalle", vid], queryFn: () => api(`/ventas/${vid}`, { schema: VentaDetalleOut }), enabled: id !== null });
  const v = venta.data;
  const platos = v?.comanda.items.filter((i) => i.estado === "entregado" || i.estado === "listo") ?? [];
  return (
    <Sheet
      open={id !== null}
      onOpenChange={(o) => !o && onClose()}
      side="right"
      title={vid ? `Venta #${vid}` : "Venta"}
      description={v ? `${hora.format(new Date(v.created_at))} · ${v.mesa ? (/^\d+$/.test(v.mesa) ? `Mesa ${v.mesa}` : v.mesa) : "Para llevar"}${v.nombre_cliente ? ` · ${v.nombre_cliente}` : ""}` : undefined}
    >
      {!v ? (
        <ListLoading rows={4} />
      ) : (
        <div className="flex flex-col gap-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <Money value={v.total} simbolo={simbolo} size="l" />
            <Link href={`/panel/ventas/${v.id}/factura`} className="inline-flex h-10 items-center rounded-control bg-paper px-4 text-base text-ink hover:bg-paper/90">
              {v.numero_factura ? `Factura N° ${v.numero_factura}` : "Datos para facturar"}
            </Link>
          </div>
          <section className="flex flex-col">
            <h3 className="eyebrow pb-2">Platos · {platos.length}</h3>
            {platos.map((i) => (
              <div key={i.id} className="flex items-baseline justify-between gap-4 border-t border-line py-3">
                <span className="flex flex-col">
                  <span className="text-base">{i.nombre}</span>
                  {i.notas && <span className="text-sm text-fg-3">“{i.notas}”</span>}
                </span>
                <Money value={i.precio_unitario} simbolo={simbolo} className="text-fg-2" />
              </div>
            ))}
          </section>
          <section className="flex flex-col">
            <h3 className="eyebrow pb-2">Pagos</h3>
            {v.comanda.pagos.map((p) => (
              <div key={p.id} className="flex items-baseline justify-between gap-4 border-t border-line py-3">
                <span className="flex flex-col">
                  <span className="text-base">{METODO[p.metodo]}</span>
                  <span className="text-sm text-fg-3">{[p.etiqueta, p.referencia].filter(Boolean).join(" · ") || " "}</span>
                </span>
                <span className="text-right">
                  <span className="block tabular">
                    {p.moneda} {p.monto}
                  </span>
                  <span className="text-sm text-fg-3">tasa {p.tasa.replace(/0+$/, "").replace(/\.$/, "")}</span>
                </span>
              </div>
            ))}
            {isPositive(v.vuelto) && (
              <p className="border-t border-line pt-3 text-sm text-fg-2">
                Vuelto <Money value={v.vuelto} simbolo={simbolo} />
              </p>
            )}
          </section>
        </div>
      )}
    </Sheet>
  );
}
