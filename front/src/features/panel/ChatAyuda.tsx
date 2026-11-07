"use client";

import { useEffect } from "react";
import { useMe } from "@/features/auth/useMe";

const PROPIEDAD = process.env.NEXT_PUBLIC_TAWK_PROPERTY_ID ?? "";
const WIDGET = process.env.NEXT_PUBLIC_TAWK_WIDGET_ID ?? "";
const ID = /^[a-z0-9]+$/i;

declare global {
  interface Window {
    Tawk_API?: { onLoad?: () => void; setAttributes?: (a: Record<string, string>, cb?: (e?: unknown) => void) => void; visitor?: { name?: string; email?: string } };
    Tawk_LoadStart?: Date;
  }
}

/**
 * Chat de ayuda (Tawk.to con su asistente IA) dentro del panel. Se activa con
 * NEXT_PUBLIC_TAWK_PROPERTY_ID y NEXT_PUBLIC_TAWK_WIDGET_ID; sin ellas no carga nada.
 * Le pasa a Tawk quién escribe (nombre, correo y rol) para que el soporte sepa con quién habla.
 */
export function ChatAyuda() {
  const { data: me } = useMe();

  useEffect(() => {
    if (!me || !ID.test(PROPIEDAD) || !ID.test(WIDGET)) return;
    const visitante = { name: me.nombre, email: me.email };
    const atributos = { rol: me.es_superadmin ? "Superadmin" : (me.rol?.nombre ?? "Sin rol"), sucursales: me.sucursales.map((s) => s.nombre).join(", ") };

    // Una sola vez por pestaña: el panel navega sin recargar
    if (document.getElementById("tawk-script")) {
      window.Tawk_API?.setAttributes?.({ ...visitante, ...atributos });
      return;
    }
    window.Tawk_API = window.Tawk_API || {};
    window.Tawk_API.visitor = visitante;
    window.Tawk_API.onLoad = () => window.Tawk_API?.setAttributes?.(atributos);
    window.Tawk_LoadStart = new Date();
    const s = document.createElement("script");
    s.id = "tawk-script";
    s.async = true;
    s.src = `https://embed.tawk.to/${PROPIEDAD}/${WIDGET}`;
    s.charset = "UTF-8";
    s.setAttribute("crossorigin", "*");
    document.head.appendChild(s);
  }, [me]);

  return null;
}
