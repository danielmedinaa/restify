import type { DatosFiscales, MontoFiscal } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { formatAmount } from "@/lib/money";

export type Formato = "ticket" | "carta";

const fechaHora = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

/**
 * Documento para facturar a mano: el restaurante copia estos datos en su talonario
 * o máquina fiscal. Siempre negro sobre blanco (es papel), en pantalla y al imprimir.
 */
export function Documento({ d, formato, simbolos }: { d: DatosFiscales; formato: Formato; simbolos: Record<string, string> }) {
  // La factura se expresa en bolívares; si no hay moneda fiscal configurada, en la principal
  const enFiscal = d.moneda_fiscal !== null;
  const codigo = enFiscal ? d.moneda_fiscal! : d.moneda_principal;
  const sim = simbolos[codigo] ?? codigo;
  const m = (v: MontoFiscal) => formatAmount((enFiscal ? v.fiscal : v.principal) ?? v.principal);
  const ticket = formato === "ticket";
  const gravados = d.resumen_iva.filter((r) => Number(r.alicuota_iva) > 0);
  const hayExento = Number(d.exento.principal) > 0;
  const tasa = d.tasa_fiscal ? formatAmount(d.tasa_fiscal, Math.max(2, (d.tasa_fiscal.split(".")[1] ?? "").replace(/0+$/, "").length)) : null;

  return (
    <article
      className={cn(
        "doc-fiscal bg-[#ffffff] text-[#1a1819] [font-feature-settings:'tnum']",
        ticket ? "w-[72mm] px-1 py-2 text-[11.5px] leading-snug" : "w-full max-w-[190mm] p-[12mm] text-[12.5px] leading-normal",
      )}
    >
      {d.anulada_en && (
        <p className={cn("border-2 border-[#1a1819] text-center font-bold uppercase tracking-[0.1em]", ticket ? "mb-3 px-1 py-1 text-[12px]" : "mb-4 py-2 text-[14px]")}>
          Factura anulada · Nota de crédito N° {d.nota_credito_numero}
        </p>
      )}
      <p className={cn("border border-[#1a1819] text-center font-semibold uppercase tracking-[0.06em]", ticket ? "mb-3 px-1 py-1 text-[10px]" : "mb-6 py-1.5 text-[11px]")}>
        {d.leyenda}
      </p>

      {/* Emisor */}
      <header className={cn(ticket ? "mb-3 text-center" : "mb-8 flex items-start justify-between gap-8")}>
        <div className={cn(ticket ? "" : "max-w-[60%]")}>
          <h2 className={cn("font-display leading-none", ticket ? "mb-1 text-[20px]" : "mb-2 text-[30px]")}>{d.emisor.nombre_comercial}</h2>
          <p className="font-semibold">{d.emisor.razon_social ?? "Razón social sin cargar"}</p>
          <p>RIF {d.emisor.rif ?? "—"}</p>
          {d.emisor.domicilio_fiscal && <p className="text-[#55504f]">{d.emisor.domicilio_fiscal}</p>}
          {d.emisor.telefono && <p className="text-[#55504f]">Tel. {d.emisor.telefono}</p>}
        </div>
        <dl className={cn(ticket ? "mt-2 flex justify-center gap-3 text-[#55504f]" : "grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5 text-right")}>
          <Dato label="Venta" ticket={ticket}>#{d.venta_id}</Dato>
          <Dato label="Fecha" ticket={ticket}>{fechaHora.format(new Date(d.fecha))}</Dato>
          {d.mesa && <Dato label="Mesa" ticket={ticket}>{/^\d+$/.test(d.mesa) ? `Mesa ${d.mesa}` : d.mesa}</Dato>}
        </dl>
      </header>

      {/* Receptor */}
      <section className={cn("border-y border-dashed border-[#1a1819]/60", ticket ? "mb-3 py-2" : "mb-6 py-3")}>
        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#55504f]">Cliente</p>
        {d.receptor.consumidor_final ? (
          <p className="font-semibold">{d.receptor.razon_social ? `${d.receptor.razon_social} · ` : ""}Consumidor final</p>
        ) : (
          <>
            <p className="font-semibold">{d.receptor.razon_social}</p>
            <p>RIF / C.I. {d.receptor.rif}</p>
            {d.receptor.domicilio && <p className="text-[#55504f]">{d.receptor.domicilio}</p>}
          </>
        )}
      </section>

      {/* Líneas */}
      <table className={cn("w-full border-collapse", ticket ? "mb-3" : "mb-6")}>
        <thead>
          <tr className="border-b border-[#1a1819] text-[10px] uppercase tracking-[0.06em] text-[#55504f]">
            <th className="py-1 pr-2 text-left font-semibold">Cant.</th>
            <th className="py-1 pr-2 text-left font-semibold">Descripción</th>
            {!ticket && <th className="py-1 pr-2 text-right font-semibold">P. unit.</th>}
            <th className="py-1 text-right font-semibold">Total {codigo}</th>
          </tr>
        </thead>
        <tbody>
          {d.lineas.map((l) => (
            <tr key={`${l.descripcion}-${l.precio_unitario.principal}-${l.alicuota_iva}`} className="border-b border-[#1a1819]/15 align-top">
              <td className="py-1 pr-2">{l.cantidad}</td>
              <td className="py-1 pr-2">
                {l.descripcion}
                {l.exento && <span className="ml-1 font-semibold">(E)</span>}
                {ticket && l.cantidad > 1 && <span className="block text-[#55504f]">{`${l.cantidad} × ${m(l.precio_unitario)}`}</span>}
              </td>
              {!ticket && <td className="py-1 pr-2 text-right">{m(l.precio_unitario)}</td>}
              <td className="py-1 text-right">{m(l.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Totales */}
      <div className={cn(ticket ? "" : "ml-auto w-[80mm]")}>
        <dl className="flex flex-col gap-0.5">
          {hayExento && <Linea label="Exento (E)" valor={`${sim} ${m(d.exento)}`} />}
          {gravados.map((r) => (
            <div key={r.alicuota_iva} className="contents">
              <Linea label={`Base imponible ${Number(r.alicuota_iva)} %`} valor={`${sim} ${m(r.base_imponible)}`} />
              <Linea label={`IVA ${Number(r.alicuota_iva)} %`} valor={`${sim} ${m(r.iva)}`} />
            </div>
          ))}
          <Linea label="Total" valor={`${sim} ${m(d.total)}`} fuerte />
          {d.igtf && Number(d.igtf.monto.principal) > 0 && (
            <>
              <Linea label={`IGTF ${Number(d.igtf.porcentaje)} % s/ ${sim} ${m(d.igtf.base)}`} valor={`${sim} ${m(d.igtf.monto)}`} />
              <Linea label="Total a pagar" valor={`${sim} ${m(d.total_a_pagar)}`} fuerte />
            </>
          )}
        </dl>
        {enFiscal && tasa && d.moneda_fiscal !== d.moneda_principal && (
          <p className="mt-2 text-right text-[#55504f]">
            {`Equivale a ${simbolos[d.moneda_principal] ?? d.moneda_principal} ${formatAmount(d.total_a_pagar.principal)} · tasa ${tasa}`}
            {d.tasa_es_actual && " (de hoy)"}
          </p>
        )}
      </div>

      {/* Pagos */}
      {d.pagos.length > 0 && (
        <section className={cn("border-t border-dashed border-[#1a1819]/60", ticket ? "mt-3 pt-2" : "mt-6 pt-3")}>
          <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#55504f]">Forma de pago</p>
          {d.pagos.map((p, i) => (
            <p key={i} className="flex justify-between gap-3">
              <span>
                {METODO_PAGO[p.metodo] ?? p.metodo}
                {p.es_divisa && " (divisa)"}
                {p.referencia && <span className="text-[#55504f]"> · Ref. {p.referencia}</span>}
              </span>
              <span>{`${simbolos[p.moneda] ?? p.moneda} ${formatAmount(p.monto)}`}</span>
            </p>
          ))}
        </section>
      )}

      {d.numero_factura && (
        <p className={cn("border-t border-[#1a1819] font-semibold", ticket ? "mt-3 pt-2 text-center" : "mt-6 pt-3")}>
          {`Factura N° ${d.numero_factura} · Control N° ${d.numero_control}`}
        </p>
      )}
      <p className={cn("text-center text-[10px] uppercase tracking-[0.06em] text-[#55504f]", ticket ? "mt-3" : "mt-8")}>{d.leyenda}</p>
    </article>
  );
}

const METODO_PAGO: Record<string, string> = {
  efectivo: "Efectivo",
  tarjeta: "Tarjeta",
  transferencia: "Transferencia",
  pago_movil: "Pago móvil",
  otro: "Otro",
};

function Dato({ label, children, ticket }: { label: string; children: React.ReactNode; ticket: boolean }) {
  if (ticket)
    return (
      <div>
        <dt className="sr-only">{label}</dt>
        <dd>{children}</dd>
      </div>
    );
  return (
    <>
      <dt className="text-[#55504f]">{label}</dt>
      <dd className="font-semibold">{children}</dd>
    </>
  );
}

function Linea({ label, valor, fuerte }: { label: string; valor: string; fuerte?: boolean }) {
  return (
    <div className={cn("flex justify-between gap-4", fuerte && "mt-1 border-t border-[#1a1819] pt-1 text-[1.15em] font-semibold")}>
      <dt>{label}</dt>
      <dd className="whitespace-nowrap">{valor}</dd>
    </div>
  );
}
