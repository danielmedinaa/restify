"use client";

import Big from "big.js";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Money } from "@/components/ui/Money";
import { MoneyInput } from "@/components/ui/MoneyInput";
import { Segmented } from "@/components/ui/Segmented";
import { toast } from "@/components/ui/Toast";
import { METODO } from "@/features/comandas/ComandaDetalle";
import { principalDe, useComandaAction } from "@/features/comandas/queries";
import { describeError, type ErrorView } from "@/lib/api/errors";
import type { Comanda, MetodoPago, Moneda } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { abonoConIgtf, coverIn, cubrirConIgtf, formatAmount, isPositive, minus, remaining, toPrincipal } from "@/lib/money";

const METODOS = Object.entries(METODO).map(([value, label]) => ({ value: value as MetodoPago, label }));

/** Billetes redondos por encima del monto: 40 -> 50, 100…; 10.500 -> 11.000, 15.000, 20.000… */
function billetes(monto: string): string[] {
  const m = new Big(monto);
  if (!m.gt(0)) return [];
  const exp = Math.max(0, m.round(0, Big.roundDown).toFixed(0).length - 1);
  const bases = [-1, 0, 1, 2].flatMap((d) => {
    const b = Math.pow(10, Math.max(0, exp + d));
    return [b, b * 5];
  });
  const vistos = new Set<string>();
  return [...new Set(bases)]
    .sort((a, b) => a - b)
    .map((b) => m.div(b).round(0, Big.roundUp).times(b))
    .filter((v) => v.gt(m))
    .map((v) => v.toFixed(2))
    .filter((v) => (vistos.has(v) ? false : (vistos.add(v), true)))
    .slice(0, 4);
}

interface Props {
  comanda: Comanda;
  monedas: Moneda[];
  /** Quién paga ("Persona 1", "Parte 2"): viaja como etiqueta del pago. En la vaca, el nombre se escribe aquí. */
  etiqueta?: string;
  /** Lo que falta por pagar (de esta persona, o de toda la cuenta en la vaca), en moneda principal. */
  falta: string;
  /** Modo vaca: cada quien aporta lo que quiera. `siguiente` numera el aporte si no se escribe nombre. */
  vaca?: { siguiente: number };
  onClose: () => void;
}

/**
 * Cobro de una persona de la cuenta dividida, sin salir de la pantalla. "Abona" es lo que se
 * aplica a su parte (editable); "Recibe" es el billete: la diferencia es el vuelto, que no
 * entra a caja (el pago se registra por lo que abona).
 */
