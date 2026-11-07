"use client";

import { motion } from "motion/react";
import { useId, useRef } from "react";
import { cn } from "@/lib/cn";
import { snappy } from "@/lib/motion";

export interface SegmentedOption<T extends string> {
  value: T;
  label: React.ReactNode;
}

export interface SegmentedProps<T extends string> {
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "md";
  className?: string;
}

/** Radiogroup con indicador que se desliza. Flechas para moverse, como un radio nativo. */
export function Segmented<T extends string>({ label, options, value, onChange, size = "md", className }: SegmentedProps<T>) {
  const group = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (from: number, delta: number) => {
    const next = (from + delta + options.length) % options.length;
    const option = options[next];
    if (!option) return;
    onChange(option.value);
    refs.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex w-fit rounded-control bg-wash p-1", className)}>
      {options.map((opt, i) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(opt.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowDown") (e.preventDefault(), move(i, 1));
              if (e.key === "ArrowLeft" || e.key === "ArrowUp") (e.preventDefault(), move(i, -1));
            }}
            className={cn(
              "relative rounded-[7px] font-medium transition-colors",
              size === "sm" ? "h-7 px-2.5 text-sm" : "h-9 px-3.5 text-base",
              active ? "text-ink" : "text-fg-2 hover:text-fg",
            )}
          >
            {active && (
              <motion.span
                layoutId={`seg-${group}`}
                transition={snappy}
                className="absolute inset-0 rounded-[7px] bg-paper"
                aria-hidden
              />
            )}
            <span className="relative">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
