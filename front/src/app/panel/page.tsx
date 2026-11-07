"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Money } from "@/components/ui/Money";
import { Loading, Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/Status";
import { can, useMe } from "@/features/auth/useMe";
import { AbrirComanda } from "@/features/comandas/AbrirComanda";
import { ESTADO_SALA, estadoSala, tituloComanda } from "@/features/comandas/estado";
import { useComandasAbiertas, useMesas } from "@/features/comandas/queries";
import { useSucursal } from "@/features/panel/sucursal";
import { cabe, huecoLibre, Plano, ubicada, type Celda } from "@/features/sala/Plano";
import { useEditarMesa, useUnirMesas, useZonaMutations, useZonas } from "@/features/sala/queries";
import { Dialog } from "@/components/ui/Dialog";
import { toast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import { describeError } from "@/lib/api/errors";
import type { ComandaResumen, Mesa } from "@/lib/api/schemas";

const SIN_ZONA = 0;

export default function SalaPage() {
  const { actual } = useSucursal();
  const { data: me } = useMe();
  const mesas = useMesas(actual?.id);
  const zonas = useZonas(actual?.id);
  const abiertas = useComandasAbiertas(actual?.id);
  const editar = useEditarMesa(actual?.id);
  const zonaMut = useZonaMutations(actual?.id);
  const { unir, separar } = useUnirMesas(actual?.id);
  const [editando, setEditando] = useState(false);
  const [uniendo, setUniendo] = useState(false);
  const [seleccion, setSeleccion] = useState<number[]>([]);
  const [activaId, setActivaId] = useState<number | null>(null);
  const [zonaId, setZonaId] = useState<number>(SIN_ZONA);
  const [dialogoZona, setDialogoZona] = useState<{ id: number | null; nombre: string } | null>(null);
  const [abrir, setAbrir] = useState<{ mesa: Mesa | null } | null>(null);

  const porMesa = useMemo(() => {
    const m = new Map<number, ComandaResumen>();
    for (const c of abiertas.data ?? []) if (c.mesa_id != null) m.set(c.mesa_id, c);
    return m;
  }, [abiertas.data]);
  const paraLlevar = (abiertas.data ?? []).filter((c) => c.mesa_id == null);

  const lista = mesas.data ?? [];
  const listaZonas = (zonas.data ?? []).filter((z) => z.activa);
  const haySinZona = lista.some((m) => m.zona_id == null || !listaZonas.some((z) => z.id === m.zona_id));
  // Pestaña visible: la elegida si existe; si no, la primera zona
  const zonaActual = zonaId !== SIN_ZONA && listaZonas.some((z) => z.id === zonaId) ? zonaId : (listaZonas[0]?.id ?? SIN_ZONA);

  const enZona = (m: Mesa) => (zonaActual === SIN_ZONA ? m.zona_id == null || !listaZonas.some((z) => z.id === m.zona_id) : m.zona_id === zonaActual);
  const deLaZona = lista.filter(enZona);
  const ocupadas = lista.filter((m) => m.ocupada || porMesa.has(m.id)).length;
  const activa = lista.find((m) => m.id === activaId) ?? null;
  const [resaltadaId, setResaltadaId] = useState<number | null>(null);
  const resaltada = lista.find((m) => m.id === resaltadaId) ?? null;

  if (!can(me, "mesas") && !can(me, "comandas")) {
    return <EmptyState title="Sin acceso" description="Tu rol no puede ver la sala. Pídele acceso a un administrador." />;
  }

  const puedeEditar = can(me, "mesas", "editar");
  const puedeAbrir = can(me, "comandas", "crear");

  function moverMesa(mesa: Mesa, celda: Celda) {
    const x = Math.min(Math.max(0, celda.x), 12 - mesa.ancho);
    const y = Math.max(0, celda.y);
    if (x === mesa.pos_x && y === mesa.pos_y) return;
    if (!cabe(lista.filter(enZona), mesa, x, y)) return toast({ title: "Ahí ya hay otra mesa", tone: "warn" });
    editar.mutate({ id: mesa.id, pos_x: x, pos_y: y });
  }

  function ubicarAqui(mesa: Mesa) {
    const zona = zonaActual === SIN_ZONA ? null : zonaActual;
    const otras = lista.filter((m) => m.id !== mesa.id && enZona(m));
    const c = huecoLibre(otras, mesa);
    editar.mutate({ id: mesa.id, pos_x: c.x, pos_y: c.y, zona_id: zona });
  }

  /** Cambia el tamaño sin pisar a las vecinas. */
  function tamano(mesa: Mesa, ancho: number, alto: number) {
    ancho = Math.min(8, Math.max(1, ancho));
    alto = Math.min(8, Math.max(1, alto));
    const prueba = { ...mesa, ancho, alto };
    if (ubicada(mesa) && !cabe(lista.filter(enZona), prueba, mesa.pos_x, mesa.pos_y)) return toast({ title: "No cabe: hay otra mesa al lado", tone: "warn" });
    editar.mutate({ id: mesa.id, ancho, alto });
  }

  function alSeleccionar(m: Mesa) {
    if (editando) return setActivaId((a) => (a === m.id ? null : m.id));
    if (uniendo) return setSeleccion((s) => (s.includes(m.id) ? s.filter((i) => i !== m.id) : [...s, m.id]));
    setResaltadaId((r) => (r === m.id ? null : m.id));
  }

  /** Estado visible de una mesa (una unida toma el de su principal). */
  function estadoDe(m: Mesa) {
    const c = porMesa.get(m.unida_a_id ?? m.id);
    if (!c && m.ocupada) return { label: "Ocupada", tone: "neutral" as const, comandaId: m.comanda_abierta_id };
    const e = ESTADO_SALA[c ? estadoSala(c) : "libre"];
    return { label: e.label, tone: e.tone, comandaId: c?.id ?? m.comanda_abierta_id };
  }

  function terminarUnion() {
    setUniendo(false);
    setSeleccion([]);
  }

  const [principalId, ...otrasIds] = seleccion;
  const principal = lista.find((m) => m.id === principalId);
  const otras = otrasIds.map((id) => lista.find((m) => m.id === id)).filter((m): m is Mesa => !!m);
  const bloqueadas = otras.filter((m) => m.ocupada && !m.unida_a_id);
  const unidoSeleccionado = seleccion.length === 1 && principal && (principal.unida_a_id != null || lista.some((m) => m.unida_a_id === principal.id));

  return (
    <>
      <PageHeader
        eyebrow={mesas.data ? `${actual?.nombre} · ${ocupadas} de ${lista.length} ocupadas` : actual?.nombre}
        title="Sala"
        actions={
          editando ? (
            <Button onClick={() => (setEditando(false), setActivaId(null))}>Listo</Button>
          ) : uniendo ? (
            <Button variant="ghost" onClick={terminarUnion}>
              Cancelar
            </Button>
          ) : (
            <>
              {puedeEditar && lista.length > 0 && (
                <Button variant="ghost" onClick={() => setEditando(true)}>
                  Editar plano
                </Button>
              )}
              {puedeEditar && lista.length > 1 && (
                <Button variant="ghost" onClick={() => setUniendo(true)}>
                  Unir mesas
                </Button>
              )}
              {puedeAbrir && (
                <Button variant="line" onClick={() => setAbrir({ mesa: null })}>
                  <Plus size={16} strokeWidth={1.5} aria-hidden /> Para llevar
                </Button>
              )}
            </>
          )
        }
      />

      {editando && (
        <p className="-mt-6 mb-6 max-w-xl text-base text-fg-2">
          Arrastra cada mesa a su lugar; toca una para cambiar su forma, tamaño o zona. Se guarda al instante para todos.
        </p>
      )}
      {uniendo && (
        <p className="-mt-6 mb-6 max-w-xl text-base text-fg-2">
          Toca primero la mesa principal y luego las que se le suman. Toca una mesa ya unida para separarla.
        </p>
      )}

      {(listaZonas.length > 0 || haySinZona || editando) && (
        <div className="mb-8 flex flex-wrap items-center gap-2" role="tablist" aria-label="Zonas">
          {listaZonas.map((z) => (
            <button key={z.id} role="tab" aria-selected={zonaActual === z.id} onClick={() => setZonaId(z.id)} className={cn("rounded-full px-4 py-2 text-base transition-colors", zonaActual === z.id ? "bg-paper text-ink" : "bg-wash text-fg-2 hover:text-fg")}>
              {z.nombre}
            </button>
          ))}
          {haySinZona && (listaZonas.length > 0 || editando) && (
            <button role="tab" aria-selected={zonaActual === SIN_ZONA} onClick={() => setZonaId(SIN_ZONA)} className={cn("rounded-full px-4 py-2 text-base transition-colors", zonaActual === SIN_ZONA ? "bg-paper text-ink" : "bg-wash text-fg-3 hover:text-fg")}>
              Sin zona
            </button>
          )}
          {editando && (
            <>
              <Button size="sm" variant="ghost" onClick={() => setDialogoZona({ id: null, nombre: "" })}>
                <Plus size={14} strokeWidth={1.5} aria-hidden /> Zona
              </Button>
              {zonaActual !== SIN_ZONA && (
                <>
                  <Button size="sm" variant="ghost" onClick={() => setDialogoZona({ id: zonaActual, nombre: listaZonas.find((z) => z.id === zonaActual)?.nombre ?? "" })}>
                    Renombrar
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => confirm("¿Eliminar esta zona? Sus mesas quedan sin zona.") && zonaMut.eliminar.mutate(zonaActual)}>
                    Eliminar
                  </Button>
                </>
              )}
            </>
          )}
        </div>
      )}

      {editando && activa && (
        <div className="mb-6 flex flex-wrap items-end gap-x-6 gap-y-3 rounded-sheet bg-sunken p-4">
          <span className="font-display text-display-s leading-none">{activa.nombre}</span>
          <label className="flex flex-col gap-1 text-xs text-fg-3">
            Forma
            <select value={activa.forma} onChange={(e) => editar.mutate({ id: activa.id, forma: e.target.value as Mesa["forma"] })} className="h-9 rounded-control bg-wash px-2 text-base text-fg outline-none [&>option]:bg-overlay">
              <option value="cuadrada">Cuadrada</option>
              <option value="redonda">Redonda</option>
              <option value="rectangular">Rectangular</option>
            </select>
          </label>
          <Paso label="Ancho" valor={activa.ancho} onCambiar={(v) => tamano(activa, v, activa.alto)} />
          <Paso label="Alto" valor={activa.alto} onCambiar={(v) => tamano(activa, activa.ancho, v)} />
          {listaZonas.length > 0 && (
            <label className="flex flex-col gap-1 text-xs text-fg-3">
              Zona
              <select
                value={activa.zona_id ?? ""}
                onChange={(e) => {
                  const z = e.target.value ? Number(e.target.value) : null;
                  const hueco = huecoLibre(lista.filter((m) => m.id !== activa.id && m.zona_id === z), activa);
                  editar.mutate({ id: activa.id, zona_id: z, pos_x: hueco.x, pos_y: hueco.y });
                  setZonaId(z ?? SIN_ZONA);
                }}
                className="h-9 rounded-control bg-wash px-2 text-base text-fg outline-none [&>option]:bg-overlay"
              >
                <option value="">Sin zona</option>
                {listaZonas.map((z) => (
                  <option key={z.id} value={z.id}>
                    {z.nombre}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Button size="sm" variant="ghost" onClick={() => (editar.mutate({ id: activa.id, pos_x: null, pos_y: null }), setActivaId(null))}>
            Quitar del plano
          </Button>
        </div>
      )}

      <div className="grid gap-16 min-[1600px]:grid-cols-[1fr_280px]">
        <section aria-label="Plano de mesas" className="min-w-0">
          {mesas.isPending ? (
            <Loading label="Cargando mesas">
              <div className="grid grid-cols-2 gap-x-6 gap-y-10 tablet:grid-cols-4 desk:grid-cols-6">
                {Array.from({ length: 12 }, (_, i) => (
                  <div key={i} className="flex flex-col gap-3 p-3">
                    <Skeleton className="h-10 w-16" />
                    <Skeleton className="h-px w-full" />
                    <Skeleton className="h-3 w-20" />
                  </div>
                ))}
              </div>
            </Loading>
          ) : mesas.isError ? (
            <EmptyState title="No se pudo cargar la sala" description={describeError(mesas.error).title} />
          ) : lista.length === 0 ? (
            <EmptyState title="Sin mesas" description="Esta sucursal todavía no tiene mesas. Se crean en Administración → Mesas y QR." />
          ) : (
            <>
              <ul className="mb-5 flex flex-wrap gap-2" aria-label="Mesas">
                {deLaZona.map((m) => {
                  const e = estadoDe(m);
                  const marcada = editando ? activaId === m.id : uniendo ? seleccion.includes(m.id) : resaltadaId === m.id;
                  return (
                    <li key={m.id}>
                      <button
                        type="button"
                        aria-pressed={marcada}
                        onClick={() => alSeleccionar(m)}
                        className={cn(
                          "flex items-center gap-2 rounded-full px-3.5 py-1.5 text-base ring-1 ring-inset transition-colors",
                          marcada ? "bg-paper text-ink ring-paper" : "bg-wash text-fg-2 ring-line hover:text-fg",
                        )}
                      >
                        <StatusDot tone={e.tone}>
                          <span className="sr-only">{e.label}</span>
                        </StatusDot>
                        {m.nombre}
                      </button>
                    </li>
                  );
                })}
              </ul>
              {resaltada && !editando && !uniendo && (
                <div className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-sheet bg-sunken px-5 py-3">
                  <span className="font-display text-display-s leading-none">{resaltada.nombre}</span>
                  <StatusDot tone={estadoDe(resaltada).tone}>{estadoDe(resaltada).label}</StatusDot>
                  {resaltada.capacidad && <span className="text-sm text-fg-3">{resaltada.capacidad} puestos</span>}
                  {resaltada.unida_a_id && <span className="text-sm text-fg-3">Unida a {lista.find((m) => m.id === resaltada.unida_a_id)?.nombre}</span>}
                  <span className="ml-auto flex gap-2">
                    {estadoDe(resaltada).comandaId ? (
                      <Link href={`/panel/comandas/${estadoDe(resaltada).comandaId}`} className="inline-flex h-10 items-center rounded-control bg-paper px-4 text-base font-medium text-ink">
                        Abrir comanda
                      </Link>
                    ) : (
                      puedeAbrir && <Button onClick={() => setAbrir({ mesa: resaltada })}>Nueva comanda</Button>
                    )}
                    <Button variant="ghost" onClick={() => setResaltadaId(null)}>
                      Cerrar
                    </Button>
                  </span>
                </div>
              )}
              <Plano
                mesas={deLaZona}
                todas={lista}
                comandas={porMesa}
                editando={editando}
                uniendo={uniendo}
                seleccion={seleccion}
                seleccionada={editando ? activaId : resaltadaId}
                onSeleccionar={alSeleccionar}
                onMover={moverMesa}
                onAbrirLibre={(m) => puedeAbrir && setAbrir({ mesa: m })}
              />
              {editando && deLaZona.some((m) => !ubicada(m)) && (
                <div className="mt-8 flex flex-col gap-3">
                  <span className="eyebrow">Sin ubicar · toca para ponerlas en el plano</span>
                  <div className="flex flex-wrap gap-2">
                    {deLaZona.filter((m) => !ubicada(m)).map((m) => (
                      <Button key={m.id} size="sm" variant="line" onClick={() => ubicarAqui(m)}>
                        {m.nombre}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              {editando && lista.some((m) => !enZona(m) && !ubicada(m)) && zonaActual !== SIN_ZONA && (
                <div className="mt-6 flex flex-col gap-3">
                  <span className="eyebrow">De otras zonas y sin ubicar</span>
                  <div className="flex flex-wrap gap-2">
                    {lista.filter((m) => !enZona(m) && !ubicada(m)).map((m) => (
                      <Button key={m.id} size="sm" variant="ghost" onClick={() => ubicarAqui(m)}>
                        {m.nombre}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </section>

        {can(me, "comandas") && !editando && (
          <aside aria-labelledby="llevar-t" className="flex flex-col gap-4">
            <h2 id="llevar-t" className="eyebrow">
              Para llevar · {paraLlevar.length}
            </h2>
            {paraLlevar.length === 0 ? (
              <p className="border-t border-line pt-4 text-sm text-fg-3">Nada pendiente.</p>
            ) : (
              <ul className="flex flex-col">
                {paraLlevar.map((c) => {
                  const e = ESTADO_SALA[estadoSala(c)];
                  return (
                    <li key={c.id}>
                      <Link
                        href={`/panel/comandas/${c.id}`}
                        className="-mx-3 flex flex-col gap-1.5 rounded-control border-t border-line px-3 py-3.5 transition-colors hover:bg-wash"
                      >
                        <span className="flex items-baseline justify-between gap-3">
                          <span className="truncate text-title font-medium">{tituloComanda(c)}</span>
                          <Money value={c.total} className="text-sm text-fg-2" />
                        </span>
                        <StatusDot tone={e.tone}>{e.label}</StatusDot>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>
        )}
      </div>

      {uniendo && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-canvas/80 px-6 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 backdrop-blur-xl">
          <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-4">
            <span className="min-w-0 flex-1 text-base text-fg-2">
              {principal ? (
                <>
                  <strong className="text-fg">{principal.nombre}</strong>
                  {otras.length > 0 ? ` + ${otras.map((m) => m.nombre).join(", ")}` : " (principal)"}
                  {bloqueadas.length > 0 && <span className="block text-sm text-warn">{bloqueadas.map((m) => m.nombre).join(", ")} tiene una comanda abierta: ciérrala antes.</span>}
                </>
              ) : (
                "Elige las mesas"
              )}
            </span>
            {unidoSeleccionado && principal && (
              <Button variant="line" disabled={separar.isPending} onClick={() => separar.mutate(principal.id, { onSuccess: terminarUnion })}>
                Separar
              </Button>
            )}
            <Button
              disabled={!principal || otras.length === 0 || bloqueadas.length > 0 || unir.isPending}
              onClick={() => principal && unir.mutate({ principal: principal.id, otras: otras.map((m) => m.id) }, { onSuccess: terminarUnion })}
            >
              Unir mesas
            </Button>
          </div>
        </div>
      )}

      <Dialog
        open={dialogoZona !== null}
        onOpenChange={(o) => !o && setDialogoZona(null)}
        title={dialogoZona?.id ? "Renombrar zona" : "Nueva zona"}
        description="Salón, Terraza, Piso 2… cada zona tiene su propio plano."
        actions={
          <>
            <Button variant="ghost" onClick={() => setDialogoZona(null)}>
              Volver
            </Button>
            <Button
              disabled={!dialogoZona?.nombre.trim()}
              onClick={() => {
                if (!dialogoZona) return;
                const nombre = dialogoZona.nombre.trim();
                const hecho = { onSuccess: (z?: { id: number }) => (z && dialogoZona.id == null && setZonaId(z.id), setDialogoZona(null)) };
                if (dialogoZona.id) zonaMut.renombrar.mutate({ id: dialogoZona.id, nombre }, hecho);
                else zonaMut.crear.mutate(nombre, hecho);
              }}
            >
              Guardar
            </Button>
          </>
        }
      >
        <input
          autoFocus
          value={dialogoZona?.nombre ?? ""}
          onChange={(e) => setDialogoZona((d) => d && { ...d, nombre: e.target.value })}
          maxLength={60}
          aria-label="Nombre de la zona"
          placeholder="Terraza"
          className="h-11 w-full border-b border-line-strong bg-transparent text-lead outline-none placeholder:text-fg-4 focus:border-paper"
        />
      </Dialog>

      {actual && (
        <AbrirComanda open={abrir !== null} onOpenChange={(o) => !o && setAbrir(null)} sucursalId={actual.id} mesa={abrir?.mesa ?? null} />
      )}
    </>
  );
}

function Paso({ label, valor, onCambiar }: { label: string; valor: number; onCambiar: (v: number) => void }) {
  return (
    <div className="flex flex-col gap-1 text-xs text-fg-3">
      {label}
      <span className="flex items-center gap-1">
        <button type="button" aria-label={`Menos ${label.toLowerCase()}`} onClick={() => onCambiar(valor - 1)} className="grid size-9 place-items-center rounded-control bg-wash text-fg hover:bg-wash-strong">
          −
        </button>
        <span className="w-6 text-center text-base tabular text-fg">{valor}</span>
        <button type="button" aria-label={`Más ${label.toLowerCase()}`} onClick={() => onCambiar(valor + 1)} className="grid size-9 place-items-center rounded-control bg-wash text-fg hover:bg-wash-strong">
          +
        </button>
      </span>
    </div>
  );
}
