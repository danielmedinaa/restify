"use client";

import { motion, type HTMLMotionProps } from "motion/react";
import { forwardRef } from "react";
import { cn } from "@/lib/cn";
import { snappy, tap } from "@/lib/motion";

type Variant = "primary" | "line" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-paper text-ink hover:bg-paper/90",
  line: "border border-line-strong text-fg hover:bg-wash",
  ghost: "text-fg-2 hover:text-fg hover:bg-wash",
  danger: "text-err hover:bg-wash",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-10 px-4 text-base gap-2",
  lg: "h-14 px-6 text-lead gap-2.5", // táctil: cocina y caja
};

export interface ButtonProps extends Omit<HTMLMotionProps<"button">, "children"> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, disabled, className, children, type = "button", ...props },
  ref,
) {
  const inactive = disabled || loading;
  return (
    <motion.button
      ref={ref}
      type={type}
      disabled={inactive}
      aria-busy={loading || undefined}
      whileTap={inactive ? undefined : tap}
      transition={snappy}
      className={cn(
        "relative inline-flex select-none items-center justify-center whitespace-nowrap rounded-control font-medium",
        "transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      <span className={cn("inline-flex items-center gap-[inherit] transition-opacity", loading && "opacity-0")}>
        {children}
      </span>
      {loading && (
        <span aria-hidden className="absolute inset-0 flex items-center justify-center gap-1">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="size-1 rounded-full bg-current"
              animate={{ opacity: [0.25, 1, 0.25] }}
              transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }}
            />
          ))}
        </span>
      )}
    </motion.button>
  );
});
