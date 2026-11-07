"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Big from "big.js";
import { ArrowLeft, ScanLine, Search } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Segmented } from "@/components/ui/Segmented";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusDot } from "@/components/ui/Status";
import { toast } from "@/components/ui/Toast";
import { can, useMe } from "@/features/auth/useMe";
import { useSucursal } from "@/features/panel/sucursal";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { InsumoEncontradoOut, InventarioOut, MovimientoOut, Pagina, type InsumoEncontrado, type Inventario } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { parseAmountInput } from "@/lib/money";
import { smooth, tap } from "@/lib/motion";
import { z } from "zod";
import { Escaner } from "./Escaner";
import { cantidad } from "./unidad";
import { atajos } from "./useUnidades";

type Operacion = "entrada" | "merma" | "ajuste" | "minimo";

const OPERACION: Record<Operacion, { label: string; verbo: string; ayuda: string }> = {
  entrada: { label: "Reponer", verbo: "Reponer", ayuda: "Lo que llegó: se suma al stock." },
  merma: { label: "Merma", verbo: "Descontar", ayuda: "Se dañó, venció o se perdió." },
  ajuste: { label: "Conteo", verbo: "Fijar stock en", ayuda: "Lo que contaste: reemplaza el stock." },
  minimo: { label: "Mínimo", verbo: "Guardar mínimo de", ayuda: "Cuando el stock baje de aquí, se avisa." },
};


const hora = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/**
 * Reposición desde el teléfono: sucursal → buscar o escanear → reponer, merma,
 * conteo o mínimo. Funciona también con lectores de código de barras USB/Bluetooth
 * (escriben el código y "Enter" en el buscador).
 */
