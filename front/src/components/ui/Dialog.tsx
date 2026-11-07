"use client";

import * as RD from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { fade, smooth } from "@/lib/motion";

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}

/** Para confirmar algo que no se deshace. Lo demás va en Sheet. */
export function Dialog({ open, onOpenChange, title, description, children, actions }: DialogProps) {
  const reduce = useReducedMotion();
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
            <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center p-4">
              <RD.Content asChild forceMount>
                <motion.div
                  initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.98 }}
                  transition={reduce ? fade : smooth}
                  className="pointer-events-auto flex w-full max-w-md flex-col gap-4 rounded-sheet bg-overlay p-7 shadow-float outline-none"
                >
                  <RD.Title className="font-display text-display-s">{title}</RD.Title>
                  {description ? (
                    <RD.Description className="text-base text-fg-2">{description}</RD.Description>
                  ) : (
                    <RD.Description className="sr-only">{title}</RD.Description>
                  )}
                  {children}
                  {actions && <div className="flex justify-end gap-2 pt-2">{actions}</div>}
                </motion.div>
              </RD.Content>
            </div>
          </RD.Portal>
        )}
      </AnimatePresence>
    </RD.Root>
  );
}
