"use client";

import { motion } from "motion/react";
import { Logo } from "@/components/ui/Logo";

/**
 * El sello gira muy despacio, como un disco: una vuelta por minuto. Con
 * movimiento reducido, MotionConfig (reducedMotion="user") lo deja quieto.
 */
export function RotatingSeal({ size }: { size: number }) {
  return (
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ duration: 60, ease: "linear", repeat: Infinity }}
      style={{ width: size, height: size }}
      className="grid place-items-center"
    >
      <Logo size={size} />
    </motion.div>
  );
}
