import type { Tone } from "@/components/ui/Status";
import type { ComandaResumen, EstadoItem } from "@/lib/api/schemas";

/**
 * Estado de sala de una comanda abierta, derivado del resumen (el backend no lo
 * guarda). El orden es de urgencia: lo que pide acción primero.
 */
export type EstadoSala = "por_aprobar" | "por_servir" | "en_cocina" | "por_cobrar" | "abierta";

export function estadoSala(c: ComandaResumen): EstadoSala {
  if (c.items_pendientes > 0) return "por_aprobar";
  if (c.items_por_servir > 0) return "por_servir";
  if (c.items_en_cocina > 0) return "en_cocina";
  if (c.items_listos > 0) return "por_cobrar";
  return "abierta";
}

export const ESTADO_SALA: Record<EstadoSala | "libre", { label: string; tone: Tone }> = {
  libre: { label: "Libre", tone: "muted" },
  abierta: { label: "Sin platos", tone: "neutral" },
  por_aprobar: { label: "Por aprobar", tone: "neutral" },
  en_cocina: { label: "En cocina", tone: "neutral" },
  por_servir: { label: "Por servir", tone: "ok" },
  por_cobrar: { label: "Por cobrar", tone: "warn" },
};

/** Platos que ya salieron de cocina sobre los que cuentan (sin cancelados). */
export function progreso(c: ComandaResumen) {
  const total = c.items_pendientes + c.items_en_cocina + c.items_listos;
  return { hechos: c.items_listos, total };
}

export const ESTADO_ITEM: Record<EstadoItem, { label: string; tone: Tone }> = {
  pendiente: { label: "Por aprobar", tone: "neutral" },
  en_cocina: { label: "En cocina", tone: "muted" },
  preparando: { label: "Preparando", tone: "neutral" },
  listo: { label: "Listo", tone: "ok" },
  entregado: { label: "Entregado", tone: "muted" },
  cancelado: { label: "Cancelado", tone: "muted" },
};

export function tituloComanda(c: { mesa: string | null; nombre_cliente: string | null; id: number }) {
  if (c.mesa) return /^\d+$/.test(c.mesa) ? `Mesa ${c.mesa}` : c.mesa;
  return c.nombre_cliente ?? `Para llevar #${c.id}`;
}

export function minutosDesde(iso: string, now: number) {
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
}
