"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Sheet } from "@/components/ui/Sheet";
import { toast } from "@/components/ui/Toast";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { ClienteOut, TIPOS_DOCUMENTO, type Cliente } from "@/lib/api/schemas";
import { TIPO_DOCUMENTO_LABEL } from "@/lib/fiscal";
import { consultarCedula } from "./consulta";

const CAMPOS = [
  { name: "telefono", label: "Teléfono", max: 40, type: "tel" },
  { name: "email", label: "Correo", max: 254, type: "email" },
  { name: "direccion", label: "Dirección fiscal", max: 255 },
] as const;

/** Alta o edición de un cliente. En edición solo se envía lo que cambió. */
export function ClienteForm({ open, onOpenChange, cliente }: { open: boolean; onOpenChange: (o: boolean) => void; cliente: Cliente | null }) {
  const qc = useQueryClient();
  const [error, setError] = useState<ErrorView | null>(null);
  const [encontrado, setEncontrado] = useState<string | null>(null);
  const nombreRef = useRef<HTMLInputElement>(null);
  const tipoRef = useRef<HTMLSelectElement>(null);
  const guardar = useMutation({
    mutationFn: (body: Record<string, string | null>) =>
      cliente
        ? api(`/clientes/${cliente.id}`, { method: "PATCH", body, schema: ClienteOut })
        : api("/clientes", { method: "POST", body, schema: ClienteOut }),
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: ["clientes"] });
      toast({ title: cliente ? "Cliente actualizado" : `${c.nombre} quedó registrado`, tone: "ok", duration: 3000 });
      onOpenChange(false);
    },
    onError: (err) => setError(describeError(err)),
  });

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body: Record<string, string | null> = {};
    for (const c of ["nombre", "tipo_documento", ...CAMPOS.map((c) => c.name), "notas"] as const) {
      const v = String(f.get(c) ?? "").trim() || null;
      if (!cliente || v !== cliente[c]) body[c] = v;
    }
    // El documento se guarda solo con números: se compara normalizado para no reenviarlo sin cambios
    const doc = String(f.get("documento") ?? "").replace(/[\s.-]/g, "").toUpperCase().replace(/^[VEJGP]/, "") || null;
    if (!cliente || doc !== cliente.documento) body.documento = doc;
    if (!body.nombre && !cliente) return setError({ title: "El nombre es obligatorio", tone: "warn" });
    if (doc && !f.get("tipo_documento")) return setError({ title: "Elige el tipo de documento", description: "V, E, J, G o P, como en la cédula o el RIF.", tone: "warn" });
    if (cliente && Object.keys(body).length === 0) return onOpenChange(false);
    guardar.mutate(body);
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="right" title={cliente ? cliente.nombre : "Nuevo cliente"}>
      <form onSubmit={onSubmit} className="flex flex-col gap-7 pt-2" noValidate>
        <Field ref={nombreRef} name="nombre" label="Nombre o razón social" maxLength={120} defaultValue={cliente?.nombre ?? ""} autoFocus />
        <div className="grid grid-cols-[8.5rem_1fr] items-end gap-4">
          <Select ref={tipoRef} name="tipo_documento" label="Tipo" defaultValue={cliente?.tipo_documento ?? ""}>
            <option value="">—</option>
            {TIPOS_DOCUMENTO.map((t) => (
              <option key={t} value={t}>
                {TIPO_DOCUMENTO_LABEL[t]}
              </option>
            ))}
          </Select>
          <Field
            name="documento"
            label="Cédula o RIF"
            inputMode="numeric"
            maxLength={20}
            defaultValue={cliente?.documento ?? ""}
            placeholder="12345678"
            onBlur={async (e) => {
              // Autocompleta el nombre (si está vacío) desde el registro público, si está configurado
              if (nombreRef.current?.value.trim()) return;
              const r = await consultarCedula(tipoRef.current?.value || null, e.currentTarget.value);
              if (r && nombreRef.current && !nombreRef.current.value.trim()) {
                nombreRef.current.value = r.nombre;
                setEncontrado(r.zona ? `${r.nombre} · ${r.zona}` : r.nombre);
              }
            }}
          />
        </div>
        {encontrado && <p className="-mt-4 text-sm text-fg-3">Encontrado en el registro público: {encontrado}. Verifícalo con el cliente.</p>}
        {CAMPOS.map((c) => (
          <Field
            key={c.name}
            name={c.name}
            label={c.label}
            type={"type" in c ? c.type : "text"}
            maxLength={c.max}
            defaultValue={cliente?.[c.name] ?? ""}
          />
        ))}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="notas-cliente" className="eyebrow">
            Notas
          </label>
          <textarea
            id="notas-cliente"
            name="notas"
            defaultValue={cliente?.notas ?? ""}
            maxLength={2000}
            rows={3}
            placeholder="Alergias, preferencias…"
            className="resize-none border-b border-line-strong bg-transparent py-2 text-base outline-none placeholder:text-fg-4 focus:border-paper"
          />
        </div>
        {error && <ErrorBox error={error} onClose={() => setError(null)} />}
        <Button type="submit" size="lg" loading={guardar.isPending}>
          {cliente ? "Guardar cambios" : "Registrar cliente"}
        </Button>
      </form>
    </Sheet>
  );
}
