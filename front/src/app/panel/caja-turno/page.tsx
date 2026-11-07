"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Big from "big.js";
import { useState } from "react";
import { z } from "zod";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Money } from "@/components/ui/Money";
import { Segmented } from "@/components/ui/Segmented";
import { Sheet } from "@/components/ui/Sheet";
import { StatusDot } from "@/components/ui/Status";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { useTurnoActual } from "@/features/caja/turno";
import { METODO } from "@/features/comandas/ComandaDetalle";
import { useMonedas } from "@/features/comandas/queries";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { TurnoOut, type Moneda, type Turno } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { isPositive, parseAmountInput } from "@/lib/money";

const hora = new Intl.DateTimeFormat("es", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function TurnoCajaPage() {
  const { data: me } = useMe();
  const { actual } = useSucursal();
  const turno = useTurnoActual(actual?.id);
  const { data: monedas } = useMonedas(actual?.id);
  const historial = useQuery({
    queryKey: ["caja", "turnos", actual?.id],
    queryFn: () => api("/caja/turnos", { query: { sucursal_id: actual!.id, limite: 10 }, schema: z.array(TurnoOut) }),
    enabled: !!actual && can(me, "caja"),
  });

  if (!can(me, "caja")) return <SinAcceso />;
  const activas = (monedas ?? []).filter((m) => m.activa);
  return (
    <>
      <PageHeader eyebrow={actual?.nombre} title="Turno de caja" />
      {turno.isPending ? (
        <ListLoading />
      ) : turno.isError ? (
        <ListError error={turno.error} />
      ) : turno.data ? (
        <TurnoAbierto t={turno.data} monedas={activas} />
      ) : (
        actual && <AbrirTurno sucursalId={actual.id} monedas={activas} puede={can(me, "caja", "crear")} />
      )}

      {historial.data && historial.data.some((t) => t.estado === "cerrado") && (
        <section className="mt-20 flex flex-col gap-4">
          <h2 className="font-display text-display-s">Turnos anteriores</h2>
          <ul className="flex flex-col">
            {historial.data
              .filter((t) => t.estado === "cerrado")
              .map((t) => (
                <li key={t.id} className="flex flex-wrap items-baseline justify-between gap-4 border-t border-line py-4">
                  <span className="flex flex-col">
                    <span className="text-base font-medium">{hora.format(new Date(t.abierto_en))}</span>
                    <span className="text-sm text-fg-3">
                      {t.resumen.ventas} ventas · cerró {t.cerrado_por ?? "—"}
                    </span>
                  </span>
                  <span className="flex flex-wrap gap-4">
                    {t.arqueo?.map((a) => (
                      <StatusDot key={a.moneda_id} tone={a.diferencia === "0.00" ? "ok" : new Big(a.diferencia).lt(0) ? "err" : "warn"}>
                        {a.moneda} {a.diferencia === "0.00" ? "cuadró" : <Money value={a.diferencia} simbolo={a.simbolo} />}
                      </StatusDot>
                    ))}
                  </span>
                </li>
              ))}
          </ul>
        </section>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ abrir */
function AbrirTurno({ sucursalId, monedas, puede }: { sucursalId: number; monedas: Moneda[]; puede: boolean }) {
  const qc = useQueryClient();
  const [fondo, setFondo] = useState<Record<number, string>>({});
  const [error, setError] = useState<ErrorView | null>(null);
  const abrir = useMutation({
    mutationFn: () =>
      api("/caja/turnos", {
        method: "POST",
        body: {
          sucursal_id: sucursalId,
          fondo: monedas.map((m) => ({ moneda_id: m.id, monto: parseAmountInput(fondo[m.id] ?? "") ?? "0" })),
        },
        schema: TurnoOut,
      }),
    onSuccess: (t) => {
      qc.setQueryData(["caja", "turno", sucursalId], t);
      void qc.invalidateQueries({ queryKey: ["caja", "turnos"] });
      toast({ title: "Caja abierta", tone: "ok", duration: 3000 });
    },
    onError: (e) => setError(describeError(e)),
  });

  return (
    <section className="flex max-w-xl flex-col gap-8">
      <div className="flex flex-col gap-2">
        <StatusDot tone="muted">Caja cerrada</StatusDot>
        <p className="text-lead text-fg-2">Abre el turno con el efectivo que hay en la gaveta. Desde ahí, cada cobro queda en este turno para el arqueo.</p>
      </div>
      {puede ? (
        <form
          className="flex flex-col gap-6"
          onSubmit={(e) => {
            e.preventDefault();
            abrir.mutate();
          }}
        >
          <div className="grid gap-6 tablet:grid-cols-2">
            {monedas.map((m) => (
              <Field
                key={m.id}
                label={`Fondo en ${m.codigo}`}
                inputMode="decimal"
                placeholder={`${m.simbolo} 0`}
                value={fondo[m.id] ?? ""}
                onChange={(e) => setFondo((f) => ({ ...f, [m.id]: e.target.value }))}
              />
            ))}
          </div>
          {error && <ErrorBox error={error} onClose={() => setError(null)} />}
          <Button type="submit" size="lg" loading={abrir.isPending} className="self-start">
            Abrir caja
          </Button>
        </form>
      ) : (
        <p className="text-sm text-fg-3">No tienes permiso para abrir la caja.</p>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ abierto */
function TurnoAbierto({ t, monedas }: { t: Turno; monedas: Moneda[] }) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [cerrar, setCerrar] = useState(false);
  const [mov, setMov] = useState<{ tipo: "ingreso" | "retiro"; moneda_id: number; monto: string; motivo: string }>({
    tipo: "retiro",
    moneda_id: monedas[0]?.id ?? 0,
    monto: "",
    motivo: "",
  });
  const [error, setError] = useState<ErrorView | null>(null);
  const r = t.resumen;
  const actualizar = (nuevo: Turno) => {
    qc.setQueryData(["caja", "turno", t.sucursal_id], nuevo.estado === "abierto" ? nuevo : null);
    void qc.invalidateQueries({ queryKey: ["caja", "turnos"] });
  };
  const movimiento = useMutation({
    mutationFn: () =>
      api(`/caja/turnos/${t.id}/movimientos`, {
        method: "POST",
        body: { ...mov, monto: parseAmountInput(mov.monto), motivo: mov.motivo.trim() },
        schema: TurnoOut,
      }),
    onSuccess: (n) => {
      actualizar(n);
      setMov((m) => ({ ...m, monto: "", motivo: "" }));
      setError(null);
      toast({ title: mov.tipo === "retiro" ? "Retiro registrado" : "Ingreso registrado", tone: "ok", duration: 3000 });
    },
    onError: (e) => setError(describeError(e)),
  });

  return (
    <div className="flex flex-col gap-14">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex flex-col gap-2">
          <StatusDot tone="ok">
            Abierta desde {hora.format(new Date(t.abierto_en))}
            {t.abierto_por && ` · ${t.abierto_por}`}
          </StatusDot>
          <dl className="flex flex-wrap gap-x-10 gap-y-4 pt-2">
            <Kpi label="Ventas" valor={String(r.ventas)} />
            <Kpi label="Facturado" dinero={r.facturado} />
            {isPositive(r.propinas) && <Kpi label="Propinas" dinero={r.propinas} />}
            {isPositive(r.descuentos) && <Kpi label="Descuentos" dinero={r.descuentos} />}
            {isPositive(r.igtf) && <Kpi label="IGTF cobrado" dinero={r.igtf} />}
          </dl>
        </div>
        {can(me, "caja", "editar") && (
          <Button size="lg" onClick={() => setCerrar(true)}>
            Cerrar caja
          </Button>
        )}
      </div>

      <div className="grid gap-14 desk:grid-cols-2">
        <section className="flex flex-col gap-3">
          <h2 className="eyebrow">Efectivo que debería haber</h2>
          {r.efectivo.map((e) => (
            <div key={e.moneda_id} className="flex flex-col gap-2 border-t border-line py-4">
              <div className="flex items-baseline justify-between">
                <span className="font-display text-display-s leading-none">{e.moneda}</span>
                <Money value={e.esperado} simbolo={e.simbolo} size="l" />
              </div>
              <p className="flex flex-wrap gap-x-4 text-sm text-fg-3">
                <span>Fondo {e.fondo}</span>
                <span>+ cobrado {e.cobrado}</span>
                {isPositive(e.ingresos) && <span>+ ingresos {e.ingresos}</span>}
                {isPositive(e.retiros) && <span>− retiros {e.retiros}</span>}
                {isPositive(e.vueltos) && <span>− vueltos {e.vueltos}</span>}
              </p>
            </div>
          ))}
        </section>
        <section className="flex flex-col gap-3">
          <h2 className="eyebrow">Cobrado por método</h2>
          {r.por_metodo.length === 0 ? (
            <p className="border-t border-line py-4 text-base text-fg-3">Todavía no hay cobros en este turno.</p>
          ) : (
            r.por_metodo.map((m) => (
              <div key={`${m.metodo}-${m.moneda}`} className="flex items-baseline justify-between border-t border-line py-3">
                <span>
                  {METODO[m.metodo]} <span className="text-sm text-fg-3">· {m.moneda} · {m.cantidad}</span>
                </span>
                <Money value={m.monto} simbolo={m.simbolo} />
              </div>
            ))
          )}
        </section>
      </div>

      <section className="flex max-w-2xl flex-col gap-4">
        <h2 className="eyebrow">Ingresos y retiros de la gaveta</h2>
        {can(me, "caja", "crear") && (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!parseAmountInput(mov.monto)) return setError({ title: "Escribe el monto", tone: "warn" });
              if (mov.motivo.trim().length < 3) return setError({ title: "Indica el motivo", tone: "warn" });
              movimiento.mutate();
            }}
          >
            <div className="flex flex-wrap gap-3">
              <Segmented
                label="Tipo"
                size="sm"
                value={mov.tipo}
                onChange={(tipo) => setMov((m) => ({ ...m, tipo }))}
                options={[
                  { value: "retiro", label: "Retiro" },
                  { value: "ingreso", label: "Ingreso" },
                ]}
              />
              <Segmented
                label="Moneda"
                size="sm"
                value={String(mov.moneda_id)}
                onChange={(v) => setMov((m) => ({ ...m, moneda_id: Number(v) }))}
                options={monedas.map((m) => ({ value: String(m.id), label: m.codigo }))}
              />
            </div>
            <div className="grid grid-cols-[8rem_1fr_auto] items-end gap-3">
              <Field label="Monto" inputMode="decimal" value={mov.monto} onChange={(e) => setMov((m) => ({ ...m, monto: e.target.value }))} />
              <Field label="Motivo" value={mov.motivo} maxLength={255} onChange={(e) => setMov((m) => ({ ...m, motivo: e.target.value }))} placeholder="Pago al panadero, cambio del banco…" />
              <Button type="submit" loading={movimiento.isPending}>
                Registrar
              </Button>
            </div>
            {error && <ErrorBox error={error} onClose={() => setError(null)} />}
          </form>
        )}
        {t.movimientos.map((m) => (
          <div key={m.id} className="flex items-baseline justify-between gap-4 border-t border-line py-3 text-sm">
            <span className="flex flex-col">
              <span className="text-base">{m.motivo}</span>
              <span className="text-fg-3">
                {m.tipo === "retiro" ? "Retiro" : "Ingreso"} · {m.usuario ?? "—"} · {hora.format(new Date(m.created_at))}
              </span>
            </span>
            <span className={cn("tabular", m.tipo === "retiro" ? "text-fg-2" : "text-fg")}>
              {m.tipo === "retiro" ? "−" : "+"}
              {m.simbolo} {m.monto}
            </span>
          </div>
        ))}
      </section>

      <CerrarTurno t={t} open={cerrar} onOpenChange={setCerrar} onCerrado={actualizar} />
    </div>
  );
}

function Kpi({ label, valor, dinero }: { label: string; valor?: string; dinero?: string }) {
  return (
    <div>
      <dt className="text-sm text-fg-3">{label}</dt>
      <dd className="font-display text-display-s leading-none">{dinero ? <Money value={dinero} /> : valor}</dd>
    </div>
  );
}

/* ------------------------------------------------------------------ cerrar (arqueo) */
function CerrarTurno({ t, open, onOpenChange, onCerrado }: { t: Turno; open: boolean; onOpenChange: (o: boolean) => void; onCerrado: (t: Turno) => void }) {
  const [contado, setContado] = useState<Record<number, string>>({});
  const [notas, setNotas] = useState("");
  const [error, setError] = useState<ErrorView | null>(null);
  const cerrar = useMutation({
    mutationFn: () =>
      api(`/caja/turnos/${t.id}/cerrar`, {
        method: "POST",
        body: {
          contado: t.resumen.efectivo.map((e) => ({ moneda_id: e.moneda_id, monto: parseAmountInput(contado[e.moneda_id] ?? "") ?? "0" })),
          notas: notas.trim() || null,
        },
        schema: TurnoOut,
      }),
    onSuccess: (n) => {
      onOpenChange(false);
      onCerrado(n);
      const descuadre = n.arqueo?.some((a) => a.diferencia !== "0.00");
      toast({ title: descuadre ? "Caja cerrada con diferencias" : "Caja cerrada · cuadró exacto", tone: descuadre ? "warn" : "ok" });
    },
    onError: (e) => setError(describeError(e)),
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="right" title="Cerrar caja" description="Cuenta el efectivo de la gaveta, moneda por moneda.">
      <form
        className="flex flex-col gap-8 pt-2"
        onSubmit={(e) => {
          e.preventDefault();
          cerrar.mutate();
        }}
      >
        {t.resumen.efectivo.map((e) => {
          const c = parseAmountInput(contado[e.moneda_id] ?? "");
          const dif = c === null ? null : new Big(c).minus(e.esperado);
          return (
            <div key={e.moneda_id} className="flex flex-col gap-2">
              <Field
                label={`Contado en ${e.moneda}`}
                inputMode="decimal"
                placeholder={`Esperado ${e.simbolo} ${e.esperado}`}
                value={contado[e.moneda_id] ?? ""}
                onChange={(ev) => setContado((x) => ({ ...x, [e.moneda_id]: ev.target.value }))}
              />
              {dif !== null && (
                <StatusDot tone={dif.eq(0) ? "ok" : dif.lt(0) ? "err" : "warn"}>
                  {dif.eq(0) ? "Cuadra exacto" : dif.lt(0) ? `Faltan ${e.simbolo} ${dif.abs().toFixed(2)}` : `Sobran ${e.simbolo} ${dif.toFixed(2)}`}
                </StatusDot>
              )}
            </div>
          );
        })}
        <Field label="Notas (opcional)" value={notas} onChange={(e) => setNotas(e.target.value)} maxLength={1000} placeholder="Algo que explique una diferencia…" />
        {error && <ErrorBox error={error} onClose={() => setError(null)} />}
        <Button type="submit" size="lg" loading={cerrar.isPending}>
          Cerrar caja
        </Button>
      </form>
    </Sheet>
  );
}
