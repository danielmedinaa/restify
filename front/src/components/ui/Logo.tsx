"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

/**
 * Sello de RESTIFY. El archivo va en public/brand/restify-sello.png (blanco sobre
 * transparente). Si falta, cae a la palabra en Gagalin para no dejar un hueco.
 */
export function Logo({ size = 160, className }: { size?: number; className?: string }) {
  const ref = useRef<HTMLImageElement>(null);
  const [missing, setMissing] = useState(false);

  // El error puede ocurrir antes de hidratar, cuando onError todavía no está conectado.
  useEffect(() => {
    const img = ref.current;
    if (img?.complete && img.naturalWidth === 0) setMissing(true);
  }, []);

  if (missing) {
    return (
      <span
        role="img"
        aria-label="Restify, gestión de cocina y restaurante"
        className={cn("font-display leading-none text-fg", className)}
        style={{ fontSize: size / 4.5 }}
      >
        RESTIFY
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- el sello puede no existir aún; necesitamos onError
    <img
      ref={ref}
      src="/brand/restify-sello.png"
      alt="Restify, gestión de cocina y restaurante"
      width={size}
      height={size}
      onError={() => setMissing(true)}
      className={cn("select-none", className)}
      draggable={false}
    />
  );
}

/** Marca compacta para el rail del panel y headers. */
export function Wordmark({ className }: { className?: string }) {
  return <span className={cn("font-display text-[1.75rem] leading-none tracking-tight", className)}>RESTIFY</span>;
}
