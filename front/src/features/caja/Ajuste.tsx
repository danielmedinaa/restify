"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Segmented";
import { useComandaAction } from "@/features/comandas/queries";
import { describeError, type ErrorView } from "@/lib/api/errors";
import type { Comanda } from "@/lib/api/schemas";
import { parseAmountInput } from "@/lib/money";

/** Descuento (% o monto, con motivo) o propina (% o monto) sobre la cuenta. Quedan en la bitácora. */
export function Ajuste({ c, tipo, simbolo, onClose }: { c: Comanda; tipo: "descuento" | "propina" | null; simbolo: string; onClose: () => void }) {
  return (
    <Dialog
      open={tipo !== null}
      onOpenChange={(o) => !o && onClose()}
      title={tipo === "propina" ? "Propina" : "Descuento"}
      description={tipo === "propina" ? "Se suma a lo que paga el cliente. No es venta del restaurante." : "Se aplica sobre la cuenta y queda registrado con su motivo."}
    >
      {tipo && <Formulario key={tipo} c={c} tipo={tipo} simbolo={simbolo} onClose={onClose} />}
    </Dialog>
  );
}

function Formulario({ c, tipo, simbolo, onClose }: { c: Comanda; tipo: "descuento" | "propina"; simbolo: string; onClose: () => void }) {
  const [modo, setModo] = useState<"porcentaje" | "monto">(tipo === "descuento" ? (c.descuento?.tipo ?? "porcentaje") : "porcentaje");
  const [valor, setValor] = useState(tipo === "descuento" && c.descuento ? c.descuento.valor.replace(/\.?0+$/, "") : "");
  const [motivo, setMotivo] = useState(tipo === "descuento" ? (c.descuento?.motivo ?? "") : "");
  const [error, setError] = useState<ErrorView | null>(null);
  const accion = useComandaAction<Record<string, unknown>>(c.id, (body) => ({ path: `/${tipo}`, method: "PUT", body }), {
    onSuccess: onClose,
    onError: (e) => {
      setError(describeError(e));
      return true;
    },
  });
  const enviar = (body: Record<string, unknown>) => accion.mutate(body);

  const n = parseAmountInput(valor);
  return (
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!n) return setError({ title: "Escribe un valor válido", tone: "warn" });
        if (tipo === "descuento") {
          if (motivo.trim().length < 3) return setError({ title: "Indica el motivo del descuento", tone: "warn" });
          enviar({ tipo: modo, valor: n, motivo: motivo.trim() });
        } else enviar(modo === "porcentaje" ? { porcentaje: n } : { monto: n });
      }}
    >
      <Segmented
        label="Tipo"
        value={modo}
        onChange={setModo}
        options={[
          { value: "porcentaje", label: "Porcentaje" },
          { value: "monto", label: `Monto (${simbolo})` },
        ]}
      />
      {tipo === "propina" && modo === "porcentaje" && (
        <div className="flex gap-2">
          {["5", "10", "15"].map((p) => (
            <Button key={p} type="button" size="sm" variant="line" onClick={() => setValor(p)}>
              {p} %
            </Button>
          ))}
        </div>
      )}
      <Field label={modo === "porcentaje" ? "Porcentaje" : `Monto en ${simbolo}`} value={valor} onChange={(e) => setValor(e.target.value)} inputMode="decimal" autoFocus />
      {tipo === "descuento" && <Field label="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={255} placeholder="Promo, cliente frecuente, reclamo…" />}
      {error && <ErrorBox error={error} onClose={() => setError(null)} />}
      <div className="flex flex-wrap justify-end gap-2">
        {((tipo === "descuento" && c.descuento) || (tipo === "propina" && Number(c.totales.propina) > 0)) && (
          <Button type="button" variant="danger" loading={accion.isPending} onClick={() => enviar(tipo === "descuento" ? { tipo: null } : { monto: "0" })}>
            Quitar
          </Button>
        )}
        <Button type="submit" loading={accion.isPending}>
          Aplicar
        </Button>
      </div>
    </form>
  );
}
