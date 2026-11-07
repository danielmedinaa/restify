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
  const backgroundColor = useTransform(scrollY, [0, 64], ["rgb(26 24 25 / 0)", "rgb(26 24 25 / 0.72)"]);
  const borderColor = useTransform(scrollY, [0, 64], ["rgb(255 255 255 / 0)", "rgb(255 255 255 / 0.1)"]);
  return (
    <motion.header
      style={{ backdropFilter, WebkitBackdropFilter: backdropFilter, backgroundColor, borderColor }}
      className={cn("sticky top-0 z-30 border-b", className)}
    >
      {children}
    </motion.header>
  );
}
