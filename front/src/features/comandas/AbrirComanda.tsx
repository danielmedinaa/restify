"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field } from "@/components/ui/Field";
import { describeError } from "@/lib/api/errors";
import type { Mesa } from "@/lib/api/schemas";
import { tituloComanda } from "./estado";
import { useAbrirComanda } from "./queries";

/** Abre una comanda en una mesa libre, o para llevar si mesa es null. */
export function AbrirComanda({
  open,
  onOpenChange,
  sucursalId,
  mesa,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  sucursalId: number;
  mesa: Mesa | null;
}) {
  const router = useRouter();
  const abrir = useAbrirComanda();
  const [nombre, setNombre] = useState("");
  const [error, setError] = useState<string | null>(null);
  const titulo = mesa ? tituloComanda({ mesa: mesa.nombre, nombre_cliente: null, id: 0 }) : "Para llevar";

  function cerrar(o: boolean) {
    onOpenChange(o);
    if (!o) {
      setNombre("");
      setError(null);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={cerrar}
      title={`Abrir · ${titulo}`}
      description={mesa ? "La mesa queda ocupada y su QR deja de aceptar pedidos nuevos." : "Una comanda sin mesa, para llevar o en barra."}
      actions={
        <>
          <Button variant="ghost" onClick={() => cerrar(false)}>
            Volver
          </Button>
          <Button
            loading={abrir.isPending}
            onClick={() =>
              abrir.mutate(
                { sucursal_id: sucursalId, mesa_id: mesa?.id ?? null, nombre_cliente: nombre.trim() || null },
                {
                  onSuccess: (c) => {
                    cerrar(false);
                    router.push(`/panel/comandas/${c.id}`);
                  },
                  onError: (err) => setError(describeError(err).title),
                },
              )
            }
          >
            Abrir comanda
          </Button>
        </>
      }
    >
      <Field
        label={mesa ? "Nombre del cliente (opcional)" : "Nombre del cliente"}
        value={nombre}
        onChange={(e) => setNombre(e.target.value)}
        maxLength={120}
        autoFocus
        error={error}
      />
    </Dialog>
  );
}
