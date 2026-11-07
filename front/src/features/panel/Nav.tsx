"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { snappy } from "@/lib/motion";
import { isActive, type NavGroup } from "./nav";

/** Lista de navegación. El ítem activo lleva una línea que se desliza entre ítems. */
export function Nav({ groups, onNavigate, idPrefix }: { groups: NavGroup[]; onNavigate?: () => void; idPrefix: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Principal" className="flex flex-col gap-6">
      {groups.map((g) => (
        <div key={g.label} className="flex flex-col gap-0.5">
          <span className="eyebrow px-3 pb-1.5">{g.label}</span>
          {g.items.map((item) => {
            const active = isActive(item.href, pathname);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex h-9 items-center gap-3 rounded-control px-3 text-base transition-colors",
                  active ? "text-fg" : "text-fg-2 hover:bg-wash hover:text-fg",
                )}
              >
                {active && (
                  <motion.span
                    layoutId={`${idPrefix}-nav-active`}
                    transition={snappy}
                    className="absolute inset-0 rounded-control bg-wash-strong"
                    aria-hidden
                  />
                )}
                <Icon size={18} strokeWidth={1.5} className="relative shrink-0" aria-hidden />
                <span className="relative">{item.label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
