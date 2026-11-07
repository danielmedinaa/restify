"use client";

import { useEffect, useState } from "react";

/** Banner fijo que avisa en qué ambiente estás (solo dev y pre; en producción no se muestra). */
export function BannerEntorno() {
  const [texto, setTexto] = useState("");

  useEffect(() => {
    let vivo = true;
    fetch("/entorno", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { banner: "" }))
      .then((d: { banner?: string }) => vivo && setTexto(d.banner ?? ""))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);

  if (!texto) return null;
  const dev = texto === "DESARROLLO";
  return (
    <div
      role="status"
      className={`pointer-events-none fixed inset-x-0 bottom-0 z-[2147483000] flex h-[26px] items-center justify-center text-[12px] font-bold uppercase tracking-[0.18em] text-[#1a1819] ${
        dev ? "bg-sky-400" : "bg-amber-400"
      }`}
    >
      {texto}
    </div>
  );
}
