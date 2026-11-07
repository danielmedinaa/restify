"use client";

import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Money } from "@/components/ui/Money";
import { MoneyInput } from "@/components/ui/MoneyInput";
import { Segmented } from "@/components/ui/Segmented";
import { Loading, Skeleton } from "@/components/ui/Skeleton";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { METODO } from "@/features/comandas/ComandaDetalle";
import { tituloComanda } from "@/features/comandas/estado";
import { principalDe, useComanda, useComandaAction, useMonedas } from "@/features/comandas/queries";
import { describeError, type ErrorView } from "@/lib/api/errors";
import type { Comanda, MetodoPago, Moneda } from "@/lib/api/schemas";
import { abonoConIgtf, coverIn, cubrirConIgtf, fromPrincipal, isPositive, minus, remaining, toPrincipal } from "@/lib/money";
import { Ajuste } from "./Ajuste";
import { PreCuenta, TicketPortal } from "./Ticket";
import { useTurnoActual } from "./turno";

const METODOS = Object.entries(METODO).map(([value, label]) => ({ value: value as MetodoPago, label }));

export function Caja({ id }: { id: number }) {
  const comanda = useComanda(id);
  const monedas = useMonedas(comanda.data?.sucursal_id);
  if (comanda.isPending || (monedas.isPending && !monedas.data)) {
    return (
      <Loading label="Cargando caja">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="mt-4 h-14 w-48" />
        <Skeleton className="mt-16 h-24 w-72" />
      </Loading>
    );
  }
  if (comanda.isError) {
    const e = describeError(comanda.error);
    return <EmptyState title={e.title} description={e.description ?? ""} />;
  }
  return <CajaComanda c={comanda.data} monedas={monedas.data ?? []} />;
}

