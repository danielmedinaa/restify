"use client";

import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/cn";
import { smooth } from "@/lib/motion";

const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
// Alto de cada renglón del odómetro. Gagalin tiene glifos más altos que 1em: con
// renglones de 1em se asomarían los dígitos vecinos.
const ROW = 1.25;
const INSTANT = { duration: 0 };

/**
 * Odómetro: cada dígito gira hasta su valor. Recibe el texto ya formateado
 * ("1.234,50") y anima solo los caracteres numéricos, alineados desde la derecha
 * para que unidades con unidades giren juntas cuando cambia la longitud.
 *
 * El marcado es siempre el mismo: con movimiento reducido solo cambia la
 * transición. Si cambiara la estructura, el HTML del servidor (que no conoce la
 * preferencia) no coincidiría con el del cliente.
 */
export function NumberRoll({ value, className }: { value: string; className?: string }) {
  const reduce = useReducedMotion();
  const chars = value.split("");
  return (
    <span className={cn("inline-flex items-start tabular", className)} style={{ lineHeight: `${ROW}em` }}>
      <span className="sr-only">{value}</span>
      {chars.map((ch, i) => {
        const key = chars.length - i; // posición desde la derecha
        const digit = DIGITS.indexOf(ch);
        if (digit === -1) {
          return (
            <span key={key} aria-hidden style={{ lineHeight: `${ROW}em` }}>
              {ch}
            </span>
          );
        }
        return (
          <span key={key} aria-hidden className="relative inline-block overflow-hidden" style={{ height: `${ROW}em`, lineHeight: `${ROW}em` }}>
            <span className="invisible">0</span>
            <motion.span
              className="absolute inset-x-0 top-0 flex flex-col"
              initial={false}
              animate={{ y: `${-digit * ROW}em` }}
              transition={reduce ? INSTANT : smooth}
            >
              {DIGITS.map((d) => (
                <span key={d} className="text-center" style={{ height: `${ROW}em` }}>
                  {d}
                </span>
              ))}
            </motion.span>
          </span>
        );
      })}
    </span>
  );
}
