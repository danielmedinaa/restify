"use client";

import * as DM from "@radix-ui/react-dropdown-menu";
import { LogOut, UserRound } from "lucide-react";
import Link from "next/link";
import type { Me } from "@/lib/api/schemas";
import { menuContent, menuItem } from "./SucursalPicker";

export function UserMenu({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const rol = me.es_superadmin ? "Superadmin" : (me.rol?.nombre ?? "Sin rol");
  return (
    <DM.Root>
      <DM.Trigger className="flex w-full items-center gap-3 rounded-control px-3 py-2 text-left transition-colors hover:bg-wash data-[state=open]:bg-wash">
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-wash-strong text-sm font-medium">
          {me.nombre.trim().charAt(0).toUpperCase()}
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-base font-medium">{me.nombre}</span>
          <span className="truncate text-sm text-fg-3">{rol}</span>
        </span>
      </DM.Trigger>
      <DM.Portal>
        <DM.Content side="top" align="start" sideOffset={6} className={menuContent}>
          <DM.Item asChild className={menuItem}>
            <Link href="/panel/cuenta">
              Mi cuenta <UserRound size={16} strokeWidth={1.5} aria-hidden />
            </Link>
          </DM.Item>
          <DM.Separator className="my-1 h-px bg-line" />
          <DM.Item className={menuItem} onSelect={onLogout}>
            Salir <LogOut size={16} strokeWidth={1.5} aria-hidden />
          </DM.Item>
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}