export function Reponer() {
  const { data: me } = useMe();
  const { sucursales, actual, cambiar } = useSucursal();
  // Con varias sucursales, lo primero es confirmar en cuál se está reponiendo
  const [sucursalLista, setSucursalLista] = useState(sucursales.length <= 1);
  const [q, setQ] = useState("");
  const [buscado, setBuscado] = useState<string | null>(null);
  const [elegido, setElegido] = useState<InsumoEncontrado | null>(null);
  const [escaneando, setEscaneando] = useState(false);

  const resultados = useQuery({
    queryKey: ["inventario", "buscar", actual?.id, buscado],
    queryFn: () => api("/inventario/buscar", { query: { sucursal_id: actual!.id, q: buscado! }, schema: z.array(InsumoEncontradoOut) }),
    enabled: !!actual && !!buscado,
  });

  const buscar = useCallback((texto: string) => {
    const t = texto.trim();
    if (!t) return;
    setQ(t);
    setElegido(null);
    setBuscado(t);
  }, []);

  const alLeer = useCallback(
    (texto: string) => {
      setEscaneando(false);
      buscar(texto);
    },
    [buscar],
  );

  // Un código exacto lleva directo a la ficha
  const unico = resultados.data?.length === 1 && resultados.data[0]!.coincidencia !== "nombre" ? resultados.data[0]! : null;
  const ficha = elegido ?? unico;

  if (!actual) return <p className="text-fg-2">No tienes sucursales asignadas.</p>;

  if (!sucursalLista) {
    return (
      <div className="mx-auto flex max-w-lg flex-col gap-8">
        <header className="flex flex-col gap-2">
          <span className="eyebrow">Reponer inventario</span>
          <h1 className="font-display text-display-m">¿En qué sucursal estás?</h1>
        </header>
        <ul className="flex flex-col gap-3">
          {sucursales.map((s) => (
            <li key={s.id}>
              <motion.button
                type="button"
                whileTap={tap}
                onClick={() => {
                  cambiar(s.id);
                  setSucursalLista(true);
                }}
                className={cn(
                  "flex h-20 w-full items-center justify-between rounded-sheet px-6 text-left ring-1 ring-inset transition-colors",
                  s.id === actual.id ? "bg-raised ring-line-strong" : "ring-line hover:bg-wash",
                )}
              >
                <span className="font-display text-display-s leading-none">{s.nombre}</span>
                {s.id === actual.id && <span className="text-sm text-fg-3">Última usada</span>}
              </motion.button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-6 pb-24">
      <header className="flex items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <span className="eyebrow">Reponer inventario</span>
          <h1 className="font-display text-display-m leading-none">{actual.nombre}</h1>
        </div>
        {sucursales.length > 1 && (
          <button type="button" onClick={() => setSucursalLista(false)} className="pb-1 text-sm text-fg-2 underline underline-offset-4">
            Cambiar
          </button>
        )}
      </header>

      {/* Buscador: también recibe lectores de código de barras (escriben el código + Enter) */}
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          buscar(q);
        }}
        className="sticky top-2 z-10 flex gap-2 rounded-sheet bg-canvas/70 p-1 backdrop-blur-xl"
      >
        <label className="flex h-14 min-w-0 flex-1 items-center gap-3 rounded-control bg-raised px-4 ring-1 ring-inset ring-line focus-within:ring-paper">
          <Search size={18} strokeWidth={1.5} className="shrink-0 text-fg-3" aria-hidden />
          <span className="sr-only">Código o nombre del insumo</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Código, barras o nombre"
            autoFocus
            enterKeyHint="search"
            autoCapitalize="characters"
            autoComplete="off"
            className="h-full w-full bg-transparent text-lead outline-none placeholder:text-fg-4 focus-visible:outline-none"
          />
        </label>
        <motion.button
          type="button"
          whileTap={tap}
          onClick={() => setEscaneando(true)}
          aria-label="Escanear con la cámara"
          className="grid size-14 shrink-0 place-items-center rounded-control bg-paper text-ink"
        >
          <ScanLine size={22} strokeWidth={1.75} />
        </motion.button>
      </form>

      <AnimatePresence mode="wait" initial={false}>
        {ficha ? (
          <motion.div key={`ficha-${ficha.insumo.id}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={smooth}>
            <Ficha
              encontrado={ficha}
              sucursalId={actual.id}
              sucursalNombre={actual.nombre}
              puedeEditar={can(me, "inventario", "editar")}
              puedeCrear={can(me, "inventario", "crear")}
              onVolver={resultados.data && resultados.data.length > 1 ? () => setElegido(null) : undefined}
              onOtro={() => {
                setElegido(null);
                setBuscado(null);
                setQ("");
                setEscaneando(true);
              }}
            />
          </motion.div>
        ) : buscado ? (
          <motion.div key="resultados" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {resultados.isPending ? (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : resultados.isError ? (
              <ErrorBox error={describeError(resultados.error)} />
            ) : resultados.data.length === 0 ? (
              <div className="flex flex-col gap-2 py-10 text-center">
                <p className="font-display text-display-s">Sin resultados</p>
                <p className="text-base text-fg-2">Ningún insumo tiene el código o nombre “{buscado}”.</p>
              </div>
            ) : (
              <ul className="flex flex-col">
                {resultados.data.map((r) => (
                  <li key={r.insumo.id}>
                    <button type="button" onClick={() => setElegido(r)} className="flex w-full items-center justify-between gap-4 border-t border-line py-4 text-left">
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate text-title font-medium">{r.insumo.nombre}</span>
                        <span className="text-sm tabular text-fg-3">{r.insumo.codigo}</span>
                      </span>
                      {r.inventario ? (
                        <span className="shrink-0 text-right">
                          <span className="block font-display text-display-s leading-none tabular">{cantidad(r.inventario.cantidad)}</span>
                          <span className="text-sm text-fg-3">{r.insumo.unidad_abreviatura}</span>
                        </span>
                      ) : (
                        <span className="shrink-0 text-sm text-fg-3">No registrado aquí</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        ) : (
          <motion.p key="ayuda" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="py-10 text-center text-base text-fg-3">
            Escanea el QR de la etiqueta, el código de barras del empaque o escribe el código interno.
          </motion.p>
        )}
      </AnimatePresence>

      <Escaner
        abierto={escaneando}
        onCerrar={() => setEscaneando(false)}
        onLeido={alLeer}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ ficha del insumo */
function Ficha({
  encontrado,
  sucursalId,
  sucursalNombre,
  puedeEditar,
  puedeCrear,
  onVolver,
  onOtro,
}: {
  encontrado: InsumoEncontrado;
  sucursalId: number;
  sucursalNombre: string;
  puedeEditar: boolean;
  puedeCrear: boolean;
  onVolver?: () => void;
  onOtro: () => void;
}) {
  const qc = useQueryClient();
  const { insumo } = encontrado;
  const [inv, setInv] = useState<Inventario | null>(encontrado.inventario);
  const [op, setOp] = useState<Operacion>("entrada");
  const [valor, setValor] = useState("");
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<ErrorView | null>(null);
  // Al reponer se puede contar en envases (3 cajas x24) en vez de unidades sueltas
  const [presId, setPresId] = useState("");
  const pres = op === "entrada" ? insumo.presentaciones.find((p) => String(p.id) === presId) : undefined;
  const base = insumo.unidad_abreviatura;
  const u = pres ? pres.nombre : base;
  const entero = !insumo.permite_decimales || !!pres;

  const movimientos = useQuery({
    queryKey: ["inventario", "movimientos", inv?.id],
    queryFn: () => api(`/inventario/${inv!.id}/movimientos`, { query: { limite: 5 }, schema: Pagina(MovimientoOut) }),
    enabled: !!inv,
  });

  const guardar = useMutation({
    mutationFn: async (cant: string) => {
      if (!inv) {
        // Primera vez en esta sucursal: se registra con lo que llegó como stock inicial
        return api("/inventario", {
          method: "POST",
          body: { sucursal_id: sucursalId, insumo_id: insumo.id, cantidad: cant, stock_minimo: "0" },
          schema: InventarioOut,
        });
      }
      const ruta = { entrada: "entrada", merma: "merma", ajuste: "ajuste", minimo: "" }[op];
      if (op === "minimo") return api(`/inventario/${inv.id}`, { method: "PATCH", body: { stock_minimo: cant }, schema: InventarioOut });
      const body = op === "ajuste" ? { cantidad_real: cant, motivo: motivo.trim() || "Conteo desde el teléfono" } : { cantidad: cant, motivo: motivo.trim() || null, ...(pres ? { presentacion_id: pres.id } : {}) };
      return api(`/inventario/${inv.id}/${ruta}`, { method: "POST", body, schema: InventarioOut });
    },
    onSuccess: (nuevo, cant) => {
      const texto = !inv
        ? `${insumo.nombre} registrado con ${cantidad(cant)} ${u}`
        : op === "entrada"
          ? `+${cantidad(cant)} ${u} de ${insumo.nombre}`
          : op === "merma"
            ? `−${cantidad(cant)} ${u} de ${insumo.nombre}`
            : op === "ajuste"
              ? `${insumo.nombre}: ${cantidad(cant)} ${u} contados`
              : `Mínimo de ${insumo.nombre}: ${cantidad(cant)} ${u}`;
      toast({ title: texto, description: `Stock: ${cantidad(nuevo.cantidad)} ${base}`, tone: "ok", duration: 3500 });
      navigator.vibrate?.(30);
      setInv(nuevo);
      setValor("");
      setMotivo("");
      setError(null);
      void qc.invalidateQueries({ queryKey: ["inventario"] });
      void qc.invalidateQueries({ queryKey: ["alertas"] });
    },
    onError: (e) => setError(describeError(e)),
  });

  const numero = parseAmountInput(valor);
  const valido = numero !== null && (op === "ajuste" || op === "minimo" ? new Big(numero).gte(0) : new Big(numero).gt(0)) && (!entero || /^\d+$/.test(numero));
  const accion = inv ? OPERACION[op] : { verbo: "Registrar con", ayuda: `Aún no está en el inventario de ${sucursalNombre}: se registra con este stock inicial.` };

  return (
    <article className="flex flex-col gap-6">
      {onVolver && (
        <button type="button" onClick={onVolver} className="flex items-center gap-2 self-start text-sm text-fg-2">
          <ArrowLeft size={16} strokeWidth={1.5} aria-hidden /> Resultados
        </button>
      )}
      <header className="flex flex-col gap-1">
        <span className="text-sm tabular text-fg-3">
          {insumo.codigo}
          {insumo.codigo_barras && ` · ${insumo.codigo_barras}`}
        </span>
        <h2 className="font-display text-display-m leading-none">{insumo.nombre}</h2>
      </header>

      {inv ? (
        <div className="flex items-end justify-between gap-4 rounded-sheet bg-raised p-5">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">En stock</span>
            <span className="font-display text-display-l leading-none tabular">
              {cantidad(inv.cantidad)}
              <span className="ml-2 font-sans text-lead text-fg-3">{base}</span>
            </span>
          </div>
          <dl className="flex flex-col items-end gap-1 text-sm">
            <StatusDot tone={inv.bajo_minimo ? "warn" : "ok"}>{inv.bajo_minimo ? "Bajo el mínimo" : "Bien"}</StatusDot>
            <div className="flex gap-1 text-fg-3">
              <dt>Mínimo</dt>
              <dd className="tabular text-fg-2">
                {cantidad(inv.stock_minimo)} {base}
              </dd>
            </div>
            {new Big(inv.reservado).gt(0) && (
              <div className="flex gap-1 text-fg-3">
                <dt>En cocina</dt>
                <dd className="tabular text-fg-2">
                  {cantidad(inv.reservado)} {base}
                </dd>
              </div>
            )}
          </dl>
        </div>
      ) : (
        <p className="rounded-sheet bg-raised p-5 text-base text-fg-2">Este insumo todavía no está en el inventario de {sucursalNombre}.</p>
      )}

      {(inv ? puedeEditar : puedeCrear) ? (
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (valido && numero) guardar.mutate(numero);
          }}
        >
          {inv && (
            <Segmented
              label="Qué quieres hacer"
              value={op}
              onChange={(o) => {
                setOp(o);
                setValor(o === "minimo" ? inv.stock_minimo.replace(/\.?0+$/, "") : "");
                setError(null);
              }}
              options={(Object.keys(OPERACION) as Operacion[]).map((k) => ({ value: k, label: OPERACION[k].label }))}
              className="w-full [&>*]:flex-1"
            />
          )}
          <p className="-mt-1 text-sm text-fg-3">{accion.ayuda}</p>
          {inv && op === "entrada" && insumo.presentaciones.length > 0 && (
            <Segmented
              label="Cómo llegó"
              value={presId}
              onChange={(v) => {
                setPresId(v);
                setValor("");
              }}
              options={[{ value: "", label: `${base} sueltas` }, ...insumo.presentaciones.map((p) => ({ value: String(p.id), label: p.nombre }))]}
              className="w-full flex-wrap [&>*]:flex-1"
            />
          )}
          <label className="flex items-baseline gap-3 border-b border-line-strong pb-2 focus-within:border-paper">
            <span className="sr-only">Cantidad en {u}</span>
            <input
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              inputMode={entero ? "numeric" : "decimal"}
              placeholder="0"
              className="min-w-0 flex-1 bg-transparent font-display text-display-l leading-none tabular outline-none placeholder:text-fg-4 focus-visible:outline-none"
            />
            <span className="text-lead text-fg-3">{u}</span>
          </label>
          {(op === "entrada" || op === "merma" || !inv) && (
            <div className="grid grid-cols-4 gap-2">
              {(pres ? ["1", "2", "5", "10"] : atajos(insumo.permite_decimales, insumo.unidad)).map((a) => (
                <motion.button
                  key={a}
                  type="button"
                  whileTap={tap}
                  onClick={() => setValor((v) => new Big(parseAmountInput(v) ?? "0").plus(a).toString())}
                  className="h-12 rounded-control text-base tabular ring-1 ring-inset ring-line-strong hover:bg-wash"
                >
                  +{cantidad(a)}
                </motion.button>
              ))}
            </div>
          )}
          {inv && op !== "minimo" && (
            <input
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              maxLength={255}
              placeholder={op === "entrada" ? "Proveedor o factura (opcional)" : op === "merma" ? "Qué pasó (opcional)" : "Nota (opcional)"}
              className="h-11 border-b border-line bg-transparent text-base outline-none placeholder:text-fg-4 focus:border-paper focus-visible:outline-none"
            />
          )}
          {error && <ErrorBox error={error} onClose={() => setError(null)} />}
          <Button type="submit" size="lg" disabled={!valido} loading={guardar.isPending} className="w-full">
            {valido && numero ? `${accion.verbo} ${cantidad(numero)} ${u}${pres ? ` (${cantidad(new Big(numero).times(pres.cantidad).toString())} ${base})` : ""}` : accion.verbo.replace(/ (en|de|con)$/, "")}
          </Button>
        </form>
      ) : (
        <p className="text-sm text-fg-3">No tienes permiso para modificar el inventario.</p>
      )}

      {inv && movimientos.data && movimientos.data.items.length > 0 && (
        <section className="flex flex-col">
          <h3 className="eyebrow pb-2">Últimos movimientos</h3>
          {movimientos.data.items.map((m) => (
            <div key={m.id} className="flex items-baseline justify-between gap-3 border-t border-line py-3 text-sm">
              <span className="flex min-w-0 flex-col">
                <span className="capitalize text-fg-2">{m.tipo}</span>
                {m.motivo && <span className="truncate text-fg-3">{m.motivo}</span>}
              </span>
              <span className="shrink-0 text-right">
                <span className={cn("block tabular", m.cantidad.startsWith("-") ? "text-fg-2" : "text-fg")}>
                  {m.cantidad.startsWith("-") ? "−" : "+"}
                  {cantidad(m.cantidad.replace("-", ""))} {base}
                </span>
                <span className="text-fg-4">{hora.format(new Date(m.created_at))}</span>
              </span>
            </div>
          ))}
        </section>
      )}

      <Button variant="line" size="lg" onClick={onOtro} className="w-full">
        <ScanLine size={18} strokeWidth={1.5} aria-hidden /> Escanear otro
      </Button>
    </article>
  );
}
