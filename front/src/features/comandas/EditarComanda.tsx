"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Sheet } from "@/components/ui/Sheet";
import { can, useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { ClienteOut, Pagina, type Cliente, type Comanda } from "@/lib/api/schemas";
import { useComandaAction, useMesas } from "./queries";
import { formatoDocumento } from "@/lib/fiscal";

/** Mesa, cliente, nombre y notas de la comanda (PATCH solo de lo que cambió). */
export function EditarComanda({ open, onOpenChange, comanda }: { open: boolean; onOpenChange: (o: boolean) => void; comanda: Comanda }) {
  const { data: me } = useMe();
  const mesas = useMesas(comanda.sucursal_id);
  const [mesaId, setMesaId] = useState<number | null>(comanda.mesa_id);
  const [cliente, setCliente] = useState<{ id: number; nombre: string } | null>(
    comanda.cliente_id ? { id: comanda.cliente_id, nombre: comanda.nombre_cliente ?? `Cliente ${comanda.cliente_id}` } : null,
  );
  const [nombre, setNombre] = useState(comanda.cliente_id ? "" : (comanda.nombre_cliente ?? ""));
  const [notas, setNotas] = useState(comanda.notas ?? "");
  const [error, setError] = useState<ErrorView | null>(null);

  const guardar = useComandaAction<Record<string, unknown>>(comanda.id, (body) => ({ path: "", method: "PATCH", body }), {
    onSuccess: () => onOpenChange(false),
    onError: (err) => {
      setError(describeError(err));
      return true;
    },
  });

  function onGuardar() {
    const body: Record<string, unknown> = {};
    if (mesaId !== comanda.mesa_id) body.mesa_id = mesaId;
    if ((cliente?.id ?? null) !== comanda.cliente_id) body.cliente_id = cliente?.id ?? null;
    const nombreFinal = nombre.trim() || null;
    if (!cliente && nombreFinal !== comanda.nombre_cliente) body.nombre_cliente = nombreFinal;
    const notasFinal = notas.trim() || null;
    if (notasFinal !== comanda.notas) body.notas = notasFinal;
    if (Object.keys(body).length === 0) return onOpenChange(false);
    guardar.mutate(body);
  }

  // Mesas libres + la actual
  const opciones = (mesas.data ?? []).filter((m) => !m.ocupada || m.id === comanda.mesa_id);

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      side="right"
      title="Mesa, cliente y notas"
      footer={
        <div className="flex flex-col gap-4">
          {error && <ErrorBox error={error} onClose={() => setError(null)} />}
          <Button size="lg" className="w-full" loading={guardar.isPending} onClick={onGuardar}>
            Guardar
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-8 pt-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="mesa" className="eyebrow">
            Mesa
          </label>
          <select
            id="mesa"
            value={mesaId ?? ""}
            onChange={(e) => setMesaId(e.target.value ? Number(e.target.value) : null)}
            className="h-11 border-b border-line-strong bg-transparent text-lead outline-none focus:border-paper"
          >
            <option value="" className="bg-overlay">
              Sin mesa (para llevar)
            </option>
            {opciones.map((m) => (
              <option key={m.id} value={m.id} className="bg-overlay">
                {m.nombre}
              </option>
            ))}
          </select>
          <p className="text-sm text-fg-3">Solo aparecen las mesas libres.</p>
        </div>

        {can(me, "clientes") && <ClientePicker value={cliente} onChange={setCliente} />}

        {!cliente && (
          <Field label="Nombre (sin ficha de cliente)" value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={120} />
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="notas" className="eyebrow">
            Notas
          </label>
          <textarea
            id="notas"
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            maxLength={1000}
            rows={3}
            className="resize-none border-b border-line-strong bg-transparent py-2 text-base outline-none focus:border-paper"
          />
        </div>
      </div>
    </Sheet>
  );
}

function ClientePicker({ value, onChange }: { value: { id: number; nombre: string } | null; onChange: (c: { id: number; nombre: string } | null) => void }) {
  const [q, setQ] = useState("");
  const term = q.trim();
  const res = useQuery({
    queryKey: ["clientes", "buscar", term],
    queryFn: () => api("/clientes", { query: { q: term, limite: 6 }, schema: Pagina(ClienteOut) }),
    enabled: term.length >= 2,
    staleTime: 30_000,
  });

  if (value) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="eyebrow">Cliente</span>
        <div className="flex h-11 items-center justify-between border-b border-line-strong">
          <span className="text-lead">{value.nombre}</span>
          <button type="button" onClick={() => onChange(null)} aria-label="Quitar cliente" className="grid size-8 place-items-center rounded-md text-fg-3 hover:bg-wash hover:text-fg">
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <Field label="Cliente" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre, documento o teléfono" autoComplete="off" />
      {term.length >= 2 && (
        <ul className="flex flex-col" aria-label="Resultados">
          {res.data?.items.map((c: Cliente) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onChange({ id: c.id, nombre: c.nombre })}
                className="flex w-full items-baseline justify-between gap-3 rounded-control px-2 py-2.5 text-left hover:bg-wash"
              >
                <span className="text-base">{c.nombre}</span>
                <span className="text-sm text-fg-3">{formatoDocumento(c.tipo_documento, c.documento) || c.telefono || ""}</span>
              </button>
            </li>
          ))}
          {res.data?.items.length === 0 && <li className="px-2 py-2 text-sm text-fg-3">Nadie con ese dato. Créalo en Clientes.</li>}
        </ul>
      )}
    </div>
  );
}
