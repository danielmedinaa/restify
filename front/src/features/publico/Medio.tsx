"use client";

import { useReducedMotion } from "motion/react";
import type { z } from "zod";
import type { MedioOut } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

type Medio = z.infer<typeof MedioOut>;

/**
 * Foto o video de producto. Los videos van silenciados, en loop e inline; con
 * movimiento reducido no arrancan solos (se muestran con controles).
 */
export function Medio({ medio, alt, autoplay, className }: { medio: Medio; alt: string; autoplay?: boolean; className?: string }) {
  const reduce = useReducedMotion();
  if (medio.tipo === "video") {
    const auto = autoplay && !reduce;
    return (
      <video
        src={medio.url}
        className={cn("h-full w-full object-cover", className)}
        muted
        loop
        playsInline
        autoPlay={auto}
        controls={autoplay && !auto}
        preload={autoplay ? "auto" : "metadata"}
        aria-label={medio.texto_alt ?? alt}
      />
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- medios del backend o URLs externas arbitrarias
    <img src={medio.url} alt={medio.texto_alt ?? alt} loading="lazy" decoding="async" className={cn("h-full w-full object-cover", className)} />
  );
}
