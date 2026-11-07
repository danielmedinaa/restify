"use client";

import { ChatPanel } from "@/features/chat/ChatPanel";
import { useChatStaff } from "@/features/chat/queries";
import * as DM from "@radix-ui/react-dropdown-menu";
import { Check, Copy, Ellipsis, Plus } from "lucide-react";
import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { z } from "zod";
import { api } from "@/lib/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Money } from "@/components/ui/Money";
import { Loading, Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/Status";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { menuContent, menuItem } from "@/features/panel/SucursalPicker";
import { describeError, type ErrorView } from "@/lib/api/errors";
import type { Comanda, EstadoItem, Item } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { fromPrincipal, isPositive } from "@/lib/money";
import { smooth } from "@/lib/motion";
import { useNow } from "@/lib/useNow";
import { AgregarPlatos } from "./AgregarPlatos";
import { CancelarComanda } from "./CancelarComanda";
import { EditarComanda } from "./EditarComanda";
import { ESTADO_ITEM, minutosDesde, tituloComanda } from "./estado";
import { principalDe, useComanda, useComandaAction, useMonedas } from "./queries";

const hora = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" });

const GRUPOS: { id: string; label: string; estados: EstadoItem[] }[] = [
  { id: "aprobar", label: "Por aprobar", estados: ["pendiente"] },
  { id: "servir", label: "Listos para servir", estados: ["listo"] },
  { id: "cocina", label: "En cocina", estados: ["en_cocina", "preparando"] },
  { id: "entregados", label: "Entregados", estados: ["entregado"] },
];

export function ComandaDetalle({ id }: { id: number }) {
  const comanda = useComanda(id);
  if (comanda.isPending) return <DetalleSkeleton />;
  if (comanda.isError) {
    const e = describeError(comanda.error);
    return <EmptyState title={e.title} description={e.description ?? "Revisa el número de comanda."} action={<Link href="/panel/comandas" className="text-fg underline underline-offset-4">Ver comandas</Link>} />;
  }
  return <Detalle c={comanda.data} />;
}

function Detalle({ c }: { c: Comanda }) {
  const { data: me } = useMe();
  const [agregar, setAgregar] = useState(false);
  const [editar, setEditar] = useState(false);
  // Cambia en cada apertura: el formulario se remonta con los datos al día
  const [editarKey, setEditarKey] = useState(0);
  const [cancelar, setCancelar] = useState(false);
  const [cortesiaItem, setCortesiaItem] = useState<Item | null>(null);
  const [motivoCortesia, setMotivoCortesia] = useState("");
  const cortesia = useComandaAction<{ id: number; cortesia: boolean; motivo?: string }>(
    c.id,
    ({ id, ...body }) => ({ path: `/items/${id}/cortesia`, method: "PUT", body }),
    {
      onSuccess: () => {
        setCortesiaItem(null);
        setMotivoCortesia("");
      },
    },
  );
  const [ingredientesItem, setIngredientesItem] = useState<Item | null>(null);
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [errorCocina, setErrorCocina] = useState<ErrorView | null>(null);

  const abierta = c.estado === "abierta";
  const editable = abierta && can(me, "comandas", "editar");
  const porGrupo = useMemo(() => {
    const m = new Map<string, Item[]>();
    for (const g of GRUPOS) m.set(g.id, c.items.filter((i) => g.estados.includes(i.estado)));
    return m;
  }, [c.items]);
  const cancelados = c.items.filter((i) => i.estado === "cancelado");
  const pendientes = porGrupo.get("aprobar") ?? [];
  const listos = porGrupo.get("servir") ?? [];

  const enviar = useComandaAction<number[] | null>(c.id, (ids) => ({ path: "/enviar-cocina", body: ids ? { item_ids: ids } : undefined }), {
    optimistic: (prev, ids) => ({
      ...prev,
      items: prev.items.map((i) =>
        i.estado === "pendiente" && (!ids || ids.includes(i.id)) ? { ...i, estado: "en_cocina", enviado_en: new Date().toISOString() } : i,
      ),
    }),
    onSuccess: () => {
      setSeleccion(new Set());
      setErrorCocina(null);
    },
    onError: (err) => {
      setErrorCocina(describeError(err));
      return true;
    },
  });
  const entregar = useComandaAction<number>(c.id, (itemId) => ({ path: `/items/${itemId}/entregar` }), {
    optimistic: (prev, itemId) => ({
      ...prev,
      items: prev.items.map((i) => (i.id === itemId ? { ...i, estado: "entregado", entregado_en: new Date().toISOString() } : i)),
    }),
  });
  const cancelarItem = useComandaAction<number>(c.id, (itemId) => ({ path: `/items/${itemId}/cancelar` }), {
    optimistic: (prev, itemId) => ({ ...prev, items: prev.items.map((i) => (i.id === itemId ? { ...i, estado: "cancelado" } : i)) }),
  });

  const seleccionados = [...seleccion].filter((sid) => pendientes.some((p) => p.id === sid));

  async function copiarSeguimiento() {
    try {
      await navigator.clipboard.writeText(c.seguimiento_url);
      toast({ title: "Enlace de seguimiento copiado", tone: "ok", duration: 3000 });
    } catch {
      toast({ title: "No se pudo copiar", description: c.seguimiento_url, tone: "warn" });
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            {`Comanda ${c.id} · ${c.origen === "qr" ? "por QR" : "en caja"} · ${hora.format(new Date(c.created_at))}${
              c.mesa && c.nombre_cliente ? ` · ${c.nombre_cliente}` : ""
            }`}
            {c.telefono_cliente && (
              <>
                {" · "}
                <a href={`tel:${c.telefono_cliente}`} className="underline-offset-4 hover:text-fg hover:underline">
                  {c.telefono_cliente}
                </a>
                {" · "}
                <a
                  href={`https://wa.me/${c.telefono_cliente.replace(/\D/g, "")}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline-offset-4 hover:text-fg hover:underline"
                >
                  WhatsApp
                </a>
              </>
            )}
          </>
        }
        title={tituloComanda(c)}
        actions={
          <>
            {editable && (
              <Button variant="line" onClick={() => setAgregar(true)}>
                <Plus size={16} strokeWidth={1.5} aria-hidden /> Agregar platos
              </Button>
            )}
            <DM.Root>
              <DM.Trigger asChild>
                <Button variant="ghost" aria-label="Más acciones">
                  <Ellipsis size={18} strokeWidth={1.5} />
                </Button>
              </DM.Trigger>
              <DM.Portal>
                <DM.Content align="end" sideOffset={6} className={menuContent}>
                  {editable && (
                    <DM.Item
                      className={menuItem}
                      onSelect={() => {
                        setEditarKey((k) => k + 1);
                        setEditar(true);
                      }}
                    >
                      Mesa, cliente y notas
                    </DM.Item>
                  )}
                  <DM.Item className={menuItem} onSelect={() => void copiarSeguimiento()}>
                    Copiar enlace de seguimiento <Copy size={16} strokeWidth={1.5} aria-hidden />
                  </DM.Item>
                  {abierta && can(me, "comandas", "eliminar") && (
                    <>
                      <DM.Separator className="my-1 h-px bg-line" />
                      <DM.Item className={cn(menuItem, "text-err data-[highlighted]:text-err")} onSelect={() => setCancelar(true)}>
                        Cancelar comanda
                      </DM.Item>
                    </>
                  )}
                </DM.Content>
              </DM.Portal>
            </DM.Root>
          </>
        }
      />

      {!abierta && (
        <p className="-mt-6 mb-10 border-l-2 border-line-strong pl-4 text-base text-fg-2">
          {c.estado === "cerrada"
            ? `Cerrada a las ${hora.format(new Date(c.cerrada_en ?? c.created_at))}. Ya es una venta.`
            : `Cancelada${c.motivo_cancelacion ? `: ${c.motivo_cancelacion}` : "."}`}
        </p>
      )}

      <div className="grid gap-16 desk:grid-cols-[1fr_340px]">
        <LayoutGroup>
          <div className="flex min-w-0 flex-col gap-12">
            {c.items.length === 0 && (
              <EmptyState
                title="Sin platos"
                description="Esta comanda todavía no tiene nada. Agrega platos para mandarlos a cocina."
                action={editable && <Button onClick={() => setAgregar(true)}>Agregar platos</Button>}
                className="py-0"
              />
            )}
            {GRUPOS.map((g) => {
              const items = porGrupo.get(g.id) ?? [];
              if (items.length === 0) return null;
              return (
                <motion.section key={g.id} layout transition={smooth} aria-labelledby={`g-${g.id}`} className="flex flex-col">
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
                    <h2 id={`g-${g.id}`} className="eyebrow">
                      {g.label} · {items.length}
                    </h2>
                    {g.id === "aprobar" && editable && (
                      <Button
                        size="sm"
                        loading={enviar.isPending}
                        onClick={() => enviar.mutate(seleccionados.length ? seleccionados : null)}
                      >
                        {seleccionados.length ? `Enviar ${seleccionados.length} a cocina` : "Enviar todo a cocina"}
                      </Button>
                    )}
                    {g.id === "servir" && editable && listos.length > 1 && (
                      <Button size="sm" variant="line" onClick={() => listos.forEach((i) => entregar.mutate(i.id))}>
                        Entregar todos
                      </Button>
                    )}
                  </div>
                  {g.id === "aprobar" && errorCocina && <ErrorBox error={errorCocina} onClose={() => setErrorCocina(null)} />}
                  <ul className="flex flex-col">
                    <AnimatePresence initial={false} mode="popLayout">
                      {items.map((i) => (
                        <ItemRow
                          key={i.id}
                          item={i}
                          editable={editable}
                          seleccionable={g.id === "aprobar" && editable}
                          seleccionado={seleccion.has(i.id)}
                          onSeleccionar={() =>
                            setSeleccion((s) => {
                              const n = new Set(s);
                              if (n.has(i.id)) n.delete(i.id);
                              else n.add(i.id);
                              return n;
                            })
                          }
                          onEntregar={() => entregar.mutate(i.id)}
                          onCancelar={() => cancelarItem.mutate(i.id)}
                          onIngredientes={editable && i.estado === "pendiente" ? () => setIngredientesItem(i) : undefined}
                          onCortesia={
                            c.estado === "abierta" && can(me, "caja", "editar")
                              ? () => (i.cortesia ? cortesia.mutate({ id: i.id, cortesia: false }) : setCortesiaItem(i))
                              : undefined
                          }
                        />
                      ))}
                    </AnimatePresence>
                  </ul>
                </motion.section>
              );
            })}
            {cancelados.length > 0 && (
              <details className="group">
                <summary className="eyebrow cursor-pointer list-none py-2 hover:text-fg-2">Cancelados · {cancelados.length}</summary>
                <ul className="flex flex-col">
                  {cancelados.map((i) => (
                    <li key={i.id} className="flex items-baseline justify-between border-t border-line py-3 text-fg-3 line-through decoration-1">
                      <span>{i.nombre}</span>
                      <Money value={i.precio_unitario} />
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </LayoutGroup>

        <div className="flex flex-col gap-10">
          <Cuenta c={c} />
          {abierta && <ChatCaja comandaId={c.id} puede={can(me, "comandas", "editar")} />}
        </div>
      </div>

      {editable && <AgregarPlatos open={agregar} onOpenChange={setAgregar} comanda={c} />}
      {editable && <EditarComanda key={editarKey} open={editar} onOpenChange={setEditar} comanda={c} />}
      {ingredientesItem && <QuitarIngredientes key={ingredientesItem.id} comandaId={c.id} item={ingredientesItem} onClose={() => setIngredientesItem(null)} />}
      <CancelarComanda open={cancelar} onOpenChange={setCancelar} comanda={c} />
      <Dialog
        open={cortesiaItem !== null}
        onOpenChange={(o) => !o && setCortesiaItem(null)}
        title={`¿${cortesiaItem?.nombre ?? ""} de cortesía?`}
        description="No se cobra ni se factura. Queda en la bitácora con su motivo."
        actions={
          <>
            <Button variant="ghost" onClick={() => setCortesiaItem(null)}>
              Volver
            </Button>
            <Button
              loading={cortesia.isPending}
              disabled={motivoCortesia.trim().length < 3}
              onClick={() => cortesiaItem && cortesia.mutate({ id: cortesiaItem.id, cortesia: true, motivo: motivoCortesia.trim() })}
            >
              Dar de cortesía
            </Button>
          </>
        }
      >
        <Field label="Motivo" value={motivoCortesia} onChange={(e) => setMotivoCortesia(e.target.value)} maxLength={255} placeholder="Cliente frecuente, demora, reclamo…" autoFocus />
      </Dialog>
    </>
  );
}

function ItemRow({
  item,
  editable,
  seleccionable,
  seleccionado,
  onSeleccionar,
  onEntregar,
  onCancelar,
  onCortesia,
  onIngredientes,
}: {
  item: Item;
  editable: boolean;
  seleccionable: boolean;
  seleccionado: boolean;
  onSeleccionar: () => void;
  onEntregar: () => void;
  onCancelar: () => void;
  /** Dar de cortesía o volver a cobrar (solo con permiso de caja). */
  onCortesia?: () => void;
  /** Quitar ingredientes de un plato pendiente (para no descontar lo que no se usa). */
  onIngredientes?: () => void;
}) {
  const now = useNow();
  const e = ESTADO_ITEM[item.estado];
  const cancelable = editable && ["pendiente", "en_cocina", "preparando"].includes(item.estado);
  return (
    <motion.li
      layout
      layoutId={`item-${item.id}`}
      transition={smooth}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex min-h-16 items-center gap-4 border-t border-line py-3"
    >
      {seleccionable && (
        <button
          type="button"
          role="checkbox"
          aria-checked={seleccionado}
          aria-label={`Seleccionar ${item.nombre}`}
          onClick={onSeleccionar}
          className={cn(
            "grid size-5 shrink-0 place-items-center rounded-[5px] border transition-colors",
            seleccionado ? "border-paper bg-paper text-ink" : "border-line-strong hover:border-fg-3",
          )}
        >
          {seleccionado && <Check size={14} strokeWidth={2} aria-hidden />}
        </button>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className={cn("text-title font-medium", item.estado === "entregado" && "text-fg-2")}>{item.nombre}</span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-fg-3">
          {item.notas && <span className="text-fg-2">“{item.notas}”</span>}
          {item.agregado_por_cliente && item.estado === "pendiente" && <span>Lo pidió el cliente</span>}
          {item.cortesia && <span className="text-ok">Cortesía{item.cortesia_motivo ? ` · ${item.cortesia_motivo}` : ""}</span>}
        </span>
      </div>
      <span className="hidden shrink-0 tablet:block">
        <StatusDot tone={e.tone}>
          {e.label}
          {(item.estado === "en_cocina" || item.estado === "preparando") && item.enviado_en && now !== null && (
            <span className="tabular text-fg-3"> · {minutosDesde(item.enviado_en, now)}′</span>
          )}
        </StatusDot>
      </span>
      <Money value={item.precio_unitario} className={cn("w-20 shrink-0 justify-end text-fg-2", item.cortesia && "line-through opacity-60")} />
      <div className="flex w-[140px] shrink-0 items-center justify-end gap-1">
        {item.estado === "listo" && editable && (
          <Button size="sm" onClick={onEntregar}>
            Entregar
          </Button>
        )}
        {(cancelable || onCortesia || onIngredientes) && item.estado !== "cancelado" && (
          <DM.Root>
            <DM.Trigger asChild>
              <Button size="sm" variant="ghost" aria-label={`Acciones de ${item.nombre}`}>
                <Ellipsis size={16} strokeWidth={1.5} />
              </Button>
            </DM.Trigger>
            <DM.Portal>
              <DM.Content align="end" sideOffset={6} className={menuContent}>
                {onIngredientes && (
                  <DM.Item className={menuItem} onSelect={onIngredientes}>
                    Quitar ingredientes
                  </DM.Item>
                )}
                {onCortesia && (
                  <DM.Item className={menuItem} onSelect={onCortesia}>
                    {item.cortesia ? "Volver a cobrar" : "Dar de cortesía"}
                  </DM.Item>
                )}
                {cancelable && (
                  <DM.Item className={cn(menuItem, "text-err data-[highlighted]:text-err")} onSelect={onCancelar}>
                    Cancelar este plato
                  </DM.Item>
                )}
              </DM.Content>
            </DM.Portal>
          </DM.Root>
        )}
      </div>
    </motion.li>
  );
}

function Cuenta({ c }: { c: Comanda }) {
  const { data: me } = useMe();
  const { data: monedas } = useMonedas(c.sucursal_id);
  const principal = principalDe(monedas);
  // Sin acceso a monedas: la principal es la que tiene el mismo monto que el total (tasa 1)
  const simbolo = principal?.simbolo ?? c.totales.total_monedas.find((m) => m.monto === c.totales.total)?.simbolo;
  const codigoPrincipal = principal?.codigo ?? c.totales.total_monedas.find((m) => m.simbolo === simbolo)?.moneda;
  const pendiente = isPositive(c.totales.pendiente);
  const vuelto = isPositive(c.totales.vuelto);
  return (
    <aside aria-labelledby="cuenta-t" className="flex flex-col gap-8 desk:sticky desk:top-12 desk:self-start">
      <div className="flex flex-col gap-3">
        <h2 id="cuenta-t" className="eyebrow">
          Cuenta
        </h2>
        <Money value={c.totales.total} simbolo={simbolo} size="l" roll />
        <dl className="flex flex-col text-base">
          <div className="flex justify-between border-t border-line py-3">
            <dt className="text-fg-3">Pagado</dt>
            <dd>
              <Money value={c.totales.pagado} simbolo={simbolo} />
            </dd>
          </div>
          <div className="flex justify-between border-t border-line py-3">
            <dt className="text-fg-3">Falta</dt>
            <dd className={cn(pendiente && "font-medium text-fg")}>
              <Money value={c.totales.pendiente} simbolo={simbolo} />
            </dd>
          </div>
          {vuelto && (
            <div className="flex justify-between border-t border-line py-3">
              <dt className="text-fg-3">Vuelto</dt>
              <dd className="flex flex-col items-end gap-0.5">
                <Money value={c.totales.vuelto} simbolo={simbolo} />
                {monedas
                  ?.filter((m) => !m.es_principal)
                  .map((m) => (
                    <Money key={m.id} value={fromPrincipal(c.totales.vuelto, m.tasa, m.operacion)} simbolo={m.simbolo} className="text-sm text-fg-3" />
                  ))}
              </dd>
            </div>
          )}
        </dl>
        {c.totales.total_monedas.length > 1 && (
          <ul className="flex flex-col gap-1 text-sm text-fg-3">
            {c.totales.total_monedas
              .filter((m) => m.moneda !== codigoPrincipal)
              .map((m) => (
                <li key={m.moneda} className="flex justify-between">
                  <span>{m.moneda}</span>
                  <Money value={m.monto} simbolo={m.simbolo} />
                </li>
              ))}
          </ul>
        )}
      </div>

      {c.estado === "abierta" && can(me, "caja", "leer") && c.items.some((i) => i.estado !== "cancelado") && (
        <Link
          href={`/panel/caja/${c.id}`}
          className="inline-flex h-14 items-center justify-center rounded-control bg-paper text-lead font-medium text-ink transition-colors hover:bg-paper/90"
        >
          {pendiente ? "Cobrar" : "Cerrar en caja"}
        </Link>
      )}

      {c.pagos.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="eyebrow">Pagos</h3>
          <ul className="flex flex-col">
            {c.pagos.map((p) => (
              <li key={p.id} className="flex items-baseline justify-between gap-3 border-t border-line py-3 text-base">
                <span className="flex flex-col">
                  <span>{METODO[p.metodo]}</span>
                  {p.etiqueta && <span className="text-sm text-fg-3">{p.etiqueta}</span>}
                </span>
                <Money value={p.monto} simbolo={monedas?.find((m) => m.codigo === p.moneda)?.simbolo ?? p.moneda} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {c.notas && (
        <div className="flex flex-col gap-2">
          <h3 className="eyebrow">Notas</h3>
          <p className="text-base text-fg-2">{c.notas}</p>
        </div>
      )}
    </aside>
  );
}

export const METODO = {
  efectivo: "Efectivo",
  tarjeta: "Tarjeta",
  transferencia: "Transferencia",
  pago_movil: "Pago móvil",
  otro: "Otro",
} as const;

function DetalleSkeleton() {
  return (
    <Loading label="Cargando comanda">
      <Skeleton className="h-3 w-48" />
      <Skeleton className="mt-4 h-14 w-56" />
      <div className="mt-14 grid gap-16 desk:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-5">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="flex items-center justify-between border-t border-line pt-5">
              <Skeleton className="h-5 w-44" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-4">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-16 w-40" />
          <Skeleton className="h-14 w-full" />
        </div>
      </div>
    </Loading>
  );
}

function ChatCaja({ comandaId, puede }: { comandaId: number; puede: boolean }) {
  const { lista, enviar } = useChatStaff(comandaId);
  return (
    <section className="flex flex-col gap-3">
      <h2 className="eyebrow">Chat con la mesa</h2>
      {puede ? (
        <ChatPanel mensajes={lista.data ?? []} yo="personal" onEnviar={(t) => enviar.mutate(t)} enviando={enviar.isPending} vacio="Sin mensajes. Escríbele a la mesa si hace falta." />
      ) : (
        <p className="text-sm text-fg-3">Tu rol no puede escribir en el chat.</p>
      )}
    </section>
  );
}

/** Caja marca qué ingredientes lleva el plato: los quitados no se reservan ni se descuentan del inventario. */
function QuitarIngredientes({ comandaId, item, onClose }: { comandaId: number; item: Item; onClose: () => void }) {
  const ingredientes = useQuery({
    queryKey: ["comanda", comandaId, "ingredientes", item.id],
    queryFn: () => api(`/comandas/${comandaId}/items/${item.id}/ingredientes`, { schema: z.array(z.object({ insumo_id: z.number(), nombre: z.string() })) }),
  });
  const [sin, setSin] = useState<number[]>(item.sin_insumo_ids);
  const guardar = useComandaAction<number[]>(comandaId, (ids) => ({ path: `/items/${item.id}/sin-ingredientes`, method: "PUT", body: { sin_insumo_ids: ids } }), { onSuccess: onClose });
  const lista = ingredientes.data ?? [];
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Ingredientes de ${item.nombre}`}
      description="Marca lo que NO lleva. Eso no se descuenta del inventario."
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Volver
          </Button>
          <Button onClick={() => guardar.mutate(sin)} disabled={guardar.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      {ingredientes.isPending ? (
        <p className="text-sm text-fg-3">Cargando…</p>
      ) : lista.length === 0 ? (
        <p className="text-sm text-fg-3">Este plato no tiene ingredientes que se puedan quitar.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {lista.map((ing) => {
            const quitado = sin.includes(ing.insumo_id);
            return (
              <button
                key={ing.insumo_id}
                type="button"
                aria-pressed={quitado}
                onClick={() => setSin((s) => (quitado ? s.filter((x) => x !== ing.insumo_id) : [...s, ing.insumo_id]))}
                className={cn("rounded-full border px-3 py-1.5 text-sm transition-colors", quitado ? "border-line bg-wash text-fg-3 line-through" : "border-line-strong text-fg-2 hover:text-fg")}
              >
                {quitado ? `Sin ${ing.nombre}` : ing.nombre}
              </button>
            );
          })}
        </div>
      )}
    </Dialog>
  );
}
