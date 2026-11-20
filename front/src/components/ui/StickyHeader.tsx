"use client";

import { motion, useScroll, useTransform } from "motion/react";
import { cn } from "@/lib/cn";

/**
 * Header que gana blur y una línea inferior a medida que el contenido pasa por
 * debajo. Sin scroll es transparente: el título respira sobre el fondo.
 */
export function StickyHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  const { scrollY } = useScroll();
  const blur = useTransform(scrollY, [0, 64], [0, 16]);
  const backdropFilter = useTransform(blur, (b) => `blur(${b}px) saturate(${1 + b / 40})`);
  // Con variables del tema (no colores fijos) para que siga la paleta personalizada
  const velo = useTransform(scrollY, [0, 64], [0, 72]);
  const backgroundColor = useTransform(velo, (v) => `color-mix(in srgb, var(--color-canvas) ${v}%, transparent)`);
  const lineaOpacidad = useTransform(scrollY, [0, 64], [0, 100]);
  const borde = useTransform(lineaOpacidad, (v) => `color-mix(in srgb, var(--color-line) ${v}%, transparent)`);
  return (
    <motion.header
      style={{ backdropFilter, WebkitBackdropFilter: backdropFilter, backgroundColor, borderColor: borde }}
      className={cn("sticky top-0 z-30 border-b", className)}
    >
      {children}
    </motion.header>
  );
}
