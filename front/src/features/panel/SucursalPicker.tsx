"use client";

import * as DM from "@radix-ui/react-dropdown-menu";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/cn";
import { useSucursal } from "./sucursal";

export const menuContent =
  "z-50 min-w-[220px] rounded-control bg-overlay/95 p-1.5 shadow-float backdrop-blur-xl outline-none";
export const menuItem =
  "flex h-9 cursor-pointer select-none items-center justify-between gap-3 rounded-[7px] px-2.5 text-base text-fg-2 outline-none data-[highlighted]:bg-wash-strong data-[highlighted]:text-fg";

export function SucursalPicker({ className }: { className?: string }) {
  const { sucursales, actual, cambiar } = useSucursal();
  if (!actual) return <span className={cn("text-sm text-fg-3", className)}>Sin sucursal</span>;
  if (sucursales.length === 1) {
    return (
      <div className={cn("flex flex-col px-3", className)}>
        <span className="eyebrow">Sucursal</span>
        <span className="truncate text-base font-medium">{actual.nombre}</span>
      </div>
    );
  }
  return (
    <DM.Root>
      <DM.Trigger
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-control px-3 py-1.5 text-left transition-colors hover:bg-wash data-[state=open]:bg-wash",
          className,
        )}
      >
        <span className="flex min-w-0 flex-col">
          <span className="eyebrow">Sucursal</span>
          <span className="truncate text-base font-medium">{actual.nombre}</span>
        </span>
        <ChevronsUpDown size={16} strokeWidth={1.5} className="shrink-0 text-fg-3" aria-hidden />
      </DM.Trigger>
      <DM.Portal>
        <DM.Content align="start" sideOffset={6} className={menuContent}>
          <DM.RadioGroup value={String(actual.id)} onValueChange={(v) => cambiar(Number(v))}>
            {sucursales.map((s) => (
              <DM.RadioItem key={s.id} value={String(s.id)} className={menuItem}>
                {s.nombre}
                <DM.ItemIndicator>
                  <Check size={16} strokeWidth={1.5} aria-hidden />
                </DM.ItemIndicator>
              </DM.RadioItem>
            ))}
          </DM.RadioGroup>
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}
