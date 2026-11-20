"use client";

import { useTema } from "@/components/TemaProvider";
import { Logo } from "@/components/ui/Logo";
import { cn } from "@/lib/cn";

/**
 * Logo del restaurante (personalización). Si no cargó uno: el sello de RESTIFY cuando
 * `conRestify`, o nada (para cabeceras donde no queremos meter nuestra marca).
 */
export function LogoCliente({ size = 72, conRestify = false, className }: { size?: number; conRestify?: boolean; className?: string }) {
  const { logo_url } = useTema();
  if (logo_url) {
    // eslint-disable-next-line @next/next/no-img-element -- el logo viene de /media del propio sistema
    return <img src={logo_url} alt="" style={{ maxHeight: size, maxWidth: size * 3 }} className={cn("w-auto select-none object-contain", className)} draggable={false} />;
  }
  return conRestify ? <Logo size={size} className={className} /> : null;
}
