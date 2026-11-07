"use client";

import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Sheet } from "@/components/ui/Sheet";
import { toast } from "@/components/ui/Toast";
import { notifyError } from "@/features/comandas/queries";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";

type Method = "POST" | "PATCH" | "PUT" | "DELETE";

/** Mutación simple contra la API que invalida las listas afectadas y avisa. */
export function useApiMutation<V = Record<string, unknown>>(opts: {
  path: (v: V) => string;
  method: Method | ((v: V) => Method);
  body?: (v: V) => unknown;
  invalidate: QueryKey[];
  ok?: string | ((v: V) => string);
  onDone?: () => void;
  /** Si se pasa, el error se guarda aquí en vez de mostrarse como toast. */
  onError?: (e: ErrorView) => void;
}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: V) =>
      api(opts.path(v), {
        method: typeof opts.method === "function" ? opts.method(v) : opts.method,
        body: opts.body ? opts.body(v) : (v as unknown),
      }),
    onSuccess: (_d, v) => {
      opts.invalidate.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
      if (opts.ok) toast({ title: typeof opts.ok === "function" ? opts.ok(v) : opts.ok, tone: "ok", duration: 3000 });
      opts.onDone?.();
    },
    onError: (err) => (opts.onError ? opts.onError(describeError(err)) : notifyError(err)),
  });
}

/** Estado de un formulario en sheet: abierto/cerrado sin perder la animación de salida. */
export function useFormSheet<T>() {
  const [state, setState] = useState<{ item: T | null; key: number; open: boolean } | null>(null);
  return {
    state,
    abrir: (item: T | null) => setState({ item, key: Date.now(), open: true }),
    cerrar: () => setState((s) => s && { ...s, open: false }),
    onOpenChange: (o: boolean) => setState((s) => s && { ...s, open: o }),
  };
}

/** Sheet lateral con formulario: título, cuerpo, error y botón de guardar. */
export function FormSheet({
  open,
  onOpenChange,
  title,
  description,
  onSubmit,
  pending,
  error,
  onClearError,
  submitLabel = "Guardar",
  children,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: string;
  onSubmit: (form: FormData) => void;
  pending: boolean;
  error: ErrorView | null;
  onClearError: () => void;
  submitLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="right" title={title} description={description}>
      <form
        noValidate
        className="flex flex-col gap-7 pt-2"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(new FormData(e.currentTarget));
        }}
      >
        {children}
        {error && <ErrorBox error={error} onClose={onClearError} />}
        <Button type="submit" size="lg" loading={pending}>
          {submitLabel}
        </Button>
      </form>
    </Sheet>
  );
}

/** Confirmación para acciones que no se deshacen. */
export function Confirmar({
  open,
  onOpenChange,
  title,
  description,
  accion,
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: string;
  accion: string;
  pending?: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      actions={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Volver
          </Button>
          <Button loading={pending} onClick={onConfirm}>
            {accion}
          </Button>
        </>
      }
    />
  );
}

/** Lee un campo de texto del form: string recortado o null si viene vacío. */
export function txt(f: FormData, name: string): string | null {
  const v = String(f.get(name) ?? "").trim();
  return v === "" ? null : v;
}

/** Checkbox/switch nativo del form. */
export function bool(f: FormData, name: string): boolean {
  return f.get(name) === "on";
}

/** Solo los campos que cambiaron respecto al original (para PATCH). */
export function cambios<T extends Record<string, unknown>>(original: T | null, next: Record<string, unknown>): Record<string, unknown> {
  if (!original) return next;
  return Object.fromEntries(Object.entries(next).filter(([k, v]) => original[k] !== v));
}
