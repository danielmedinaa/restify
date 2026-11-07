"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/cn";
import { snappy } from "@/lib/motion";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  /** Oculta la etiqueta visualmente (sigue disponible para lectores de pantalla). */
  hideLabel?: boolean;
  disabled?: boolean;
}

export function Switch({ checked, onCheckedChange, label, hideLabel, disabled }: SwitchProps) {
  return (
    <label className={cn("inline-flex items-center gap-3", disabled ? "opacity-40" : "cursor-pointer")}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          "flex h-6 w-10 shrink-0 items-center rounded-full p-0.5 transition-colors duration-200",
          checked ? "justify-end bg-paper" : "justify-start bg-wash-strong",
        )}
      >
        <motion.span
          layout
          transition={snappy}
          className={cn("size-5 rounded-full", checked ? "bg-ink" : "bg-fg-2")}
        />
      </button>
      <span className={cn("text-base", hideLabel && "sr-only")}>{label}</span>
    </label>
  );
}
