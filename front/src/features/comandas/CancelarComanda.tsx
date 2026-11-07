"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field } from "@/components/ui/Field";
import { toast } from "@/components/ui/Toast";
import { describeError } from "@/lib/api/errors";
import type { Comanda } from "@/lib/api/schemas";
import { tituloComanda } from "./estado";
import { useComandaAction } from "./queries";

export function CancelarComanda({ open, onOpenChange, comanda }: { open: boolean; onOpenChange: (o: boolean) => void; comanda: Comanda }) {
  const router = useRouter();
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const cancelar = useComandaAction<string>(comanda.id, (m) => ({ path: "/cancelar", body: { motivo: m } }), {
    onSuccess: () => {
      onOpenChange(false);
      toast({ title: `${tituloComanda(comanda)} cancelada`, description: "Se liberó el stock reservado.", tone: "ok" });
      router.push("/panel");
    },
    onError: (err) => {
      setError(describeError(err).title);
      return true;
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`¿Cancelar ${tituloComanda(comanda)}?`}
      description="Se libera el stock reservado y la mesa queda libre. No se puede deshacer."
      actions={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Volver
          </Button>
          <Button
            loading={cancelar.isPending}
            onClick={() => {
              if (motivo.trim().length < 3) return setError("Cuéntanos el motivo en pocas palabras.");
              cancelar.mutate(motivo.trim());
            }}
          >
            Cancelar comanda
          </Button>
        </>
      }
    >
      <Field label="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={255} placeholder="El cliente se fue, pedido duplicado…" error={error} autoFocus />
    </Dialog>
  );
}