function CajaComanda({ c, monedas }: { c: Comanda; monedas: Moneda[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const { data: me } = useMe();
  const principal = principalDe(monedas);
  const etiquetaInicial = params.get("etiqueta") ?? "";
  // Si se vino a cobrar una parte desde Dividir, al registrar el pago se vuelve allá
  const desdeDividir = params.get("volver") === "dividir";

  const [monedaId, setMonedaId] = useState<number | null>(principal?.id ?? null);
  // undefined = sin tocar (vale el prellenado); null = el usuario lo dejó vacío o inválido
  const [monto, setMonto] = useState<string | null | undefined>(undefined);
  const [inputKey, setInputKey] = useState(0);
  const [inicial, setInicial] = useState(params.get("monto") ?? "");
  const [metodo, setMetodo] = useState<MetodoPago>("efectivo");
  const [referencia, setReferencia] = useState("");
  const [etiqueta, setEtiqueta] = useState(etiquetaInicial);
  const [error, setError] = useState<ErrorView | null>(null);
  const cerrarRef = useRef<HTMLButtonElement>(null);

  const moneda = monedas.find((m) => m.id === monedaId) ?? principal;
  // En divisas, si la sucursal cobra IGTF, el pago lleva el impuesto incluido
  const pctIgtf = moneda?.es_divisa ? c.igtf_porcentaje : null;
  const turno = useTurnoActual(c.sucursal_id);
  const [ajuste, setAjuste] = useState<"descuento" | "propina" | null>(null);
  const simbolo = principal?.simbolo ?? c.totales.total_monedas.find((m) => m.monto === c.totales.total)?.simbolo;
  const montoEfectivo = monto === undefined ? inicial || null : monto;

  // Vista previa exacta (big.js, mismo redondeo que el backend). El backend confirma al registrar.
  const preview = useMemo(() => {
    if (!moneda || !montoEfectivo) return { falta: c.totales.pendiente, vuelto: null as string | null };
    const pagado = toPrincipal(montoEfectivo, moneda.tasa, moneda.operacion);
    const enPrincipal = pctIgtf ? abonoConIgtf(pagado, pctIgtf) : pagado;
    const diff = minus(enPrincipal, c.totales.pendiente);
    return { falta: remaining(c.totales.pendiente, enPrincipal), vuelto: isPositive(diff) ? diff : null };
  }, [moneda, montoEfectivo, c.totales.pendiente, pctIgtf]);
  // Lo que hay que recibir en la moneda elegida para cubrir lo pendiente (con IGTF si aplica)
  const exactoEn = moneda ? coverIn(pctIgtf ? cubrirConIgtf(c.totales.pendiente, pctIgtf) : c.totales.pendiente, moneda.tasa, moneda.operacion) : null;

  // Vuelto: el de la vista previa mientras se escribe, o el ya registrado si se pagó de más
  const vuelto = preview.vuelto ?? (isPositive(c.totales.vuelto) ? c.totales.vuelto : null);

  const abierta = c.estado === "abierta";
  const puedeCobrar = abierta && can(me, "caja", "crear");
  const puedeCerrar = abierta && can(me, "caja", "editar");
  const hayPendiente = isPositive(c.totales.pendiente);

  const pagar = useComandaAction<void>(
    c.id,
    () => ({
      path: "/pagos",
      body: {
        moneda_id: moneda?.id,
        monto: montoEfectivo,
        metodo,
        referencia: referencia.trim() || null,
        etiqueta: etiqueta.trim() || null,
      },
    }),
    {
      onSuccess: (nueva) => {
        toast({ title: "Pago registrado", description: `${moneda?.simbolo ?? ""} ${montoEfectivo} · ${METODO[metodo]}`, tone: "ok", duration: 3000 });
        setMonto(undefined);
        setInicial("");
        setReferencia("");
        setInputKey((k) => k + 1);
        setError(null);
        if (desdeDividir && isPositive(nueva.totales.pendiente)) return router.push(`/panel/caja/${c.id}/dividir`);
        if (!isPositive(nueva.totales.pendiente)) requestAnimationFrame(() => cerrarRef.current?.focus());
      },
      onError: (err) => {
        setError(describeError(err));
        return true;
      },
    },
  );
  const quitarPago = useComandaAction<number>(c.id, (pagoId) => ({ path: `/pagos/${pagoId}`, method: "DELETE" }));
  // Al cerrar: se ofrece ir a facturar (y registrar al cliente) antes de volver a la sala
  const [cerrada, setCerrada] = useState<Comanda | null>(null);
  const cerrar = useComandaAction<void>(c.id, () => ({ path: "/cerrar" }), {
    onSuccess: (nueva) => {
      toast({ title: `Venta registrada · ${tituloComanda(c)}`, description: "La mesa quedó libre.", tone: "ok" });
      if (nueva.venta_id && can(me, "ventas", "editar")) setCerrada(nueva);
      else router.push("/panel");
    },
    onError: (err) => {
      setError(describeError(err));
      return true;
    },
  });

  function exacto() {
    if (!exactoEn) return;
    setMonto(undefined);
    setInicial(exactoEn);
    setInputKey((k) => k + 1);
  }

  return (
    <>
      <PageHeader
        eyebrow={
          desdeDividir ? (
            <Link href={`/panel/caja/${c.id}/dividir`} className="hover:text-fg-2">
              ← Dividir · cobrando a {etiquetaInicial}
            </Link>
          ) : (
            <Link href={`/panel/comandas/${c.id}`} className="hover:text-fg-2">
              ← Comanda {c.id}
            </Link>
          )
        }
        title={`Caja · ${tituloComanda(c)}`}
        actions={
          abierta && can(me, "caja", "leer") && c.items.some((i) => i.estado !== "cancelado") ? (
            <Link href={`/panel/caja/${c.id}/dividir`} className="inline-flex h-10 items-center rounded-control border border-line-strong px-4 text-base font-medium hover:bg-wash">
              Dividir cuenta
            </Link>
          ) : null
        }
      />

      {!abierta && <p className="-mt-6 mb-10 text-base text-fg-2">Esta comanda ya está {c.estado}.</p>}
      {abierta && turno.data === null && (
        <div role="status" className="-mt-4 mb-10 flex flex-wrap items-center justify-between gap-3 rounded-control border border-warn/50 bg-warn/10 px-4 py-3 text-sm">
          <span>La caja no tiene un turno abierto: los pagos no entrarán en ningún arqueo.</span>
          <Link href="/panel/caja-turno" className="font-medium underline underline-offset-4">
            Abrir turno
          </Link>
        </div>
      )}

      <div className="grid gap-16 desk:grid-cols-12">
        <section aria-label="Lo que falta" className="flex flex-col gap-6 desk:col-span-7">
          <span className="eyebrow">{vuelto ? "Cubierto" : "Falta"}</span>
          <Money value={preview.falta} simbolo={simbolo} size="xl" roll />
          {vuelto && monedas.length > 0 && (
            <section aria-label="Vuelto" className="flex flex-col">
              <h3 className="eyebrow pb-2 text-fg-2">Vuelto</h3>
              <ul className="flex flex-col">
                {monedas.map((m) => (
                  <li key={m.id} className="flex items-baseline justify-between border-t border-line py-4">
                    <span className="text-sm text-fg-3">{m.codigo}</span>
                    <Money value={fromPrincipal(vuelto, m.tasa, m.operacion)} simbolo={m.simbolo} size={m.es_principal ? "l" : "s"} roll className="text-fg" />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {vuelto && monedas.length === 0 && (
            <p className="text-lead text-fg-2">
              Vuelto <Money value={vuelto} simbolo={simbolo} className="font-medium text-fg" />
            </p>
          )}
          <ul className="flex flex-col">
            {monedas
              .filter((m) => !m.es_principal && !vuelto)
              .map((m) => (
                <li key={m.id} className="flex items-baseline justify-between border-t border-line py-4">
                  <span className="text-sm text-fg-3">{m.codigo}</span>
                  <Money value={fromPrincipal(preview.falta, m.tasa, m.operacion)} simbolo={m.simbolo} size="s" roll />
                </li>
              ))}
            {monedas.length === 0 &&
              c.totales.pendiente_monedas.map((m) => (
                <li key={m.moneda} className="flex items-baseline justify-between border-t border-line py-4">
                  <span className="text-sm text-fg-3">{m.moneda}</span>
                  <Money value={m.monto} simbolo={m.simbolo} size="s" />
                </li>
              ))}
          </ul>
          <dl className="flex flex-col text-sm">
            {(
              [
                ["Subtotal", c.totales.subtotal, isPositive(c.totales.descuento) || isPositive(c.totales.propina)],
                [`Descuento${c.descuento?.motivo ? ` · ${c.descuento.motivo}` : ""}`, `-${c.totales.descuento}`, isPositive(c.totales.descuento)],
                ["Propina", c.totales.propina, isPositive(c.totales.propina)],
                ["Total", c.totales.total, true],
                ["Pagado", c.totales.pagado, true],
                ["IGTF cobrado", c.totales.igtf, isPositive(c.totales.igtf)],
              ] as const
            )
              .filter(([, , ver]) => ver)
              .map(([label, valor]) => (
                <div key={label} className="flex items-baseline justify-between gap-4 border-t border-line py-2.5">
                  <dt className="truncate text-fg-3">{label}</dt>
                  <dd>
                    <Money value={valor} simbolo={simbolo} />
                  </dd>
                </div>
              ))}
          </dl>
          <div className="flex flex-wrap gap-2">
            {abierta && can(me, "caja", "editar") && (
              <>
                <Button size="sm" variant="line" onClick={() => setAjuste("descuento")}>
                  {c.descuento ? "Cambiar descuento" : "Descuento"}
                </Button>
                <Button size="sm" variant="line" onClick={() => setAjuste("propina")}>
                  {isPositive(c.totales.propina) ? "Cambiar propina" : "Propina"}
                </Button>
              </>
            )}
            <Button size="sm" variant="ghost" onClick={() => window.print()}>
              Imprimir pre-cuenta
            </Button>
          </div>
        </section>

        <section aria-label="Registrar pago" className="flex flex-col gap-8 desk:col-span-5">
          {puedeCobrar && hayPendiente && (
            <form
              className="flex flex-col gap-8"
              onSubmit={(e) => {
                e.preventDefault();
                if (!montoEfectivo || !moneda) return setError({ title: "Escribe cuánto te pagaron", tone: "warn" });
                pagar.mutate();
              }}
            >
              {monedas.length > 1 && (
                <Segmented
                  label="Moneda del pago"
                  value={String(moneda?.id ?? "")}
                  onChange={(v) => {
                    setMonedaId(Number(v));
                    setMonto(undefined);
                    setInicial("");
                    setInputKey((k) => k + 1);
                  }}
                  options={monedas.map((m) => ({ value: String(m.id), label: m.codigo }))}
                />
              )}
              <div className="flex flex-col gap-2">
                <MoneyInput
                  key={`${inputKey}-${moneda?.id}`}
                  label={`Recibido en ${moneda?.codigo ?? ""}`}
                  simbolo={moneda?.simbolo ?? ""}
                  defaultValue={inicial}
                  onValueChange={setMonto}
                  autoFocus
                />
                {moneda && exactoEn && (
                  <button type="button" onClick={exacto} className="self-start text-sm text-fg-2 underline-offset-4 hover:text-fg hover:underline">
                    Exacto: <Money value={exactoEn} simbolo={moneda.simbolo} />
                    {pctIgtf && <span className="text-fg-3"> (incluye IGTF {Number(pctIgtf)} %)</span>}
                  </button>
                )}
              </div>
              <Segmented label="Método" size="sm" value={metodo} onChange={setMetodo} options={METODOS} className="flex-wrap" />
              {metodo !== "efectivo" && (
                <Field label="Referencia" value={referencia} onChange={(e) => setReferencia(e.target.value)} maxLength={120} placeholder="Últimos dígitos, nro. de operación…" />
              )}
              <Field label="Etiqueta (cuenta dividida)" value={etiqueta} onChange={(e) => setEtiqueta(e.target.value)} maxLength={60} placeholder="Opcional · Ana, Parte 2…" />
              {error && <ErrorBox error={error} onClose={() => setError(null)} />}
              <Button type="submit" size="lg" loading={pagar.isPending} disabled={!montoEfectivo}>
                Registrar pago
              </Button>
            </form>
          )}

          {abierta && !hayPendiente && (
            <div className="flex flex-col gap-4">
              <p className="text-lead text-fg-2">La cuenta está cubierta.</p>
              {error && <ErrorBox error={error} onClose={() => setError(null)} />}
              {puedeCerrar && (
                <Button ref={cerrarRef} size="lg" loading={cerrar.isPending} onClick={() => cerrar.mutate()}>
                  Cerrar y liberar {c.mesa ? "la mesa" : "la comanda"}
                </Button>
              )}
            </div>
          )}

          {c.pagos.length > 0 && (
            <div className="flex flex-col gap-2">
              <h2 className="eyebrow">Pagos · {c.pagos.length}</h2>
              <ul className="flex flex-col">
                {c.pagos.map((p) => (
                  <li key={p.id} className="flex items-center gap-4 border-t border-line py-3">
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="text-base">
                        {METODO[p.metodo]}
                        {p.referencia && <span className="text-fg-3"> · {p.referencia}</span>}
                      </span>
                      <span className="text-sm text-fg-3">
                        {p.etiqueta ? `${p.etiqueta} · ` : ""}
                        {p.moneda !== principal?.codigo && <>= <Money value={p.monto_principal} simbolo={simbolo} /></>}
                      </span>
                    </span>
                    <Money value={p.monto} simbolo={monedas.find((m) => m.codigo === p.moneda)?.simbolo ?? p.moneda} className="text-base" />
                    {abierta && can(me, "caja", "eliminar") && (
                      <button
                        type="button"
                        onClick={() => quitarPago.mutate(p.id)}
                        aria-label={`Eliminar pago de ${p.monto} ${p.moneda}`}
                        className="grid size-8 place-items-center rounded-md text-fg-3 hover:bg-wash hover:text-err"
                      >
                        <Trash2 size={16} strokeWidth={1.5} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>

      <Ajuste c={c} tipo={ajuste} simbolo={simbolo ?? ""} onClose={() => setAjuste(null)} />
      <TicketPortal>
        <PreCuenta c={c} simbolo={simbolo ?? ""} />
      </TicketPortal>

      <Dialog
        open={cerrada !== null}
        onOpenChange={(o) => !o && router.push("/panel")}
        title={cerrada?.cliente_id ? "¿Facturar esta venta?" : "¿Deseas registrar al cliente?"}
        description={
          cerrada?.cliente_id
            ? `La venta #${cerrada.venta_id} ya tiene cliente. Puedes imprimir los datos para la factura ahora.`
            : "Para hacerle factura, registra su nombre y cédula o RIF. Queda guardado para la próxima vez."
        }
        actions={
          <>
            <Button variant="ghost" onClick={() => router.push("/panel")}>
              No, volver a la sala
            </Button>
            <Button onClick={() => cerrada && router.push(`/panel/ventas/${cerrada.venta_id}/factura`)}>
              {cerrada?.cliente_id ? "Ir a facturar" : "Sí, registrar y facturar"}
            </Button>
          </>
        }
      />
    </>
  );
}