export function CobrarModal({ comanda: c, monedas, etiqueta: etiquetaFija, falta, vaca, onClose }: Props) {
  const principal = principalDe(monedas);
  const [monedaId, setMonedaId] = useState<number | null>(principal?.id ?? null);
  const moneda = monedas.find((m) => m.id === monedaId) ?? principal;
  const [metodo, setMetodo] = useState<MetodoPago>("efectivo");
  const [referencia, setReferencia] = useState("");
  const [nombre, setNombre] = useState("");
  const etiqueta = etiquetaFija ?? (nombre.trim() || `Aporte ${vaca?.siguiente ?? 1}`);
  const [abona, setAbona] = useState<string | null>(null);
  const [recibe, setRecibe] = useState<string | null>(null);
  const [key, setKey] = useState(0);
  const [error, setError] = useState<ErrorView | null>(null);

  // En divisas, si la sucursal cobra IGTF, el pago lleva el impuesto incluido
  const pctIgtf = moneda?.es_divisa ? c.igtf_porcentaje : null;
  const exacto = useMemo(
    () => (moneda ? coverIn(pctIgtf ? cubrirConIgtf(falta, pctIgtf) : falta, moneda.tasa, moneda.operacion) : null),
    [moneda, pctIgtf, falta],
  );
  const [abonaInicial, setAbonaInicial] = useState<string | null>(null);
  const abonaEf = abona ?? abonaInicial ?? exacto;

  const calc = useMemo(() => {
    if (!moneda || !abonaEf) return null;
    const enPrincipal = toPrincipal(abonaEf, moneda.tasa, moneda.operacion);
    const aCuenta = pctIgtf ? abonoConIgtf(enPrincipal, pctIgtf) : enPrincipal;
    const vuelto = recibe && metodo === "efectivo" ? minus(recibe, abonaEf) : null;
    return { aCuenta, quedaDeSuParte: remaining(falta, aCuenta), exceso: new Big(aCuenta).gt(new Big(falta).plus("0.01")), vuelto };
  }, [moneda, abonaEf, pctIgtf, falta, recibe, metodo]);

  const vueltoPositivo = calc?.vuelto && isPositive(calc.vuelto) ? calc.vuelto : null;
  const faltaBillete = calc?.vuelto && new Big(calc.vuelto).lt(0) ? new Big(calc.vuelto).abs().toFixed(2) : null;

  const pagar = useComandaAction<void>(
    c.id,
    () => ({
      path: "/pagos",
      body: { moneda_id: moneda?.id, monto: abonaEf, metodo, referencia: referencia.trim() || null, etiqueta },
    }),
    {
      onSuccess: () => {
        toast({
          title: `${etiqueta} ya pagó`,
          description: vueltoPositivo ? `Vuelto: ${moneda?.simbolo ?? ""} ${formatAmount(vueltoPositivo)}` : `${moneda?.simbolo ?? ""} ${formatAmount(abonaEf ?? "0")} · ${METODO[metodo]}`,
          tone: "ok",
          duration: 4000,
        });
        onClose();
      },
      onError: (err) => {
        setError(describeError(err));
        return true;
      },
    },
  );

  const puede = !!abonaEf && isPositive(abonaEf) && !faltaBillete && !calc?.exceso && !pagar.isPending;
  const sugeridos = metodo === "efectivo" && abonaEf ? billetes(abonaEf) : [];

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={vaca ? "Agregar aporte" : `Cobrar a ${etiqueta}`}
      description={
        <>
          {vaca ? "Falta para cubrir la cuenta" : "Le corresponde"} <Money value={falta} simbolo={principal?.simbolo} className="font-medium text-fg" />
        </>
      }
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button loading={pagar.isPending} disabled={!puede} onClick={() => (setError(null), pagar.mutate())}>
            {vueltoPositivo ? "Cobrar y dar vuelto" : "Registrar pago"}
          </Button>
        </>
      }
    >
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (puede) pagar.mutate();
        }}
      >
        {vaca && <Field label="Nombre (opcional)" value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={50} placeholder={`Aporte ${vaca.siguiente}`} autoFocus />}
        {monedas.length > 1 && (
          <Segmented
            label="Moneda del pago"
            size="sm"
            value={String(moneda?.id ?? "")}
            onChange={(v) => {
              setMonedaId(Number(v));
              setAbona(null);
              setAbonaInicial(null);
              setRecibe(null);
              setKey((k) => k + 1);
            }}
            options={monedas.map((m) => ({ value: String(m.id), label: m.codigo }))}
          />
        )}
        <Segmented label="Método" size="sm" value={metodo} onChange={setMetodo} options={METODOS} className="flex-wrap" />

        <MoneyInput
          key={`abona-${key}-${moneda?.id}`}
          label={`Abona (${moneda?.codigo ?? ""})`}
          simbolo={moneda?.simbolo ?? ""}
          defaultValue={abonaEf ? formatAmount(abonaEf) : ""}
          onValueChange={(v) => {
            setAbona(v);
            setAbonaInicial(null);
          }}
        />
        {calc && isPositive(calc.quedaDeSuParte) && (
          <p className="-mt-3 text-sm text-warn">
            {vaca ? "Aún faltaría" : "Queda por pagar de su parte:"} <Money value={calc.quedaDeSuParte} simbolo={principal?.simbolo} />
          </p>
        )}
        {calc?.exceso && <p className="-mt-3 text-sm text-warn">Abona más de lo que falta. Si paga con un billete grande, escríbelo abajo en «Recibe» y se calcula el vuelto.</p>}

        {metodo === "efectivo" ? (
          <div className="flex flex-col gap-3">
            <MoneyInput
              key={`recibe-${key}-${moneda?.id}`}
              label="Recibe del cliente (opcional)"
              simbolo={moneda?.simbolo ?? ""}
              defaultValue={recibe ? formatAmount(recibe) : ""}
              onValueChange={setRecibe}
              autoFocus={!vaca}
            />
            {sugeridos.length > 0 && (
              <div className="flex flex-wrap gap-2" role="group" aria-label="Billete con el que paga">
                {abonaEf && (
                  <button type="button" onClick={() => (setRecibe(abonaEf), setKey((k) => k + 1))} className="rounded-full bg-wash px-3 py-1.5 text-sm text-fg-2 hover:text-fg">
                    Exacto
                  </button>
                )}
                {sugeridos.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => (setRecibe(s), setKey((k) => k + 1))}
                    className={cn("rounded-full px-3 py-1.5 text-sm tabular transition-colors", recibe === s ? "bg-paper text-ink" : "bg-wash text-fg-2 hover:text-fg")}
                  >
                    {formatAmount(s)}
                  </button>
                ))}
              </div>
            )}
            {vueltoPositivo && (
              <div className="flex items-baseline justify-between rounded-control bg-ok/12 px-4 py-3 ring-1 ring-inset ring-ok/40">
                <span className="eyebrow text-ok">Vuelto</span>
                <span className="flex flex-col items-end">
                  <Money value={vueltoPositivo} simbolo={moneda?.simbolo} size="m" className="text-fg" />
                  {moneda && principal && moneda.id !== principal.id && (
                    <span className="text-sm text-fg-3">
                      = <Money value={toPrincipal(vueltoPositivo, moneda.tasa, moneda.operacion)} simbolo={principal.simbolo} />
                    </span>
                  )}
                </span>
              </div>
            )}
            {faltaBillete && (
              <p className="text-sm text-warn">
                Con ese billete faltan <Money value={faltaBillete} simbolo={moneda?.simbolo} />
              </p>
            )}
          </div>
        ) : (
          <Field label="Referencia" value={referencia} onChange={(e) => setReferencia(e.target.value)} maxLength={120} placeholder="Últimos dígitos, nro. de operación…" />
        )}

        {error && <ErrorBox error={error} onClose={() => setError(null)} />}
        <button type="submit" className="sr-only" tabIndex={-1}>
          Registrar
        </button>
      </form>
    </Dialog>
  );
}
