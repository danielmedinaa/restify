"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Menu, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useCommandHotkey } from "@/components/ui/CommandPalette";
import { EmptyState } from "@/components/ui/EmptyState";
import { Logo, Wordmark } from "@/components/ui/Logo";
import { Sheet } from "@/components/ui/Sheet";
import { Skeleton } from "@/components/ui/Skeleton";
import { StickyHeader } from "@/components/ui/StickyHeader";
import { Button } from "@/components/ui/Button";
import { can, useMe } from "@/features/auth/useMe";
import { ComandasLive } from "@/features/comandas/ComandasLive";
import { setUnauthorizedHandler } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { Me } from "@/lib/api/schemas";
import { RealtimeProvider } from "@/lib/realtime/RealtimeProvider";
import { LiveStatus } from "./LiveStatus";
import { Nav } from "./Nav";
import { PanelCommands } from "./PanelCommands";
import { navFor } from "./nav";
import { logout } from "./session";
import { AlertaSeguridad } from "./AlertaSeguridad";
import { ChatAyuda } from "./ChatAyuda";
import { StockAlerts } from "./StockAlerts";
import { SucursalPicker } from "./SucursalPicker";
import { SucursalProvider, useSucursal } from "./sucursal";
import { UserMenu } from "./UserMenu";

export function PanelShell({ initialSucursalId, children }: { initialSucursalId: number | null; children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  const me = useMe();

  // Si una llamada responde 401 (ni renovando el token), se vuelve al login
  useEffect(() => {
    setUnauthorizedHandler(() => {
      qc.clear();
      router.replace(`/login?motivo=expirada&next=${encodeURIComponent(pathname)}`);
    });
    return () => setUnauthorizedHandler(null);
  }, [qc, router, pathname]);

  if (me.isPending) return <ShellSkeleton />;
  if (me.isError) {
    const err = describeError(me.error);
    return (
      <main className="mx-auto max-w-3xl px-6 py-24">
        <EmptyState title={err.title} description={err.description ?? "Intenta de nuevo."} action={<Button onClick={() => void me.refetch()}>Reintentar</Button>} />
      </main>
    );
  }

  return (
    <SucursalProvider me={me.data} initialId={initialSucursalId}>
      <ShellWithSucursal me={me.data}>{children}</ShellWithSucursal>
    </SucursalProvider>
  );
}

function ShellWithSucursal({ me, children }: { me: Me; children: React.ReactNode }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { actual } = useSucursal();
  const [menuOpen, setMenuOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const groups = useMemo(() => navFor(me), [me]);

  const salir = useCallback(async () => {
    await logout();
    qc.clear();
    router.replace("/login");
  }, [qc, router]);

  const togglePalette = useCallback(() => setPaletteOpen((o) => !o), []);
  useCommandHotkey(togglePalette);

  return (
    <RealtimeProvider sucursalId={actual?.id ?? null}>
      <StockAlerts />
      <AlertaSeguridad />
      <ChatAyuda />
      {can(me, "comandas") && <ComandasLive />}
      <div className="desk:pl-[248px]">
        {/* Rail de escritorio */}
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col gap-6 border-r border-line px-3 pb-4 pt-6 desk:flex">
          <Link href="/panel" aria-label="Ir a la sala" className="self-start px-1">
            <Logo size={104} />
          </Link>
          <SucursalPicker />
          <SearchTrigger onClick={() => setPaletteOpen(true)} />
          {/* Solo la navegación hace scroll: el estado y el usuario quedan siempre a la vista */}
          <div className="scrollbar-none -mx-3 min-h-0 flex-1 overflow-y-auto px-3">
            <Nav groups={groups} idPrefix="rail" />
          </div>
          <div className="flex flex-col gap-3 border-t border-line pt-4">
            <LiveStatus className="px-3" />
            <UserMenu me={me} onLogout={() => void salir()} />
          </div>
        </aside>

        {/* Barra superior en tablet y móvil */}
        <StickyHeader className="desk:hidden">
          <div className="flex h-14 items-center gap-2 px-2 tablet:px-4">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Abrir menú"
              className="grid size-10 place-items-center rounded-control text-fg-2 hover:bg-wash hover:text-fg"
            >
              <Menu size={20} strokeWidth={1.5} />
            </button>
            <Wordmark className="text-[1.5rem]" />
            <span className="ml-2 hidden truncate text-sm text-fg-3 tablet:inline">{actual?.nombre}</span>
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-label="Buscar"
              className="ml-auto grid size-10 place-items-center rounded-control text-fg-2 hover:bg-wash hover:text-fg"
            >
              <Search size={20} strokeWidth={1.5} />
            </button>
          </div>
        </StickyHeader>

        <Sheet open={menuOpen} onOpenChange={setMenuOpen} side="left" title="Menú" footer={<UserMenu me={me} onLogout={() => void salir()} />}>
          <div className="-mx-3 flex flex-col gap-6">
            <SucursalPicker />
            <LiveStatus className="px-3" />
            <Nav groups={groups} idPrefix="sheet" onNavigate={() => setMenuOpen(false)} />
          </div>
        </Sheet>

        <main id="contenido" className="mx-auto w-full max-w-[1400px] px-4 pb-24 pt-8 tablet:px-8 desk:px-12 desk:pt-12">
          {actual ? (
            children
          ) : (
            <EmptyState
              title="Sin sucursal"
              description={
                me.es_superadmin
                  ? "Todavía no hay sucursales. Crea la primera desde Administración."
                  : "No tienes ninguna sucursal asignada. Pídele a un administrador que te asigne una."
              }
            />
          )}
        </main>
      </div>

      <PanelCommands
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        me={me}
        groups={groups}
        sucursalId={actual?.id}
        onLogout={() => void salir()}
      />
    </RealtimeProvider>
  );
}

function SearchTrigger({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-9 items-center gap-3 rounded-control border border-line px-3 text-base text-fg-3 transition-colors hover:border-line-strong hover:text-fg-2"
    >
      <Search size={16} strokeWidth={1.5} aria-hidden />
      <span className="flex-1 text-left">Buscar</span>
      <kbd className="text-sm">⌘K</kbd>
    </button>
  );
}

function ShellSkeleton() {
  return (
    <div className="desk:pl-[248px]" role="status" aria-busy>
      <span className="sr-only">Cargando el panel</span>
      <div className="fixed inset-y-0 left-0 hidden w-[248px] flex-col gap-6 border-r border-line px-6 py-6 desk:flex">
        <Skeleton className="h-7 w-28" />
        <Skeleton className="h-10 w-full" />
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-4 w-32" />
        ))}
      </div>
      <div className="mx-auto max-w-[1400px] px-4 pt-12 tablet:px-8 desk:px-12">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-4 h-14 w-64" />
      </div>
    </div>
  );
}
