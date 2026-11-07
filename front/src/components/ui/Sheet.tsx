"use client";

import * as RD from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { fade, sheet } from "@/lib/motion";

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  side?: "bottom" | "right" | "left";
  children: React.ReactNode;
  footer?: React.ReactNode;
}

/**
 * Panel deslizable con el fondo desenfocado. Abajo en móvil (se descarta
 * arrastrando hacia abajo), a la derecha en el panel de escritorio y a la
 * izquierda para la navegación en pantallas chicas.
 */
export function Sheet({ open, onOpenChange, title, description, side = "bottom", children, footer }: SheetProps) {
  const reduce = useReducedMotion();
  const bottom = side === "bottom";
  const hidden = reduce ? { opacity: 0 } : bottom ? { y: "100%" } : { x: side === "left" ? "-100%" : "100%" };
  const shown = reduce ? { opacity: 1 } : bottom ? { y: 0 } : { x: 0 };

  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <RD.Portal forceMount>
            <RD.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-40 bg-scrim backdrop-blur-[8px]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={fade}
              />
            </RD.Overlay>
            <RD.Content asChild forceMount>
              <motion.div
                initial={hidden}
                animate={shown}
                exit={hidden}
                transition={reduce ? fade : sheet}
                drag={bottom && !reduce ? "y" : false}
                dragConstraints={{ top: 0, bottom: 0 }}
                dragElastic={{ top: 0, bottom: 0.6 }}
                onDragEnd={(_, info) => {
                  if (info.offset.y > 120 || info.velocity.y > 600) onOpenChange(false);
                }}
                className={cn(
                  "fixed z-50 flex flex-col bg-overlay/90 shadow-float backdrop-blur-xl outline-none",
                  bottom
                    ? "inset-x-0 bottom-0 max-h-[92dvh] rounded-t-sheet pb-[env(safe-area-inset-bottom)]"
                    : side === "left"
                      ? "inset-y-0 left-0 w-[min(320px,88vw)] border-r border-line"
                      : "inset-y-0 right-0 w-full max-w-[480px] border-l border-line",
                )}
              >
                {bottom && <span aria-hidden className="mx-auto mt-3 h-1 w-10 shrink-0 rounded-full bg-line-strong" />}
                <header className="flex items-start justify-between gap-4 px-6 pb-4 pt-5">
                  <div className="flex flex-col gap-1">
                    <RD.Title className="font-display text-display-s">{title}</RD.Title>
                    {description ? (
                      <RD.Description className="text-base text-fg-2">{description}</RD.Description>
                    ) : (
                      <RD.Description className="sr-only">{title}</RD.Description>
                    )}
                  </div>
                  <RD.Close
                    className="-mr-2 grid size-10 place-items-center rounded-control text-fg-2 transition-colors hover:bg-wash hover:text-fg"
                    aria-label="Cerrar"
                  >
                    <X size={20} strokeWidth={1.5} />
                  </RD.Close>
                </header>
                <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 pb-6">{children}</div>
                {footer && <footer className="border-t border-line px-6 py-4">{footer}</footer>}
              </motion.div>
            </RD.Content>
          </RD.Portal>
        )}
      </AnimatePresence>
    </RD.Root>
  );
}
