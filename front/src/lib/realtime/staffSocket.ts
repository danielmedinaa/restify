import { wsBase } from "@/lib/realtime/wsBase";
import { api } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { WsTicketOut } from "@/lib/api/schemas";

export type SocketStatus = "conectando" | "en_vivo" | "reconectando" | "detenido";

export interface StaffEvent {
  tipo: string;
  data: unknown;
}

interface Options {
  sucursalId: number;
  /** "cocina" usa la API key de cocina al pedir el ticket */
  app?: "panel" | "cocina";
  onEvent: (e: StaffEvent) => void;
  onStatus: (s: SocketStatus) => void;
}

const MAX_DELAY = 30_000;
// 1008: ticket inválido o sin permiso. Unos pocos reintentos cubren un ticket vencido en tránsito.
const MAX_POLICY_CLOSES = 3;

/**
 * WebSocket del personal: POST /auth/ws-ticket (vía BFF) y luego /ws/staff.
 * Los tickets son de un solo uso, así que cada reconexión pide uno nuevo.
 * Backoff exponencial con jitter, y reconexión inmediata al volver la red.
 */
export class StaffSocket {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private policyCloses = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;

  constructor(private opts: Options) {}

  start() {
    this.stopped = false;
    window.addEventListener("online", this.reconnectNow);
    void this.connect();
  }

  stop() {
    this.stopped = true;
    window.removeEventListener("online", this.reconnectNow);
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close(1000);
    this.ws = null;
    this.opts.onStatus("detenido");
  }

  private reconnectNow = () => {
    if (this.stopped || this.ws?.readyState === WebSocket.OPEN) return;
    if (this.timer) clearTimeout(this.timer);
    this.attempt = 0;
    void this.connect();
  };

  private async connect() {
    if (this.stopped) return;
    this.opts.onStatus(this.attempt === 0 ? "conectando" : "reconectando");
    const base = wsBase();
    if (!base) {
      console.error("[ws] Falta NEXT_PUBLIC_WS_URL");
      return this.opts.onStatus("detenido");
    }

    let ticket: string;
    try {
      ticket = (await api("/auth/ws-ticket", { method: "POST", schema: WsTicketOut, app: this.opts.app })).ticket;
    } catch (err) {
      // Sin sesión o sin permiso: reintentar no sirve (el 401 ya manda al login)
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return this.opts.onStatus("detenido");
      return this.schedule();
    }
    if (this.stopped) return;

    const url = `${base.replace(/\/$/, "")}/ws/staff?ticket=${encodeURIComponent(ticket)}&sucursal_id=${this.opts.sucursalId}`;
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onmessage = (msg) => {
      let event: StaffEvent;
      try {
        event = JSON.parse(String(msg.data)) as StaffEvent;
      } catch {
        return;
      }
      if (event.tipo === "ping") return;
      if (event.tipo === "conectado") {
        this.attempt = 0;
        this.policyCloses = 0;
        this.opts.onStatus("en_vivo");
      }
      this.opts.onEvent(event);
    };

    ws.onclose = (e) => {
      if (this.ws !== ws || this.stopped) return;
      this.ws = null;
      if (e.code === 1008 && ++this.policyCloses >= MAX_POLICY_CLOSES) return this.opts.onStatus("detenido");
      this.schedule();
    };
  }

  private schedule() {
    if (this.stopped) return;
    this.opts.onStatus("reconectando");
    const delay = Math.min(MAX_DELAY, 1000 * 2 ** this.attempt++);
    this.timer = setTimeout(() => void this.connect(), delay / 2 + Math.random() * (delay / 2));
  }
}
