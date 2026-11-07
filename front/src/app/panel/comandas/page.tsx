"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Money } from "@/components/ui/Money";
import { Segmented } from "@/components/ui/Segmented";
import { Loading, Skeleton } from "@/components/ui/Skeleton";
import { ProgressLine, StatusDot } from "@/components/ui/Status";
import { can, useMe } from "@/features/auth/useMe";
import { AbrirComanda } from "@/features/comandas/AbrirComanda";
import { ESTADO_SALA, estadoSala, minutosDesde, progreso, tituloComanda, type EstadoSala } from "@/features/comandas/estado";
import { keys, useComandasAbiertas } from "@/features/comandas/queries";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { ComandaResumenOut, Pagina, type ComandaResumen } from "@/lib/api/schemas";
import { smooth } from "@/lib/motion";
import { useNow } from "@/lib/useNow";

type Vista = "abierta" | "cerrada" | "cancelada";
const URGENCIA: EstadoSala[] = ["por_aprobar", "por_servir", "por_cobrar", "en_cocina", "abierta"];
const PAGINA = 30;
const fecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export default function ComandasPage() {
  const { actual } = useSucursal();
  const { data: me } = useMe();
  const [vista, setVista] = useState<Vista>("abierta");
  const [abrir, setAbrir] = useState(false);

  if (!can(me, "comandas")) return <EmptyState title="Sin acceso" description="Tu rol no puede ver comandas." />;

  return (
    <>
      <PageHeader
        eyebrow={actual?.nombre}
        title="Comandas"
        actions={
          <>
            <Segmented
              label="Estado"
              value={vista}
              onChange={setVista}
              options={[
                { value: "abierta", label: "Abiertas" },
                { value: "cerrada", label: "Cerradas" },
                { value: "cancelada", label: "Canceladas" },
              ]}
            />
            {can(me, "comandas", "crear") && <Button onClick={() => setAbrir(true)}>Para llevar</Button>}
          </>
        }
      />
      {vista === "abierta" ? <Abiertas sucursalId={actual?.id} /> : <Historial key={vista} sucursalId={actual?.id} estado={vista} />}
      {actual && <AbrirComanda open={abrir} onOpenChange={setAbrir} sucursalId={actual.id} mesa={null} />}
    </>
  );
}

function Abiertas({ sucursalId }: { sucursalId: number | undefined }) {
  const abiertas = useComandasAbiertas(sucursalId);
  const ordenadas = useMemo(
    () =>
      [...(abiertas.data ?? [])].sort(
        (a, b) => URGENCIA.indexOf(estadoSala(a)) - URGENCIA.indexOf(estadoSala(b)) || a.created_at.localeCompare(b.created_at),
      ),
    [abiertas.data],
  );
  if (abiertas.isPending) return <ListaSkeleton />;
  if (abiertas.isError) return <EmptyState title={describeError(abiertas.error).title} description="" />;
  if (ordenadas.length === 0) {
    return <EmptyState title="Sala tranquila" description="No hay comandas abiertas. Las que lleguen por QR aparecen aquí al instante." />;
  }
  return (
    <ul className="flex flex-col">
      {ordenadas.map((c) => (
        <Fila key={c.id} c={c} viva />
      ))}
    </ul>
  );
}

function Historial({ sucursalId, estado }: { sucursalId: number | undefined; estado: "cerrada" | "cancelada" }) {
  const [offset, setOffset] = useState(0);
  const q = useQuery({
    queryKey: [...keys.historial(sucursalId, estado), offset],
    queryFn: () => api("/comandas", { query: { sucursal_id: sucursalId, estado, limite: PAGINA, offset }, schema: Pagina(ComandaResumenOut) }),
    enabled: sucursalId != null,
    placeholderData: keepPreviousData,
  });
  if (q.isPending) return <ListaSkeleton />;
  if (q.isError) return <EmptyState title={describeError(q.error).title} description="" />;
  if (q.data.total === 0) {
    return <EmptyState title="Nada aún" description={estado === "cerrada" ? "Las comandas cobradas aparecerán aquí." : "No hay comandas canceladas."} />;
  }
  const hasta = Math.min(offset + PAGINA, q.data.total);
  return (
    <div className="flex flex-col gap-8">
      <ul className="flex flex-col">
        {q.data.items.map((c) => (
          <Fila key={c.id} c={c} />
        ))}
      </ul>
      <div className="flex items-center justify-between text-sm text-fg-3">
        <span>
          {offset + 1}–{hasta} de {q.data.total}
        </span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGINA))}>
            Anteriores
          </Button>
          <Button size="sm" variant="ghost" disabled={hasta >= q.data.total} onClick={() => setOffset((o) => o + PAGINA)}>
            Siguientes
          </Button>
        </div>
      </div>
    </div>
  );
}

function Fila({ c, viva }: { c: ComandaResumen; viva?: boolean }) {
  const now = useNow();
  const e = viva ? ESTADO_SALA[estadoSala(c)] : { label: c.estado === "cerrada" ? "Cobrada" : "Cancelada", tone: "muted" as const };
  const p = progreso(c);
  return (
    <motion.li layout transition={smooth}>
      <Link
        href={`/panel/comandas/${c.id}`}
        className="-mx-3 grid grid-cols-[1fr_auto] items-center gap-x-6 gap-y-2 rounded-control border-t border-line px-3 py-4 transition-colors hover:bg-wash tablet:grid-cols-[minmax(0,1fr)_160px_120px_100px]"
      >
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-title font-medium">{tituloComanda(c)}</span>
          <span className="text-sm text-fg-3">
            #{c.id} · {c.origen === "qr" ? "QR" : "Caja"}
            {c.mesa && c.nombre_cliente ? ` · ${c.nombre_cliente}` : ""}
          </span>
        </span>
        <span className="hidden flex-col gap-2 tablet:flex">
          <StatusDot tone={e.tone}>{e.label}</StatusDot>
          {viva && <ProgressLine value={p.hechos} max={p.total} tone={e.tone} label={`Platos listos de ${tituloComanda(c)}`} />}
        </span>
        <span className="hidden text-sm tabular text-fg-3 tablet:block">
          {viva ? (now !== null ? `hace ${minutosDesde(c.created_at, now)} min` : "") : fecha.format(new Date(c.created_at))}
        </span>
        <Money value={c.total} className="justify-end text-base" />
      </Link>
    </motion.li>
  );
}

function ListaSkeleton() {
  return (
    <Loading label="Cargando comandas">
      <div className="flex flex-col">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex items-center justify-between border-t border-line py-5">
            <div className="flex flex-col gap-2">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-3 w-20" />
            </div>
            <Skeleton className="h-5 w-16" />
          </div>
        ))}
      </div>
    </Loading>
  );
}
