"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "@/components/ui/Toast";
import { StockAlertaEvento } from "@/lib/api/schemas";
import { useRealtime } from "@/lib/realtime/RealtimeProvider";

/** Las alertas de stock bajo aparecen como toast en cualquier pantalla del panel. */
export function StockAlerts() {
  const qc = useQueryClient();
  useRealtime("stock.alerta", (data) => {
    const alerta = StockAlertaEvento.safeParse(data);
    if (!alerta.success) return;
    toast({ title: `Stock bajo · ${alerta.data.insumo}`, description: alerta.data.mensaje, tone: "warn", duration: 10_000 });
    void qc.invalidateQueries({ queryKey: ["alertas"] });
  });
  useRealtime("stock.alerta_resuelta", () => void qc.invalidateQueries({ queryKey: ["alertas"] }));
  return null;
}
