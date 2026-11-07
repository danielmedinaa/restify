import type { Tone } from "@/components/ui/Status";

/** Error de la API tal como llega por el BFF: status + detail (string, objeto o lista). */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
    public retryAfter: number | null = null,
  ) {
    super(typeof detail === "string" ? detail : `Error ${status}`);
    this.name = "ApiError";
  }
}

export interface ErrorView {
  title: string;
  description?: string;
  /** Líneas de detalle (faltantes de stock, productos con error, etc.) */
  items?: string[];
  tone: Tone;
}

type Dict = Record<string, unknown>;
const isDict = (v: unknown): v is Dict => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));

function minutes(sec: number | null) {
  if (!sec) return "unos minutos";
  const m = Math.ceil(sec / 60);
  return m <= 1 ? "un minuto" : `${m} minutos`;
}

/** Traduce cualquier error a algo que una persona entienda. Nunca muestra JSON. */
export function describeError(error: unknown): ErrorView {
  if (!(error instanceof ApiError)) {
    return { title: "Sin conexión", description: "No pudimos hablar con el servidor. Revisa la red e intenta de nuevo.", tone: "err" };
  }
  const { status, detail } = error;

  if (status === 401) return { title: "Tu sesión terminó", description: "Vuelve a entrar para continuar.", tone: "warn" };
  if (status === 403) {
    return { title: "No tienes permiso", description: str(detail) || "Pídele acceso a un administrador.", tone: "warn" };
  }
  if (status === 402 && isDict(detail)) {
    // Suscripción: cuenta bloqueada o límite del plan alcanzado (el mensaje ya viene redactado)
    const mensaje = str(detail.mensaje);
    if (detail.codigo === "limite_plan") {
      return { title: "Llegaste al límite de tu plan", description: mensaje || "Pide un cambio de plan para agregar más.", tone: "warn" };
    }
    const titulos: Record<string, string> = { suspendida: "Cuenta suspendida", pausada: "Cuenta pausada", cancelada: "Cuenta dada de baja" };
    const motivo = str(detail.motivo);
    return {
      title: titulos[str(detail.estado)] ?? "Suscripción inactiva",
      description: [mensaje, motivo && `Motivo: ${motivo}.`].filter(Boolean).join(" ") || "Contacta a RESTIFY.",
      tone: "err",
    };
  }
  if (status === 423) {
    return { title: "Mesa ocupada", description: "Esa mesa ya tiene una comanda abierta.", tone: "warn" };
  }
  if (status === 429) {
    return { title: "Demasiados intentos", description: `Espera ${minutes(error.retryAfter)} y vuelve a intentarlo.`, tone: "warn" };
  }
  if (status === 409 && isDict(detail)) {
    const mensaje = str(detail.mensaje) || "No se pudo completar";
    if (Array.isArray(detail.faltantes)) {
      return {
        title: mensaje,
        tone: "err",
        items: detail.faltantes.filter(isDict).map((f) => `${str(f.insumo) || "Insumo"}: hay ${str(f.disponible)}, se necesitan ${str(f.requerido)}`),
      };
    }
    if (Array.isArray(detail.errores)) {
      return { title: mensaje, tone: "err", items: detail.errores.filter(isDict).map((e) => str(e.error)) };
    }
    if ("pendiente" in detail) {
      return { title: mensaje, description: `Faltan ${str(detail.pendiente)} por cobrar.`, tone: "warn" };
    }
    if (Array.isArray(detail.item_ids)) {
      return { title: "Hay platos sin terminar", description: "Márcalos listos en cocina o cancélalos antes de cerrar.", tone: "warn" };
    }
    return { title: mensaje, tone: "err" };
  }
  if (status === 422 && Array.isArray(detail)) {
    // Validación de Pydantic: [{ loc, msg }]
    return {
      title: "Revisa los datos",
      tone: "err",
      items: detail.filter(isDict).map((d) => str(d.msg).replace(/^Value error, /, "")),
    };
  }
  if (status === 404) return { title: str(detail) || "No encontrado", tone: "err" };
  if (status >= 500) return { title: "Algo falló de nuestro lado", description: str(detail) || "Intenta de nuevo en un momento.", tone: "err" };
  return { title: str(detail) || "No se pudo completar", tone: "err" };
}
