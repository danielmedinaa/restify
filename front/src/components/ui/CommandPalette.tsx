"use client";

import * as RD from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Search } from "lucide-react";
import { useEffect } from "react";
import { fade, snappy } from "@/lib/motion";

export interface CommandItem {
  id: string;
  label: string;
  group: string;
  hint?: string;
  keywords?: string[];
  onSelect: () => void;
}

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: CommandItem[];
  /** Se llama mientras se escribe, para búsquedas remotas (clientes, comandas). */
  onQueryChange?: (q: string) => void;
}

/** ⌘K / Ctrl+K desde cualquier parte del panel. */
export function useCommandHotkey(toggle: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
}

export function CommandPalette({ open, onOpenChange, items, onQueryChange }: CommandPaletteProps) {
  const reduce = useReducedMotion();
  const groups = [...new Set(items.map((i) => i.group))];
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
            <div className="pointer-events-none fixed inset-0 z-50 flex justify-center px-4 pt-[14vh]">
              <RD.Content asChild forceMount>
                <motion.div
                  initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={reduce ? fade : snappy}
                  className="pointer-events-auto h-fit w-full max-w-xl overflow-hidden rounded-sheet bg-overlay/90 shadow-float backdrop-blur-xl outline-none"
                >
                  <RD.Title className="sr-only">Buscar o ejecutar</RD.Title>
                  <RD.Description className="sr-only">Escribe para buscar comandas, mesas, clientes o acciones</RD.Description>
                  <Command label="Paleta de comandos" loop>
                    <div className="flex items-center gap-3 border-b border-line px-5">
                      <Search size={18} strokeWidth={1.5} className="text-fg-3" aria-hidden />
                      <Command.Input
                        autoFocus
                        onValueChange={onQueryChange}
                        placeholder="Mesa 4, comanda 128, cobrar…"
                        className="h-14 w-full bg-transparent text-lead text-fg outline-none placeholder:text-fg-4 focus-visible:outline-none"
                      />
                      <kbd className="rounded border border-line px-1.5 py-0.5 text-sm text-fg-3">esc</kbd>
                    </div>
                    <Command.List className="max-h-[50vh] overflow-y-auto overscroll-contain p-2">
                      <Command.Empty className="px-3 py-8 text-center text-base text-fg-3">Nada con ese nombre.</Command.Empty>
                      {groups.map((group) => (
                        <Command.Group
                          key={group}
                          heading={group}
                          className="[&_[cmdk-group-heading]]:eyebrow [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3"
                        >
                          {items
                            .filter((i) => i.group === group)
                            .map((item) => (
                              <Command.Item
                                key={item.id}
                                value={`${item.label} ${item.id}`}
                                keywords={item.keywords}
                                onSelect={() => {
                                  item.onSelect();
                                  onOpenChange(false);
                                }}
                                className="flex h-11 cursor-pointer items-center justify-between rounded-control px-3 text-base text-fg-2 data-[selected=true]:bg-wash-strong data-[selected=true]:text-fg"
                              >
                                <span>{item.label}</span>
                                {item.hint && <span className="text-sm text-fg-3">{item.hint}</span>}
                              </Command.Item>
                            ))}
                        </Command.Group>
                      ))}
                    </Command.List>
                  </Command>
                </motion.div>
              </RD.Content>
            </div>
          </RD.Portal>
        )}
      </AnimatePresence>
    </RD.Root>
  );
}
