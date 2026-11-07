"use client";

import { AnimatePresence, LayoutGroup, motion } from "motion/react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { CommandPalette, useCommandHotkey, type CommandItem } from "@/components/ui/CommandPalette";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Logo, Wordmark } from "@/components/ui/Logo";
import { Money } from "@/components/ui/Money";
import { MoneyInput } from "@/components/ui/MoneyInput";
import { Segmented } from "@/components/ui/Segmented";
import { Sheet } from "@/components/ui/Sheet";
import { Skeleton, Loading } from "@/components/ui/Skeleton";
import { ProgressLine, StatusDot, type Tone } from "@/components/ui/Status";
import { StickyHeader } from "@/components/ui/StickyHeader";
import { Switch } from "@/components/ui/Switch";
import { Table, Td, Th, Tr } from "@/components/ui/Table";
import { Timer } from "@/components/ui/Timer";
import { toast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import { fromPrincipal, remaining, toPrincipal, type Operacion } from "@/lib/money";
import { smooth, snappy, tap } from "@/lib/motion";

/* ------------------------------------------------------------------ datos de muestra */
const MONEDAS: { id: string; codigo: string; simbolo: string; tasa: string; operacion: Operacion }[] = [
  { id: "1", codigo: "USD", simbolo: "$", tasa: "1", operacion: "multiplicar" },
  { id: "2", codigo: "VES", simbolo: "Bs", tasa: "38.450000", operacion: "multiplicar" },
  { id: "3", codigo: "COP", simbolo: "COL$", tasa: "4012.500000", operacion: "multiplicar" },
];
const TOTAL = "48.50";

const SECCIONES = [
  { id: "color", label: "Color" },
  { id: "tipografia", label: "Tipografía" },
  { id: "caja", label: "Caja" },
  { id: "cocina", label: "Cocina" },
  { id: "componentes", label: "Componentes" },
  { id: "movimiento", label: "Movimiento" },
];

export function Showcase() {
  return (
    <>
      <StickyHeader>
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-6 tablet:px-12">
          <Wordmark />
          <nav aria-label="Secciones" className="scrollbar-none -mr-2 flex overflow-x-auto">
            {SECCIONES.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                className="whitespace-nowrap rounded-control px-3 py-2 text-sm text-fg-2 transition-colors hover:text-fg"
              >
                {s.label}
              </a>
            ))}
          </nav>
        </div>
      </StickyHeader>

      <main className="mx-auto flex max-w-6xl flex-col gap-32 px-6 pb-40 pt-16 tablet:px-12">
        <Intro />
        <Colores />
        <Tipografia />
        <Caja />
        <Cocina />
        <Componentes />
        <Movimiento />
      </main>
    </>
  );
}

/* ------------------------------------------------------------------ secciones */
function Section({ id, n, title, lead, children }: { id: string; n: string; title: string; lead: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-t`} className="scroll-mt-24">
      <div className="mb-12 grid gap-4 border-t border-line pt-6 desk:grid-cols-12">
        <span className="eyebrow desk:col-span-2">{n}</span>
        <div className="flex flex-col gap-3 desk:col-span-7">
          <h2 id={`${id}-t`} className="font-display text-display-m">
            {title}
          </h2>
          <p className="max-w-xl text-lead text-fg-2">{lead}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function Intro() {
  return (
    <header className="grid items-end gap-10 desk:grid-cols-12">
      <div className="desk:col-span-4">
        <Logo size={200} />
      </div>
      <div className="flex flex-col gap-5 desk:col-span-8">
        <span className="eyebrow">Sistema de diseño · v0.1</span>
        <h1 className="font-display text-display-l tablet:text-display-xl">
          Negro cálido,
          <br />
          blanco y números.
        </h1>
        <p className="max-w-lg text-lead text-fg-2">
          Dos colores y sus mezclas. La jerarquía la hacen el tamaño y el peso, no las cajas. El color de estado aparece
          solo cuando informa algo.
        </p>
      </div>
    </header>
  );
}

const SWATCHES: { token: string; value: string; use: string; cls: string }[] = [
  { token: "canvas", value: "#1a1819", use: "Fondo de todo", cls: "bg-canvas border border-line" },
  { token: "raised", value: "blanco 4 %", use: "Superficie elevada", cls: "bg-raised" },
  { token: "overlay", value: "blanco 7 %", use: "Sheets y popovers", cls: "bg-overlay" },
  { token: "paper", value: "#ffffff", use: "Acción primaria, foco", cls: "bg-paper" },
  { token: "fg", value: "blanco 94 %", use: "Texto principal", cls: "bg-fg" },
  { token: "fg-2", value: "blanco 68 %", use: "Texto secundario · 8,9:1", cls: "bg-fg-2" },
  { token: "fg-3", value: "blanco 52 %", use: "Metadatos · 5,4:1", cls: "bg-fg-3" },
  { token: "line", value: "blanco 10 %", use: "Separadores", cls: "bg-line" },
];

const ESTADOS: { token: string; value: string; use: string; tone: Tone }[] = [
  { token: "ok", value: "#93a68e", use: "Listo, pagado", tone: "ok" },
  { token: "warn", value: "#c4a978", use: "Stock bajo, demora", tone: "warn" },
  { token: "err", value: "#cc8a7d", use: "Error, rechazo", tone: "err" },
];

function Colores() {
  return (
    <Section id="color" n="01" title="Color" lead="Todo sale de #1a1819 y blanco. Los estados van desaturados y nunca tiñen texto ni fondos grandes.">
      <ul className="grid gap-x-10 tablet:grid-cols-2">
        {SWATCHES.map((s) => (
          <li key={s.token} className="flex items-center gap-5 border-b border-line py-4">
            <span aria-hidden className={cn("size-12 shrink-0 rounded-full", s.cls)} />
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="text-base font-medium">{s.token}</span>
              <span className="text-sm text-fg-3">{s.use}</span>
            </div>
            <code className="text-sm text-fg-2">{s.value}</code>
          </li>
        ))}
      </ul>
      <div className="mt-16 grid gap-8 tablet:grid-cols-3">
        {ESTADOS.map((e) => (
          <div key={e.token} className="flex flex-col gap-3">
            <ProgressLine value={2} max={3} tone={e.tone} label={e.use} />
            <StatusDot tone={e.tone}>{e.use}</StatusDot>
            <code className="text-sm text-fg-3">
              {e.token} · {e.value}
            </code>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Tipografia() {
  return (
    <Section
      id="tipografia"
      n="02"
      title="Tipografía"
      lead="Gagalin para lo que tiene que leerse a dos metros: totales, mesas y timers. General Sans para todo lo demás."
    >
      <div className="grid gap-16 desk:grid-cols-12">
        <div className="flex flex-col gap-8 desk:col-span-7">
          {[
            { cls: "text-display-xl", label: "Display XL · 96", sample: <Money value="1284.50" simbolo="$" size="xl" /> },
            { cls: "text-display-l", label: "Display L · 64", sample: "Mesa 12" },
            { cls: "text-display-m", label: "Display M · 40", sample: "Para llevar" },
            { cls: "text-display-s", label: "Display S · 28", sample: "12:48" },
          ].map((row) => (
            <div key={row.label} className="flex flex-col gap-2 border-b border-line pb-6">
              <span className="eyebrow">{row.label}</span>
              <span className={cn("font-display", row.cls)}>{row.sample}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-6 desk:col-span-5">
          <span className="eyebrow">Etiqueta · 13 · mayúsculas</span>
          <p className="text-h3 font-medium">Comanda 128 · Terraza</p>
          <p className="text-title font-medium">Hamburguesa doble, sin cebolla</p>
          <p className="text-lead text-fg-2">La cocina marcó lista la segunda hamburguesa. Falta la limonada.</p>
          <p className="text-base text-fg-2">
            Texto de cuerpo a 15 px. Se usa para descripciones, ayudas y todo lo que se lee de cerca. Los montos pequeños
            van con cifras tabulares: <span className="tabular text-fg">$ 12,50 · $ 9,00 · $ 104,25</span>.
          </p>
          <p className="text-sm text-fg-3">Metadatos · hace 4 min · por Ana</p>
          <p className="border-t border-line pt-6 text-sm text-fg-3">
            Si ves Gagalin igual que el cuerpo, falta <code className="text-fg-2">public/fonts/Gagalin-Regular.woff2</code>.
          </p>
        </div>
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ caja */
function Caja() {
  const [monedaId, setMonedaId] = useState("2");
  const [monto, setMonto] = useState<string | null>(null);
  const moneda = MONEDAS.find((m) => m.id === monedaId) ?? MONEDAS[0]!;

  const pendiente = useMemo(() => {
    if (!monto) return TOTAL;
    return remaining(TOTAL, toPrincipal(monto, moneda.tasa, moneda.operacion));
  }, [monto, moneda]);

  return (
    <Section
      id="caja"
      n="03"
      title="Caja"
      lead="Escribe el monto en cualquier moneda. Lo que falta gira en todas a la vez. Es solo una vista previa: el backend confirma el pago."
    >
      <div className="grid gap-12 desk:grid-cols-12">
        <div className="flex flex-col gap-8 desk:col-span-5">
          <Segmented
            label="Moneda del pago"
            value={monedaId}
            onChange={(v) => {
              setMonedaId(v);
              setMonto(null);
            }}
            options={MONEDAS.map((m) => ({ value: m.id, label: m.codigo }))}
          />
          <MoneyInput key={monedaId} label={`Recibido en ${moneda.codigo}`} simbolo={moneda.simbolo} onValueChange={setMonto} />
          <p className="text-sm text-fg-3">
            Total de la comanda <Money value={TOTAL} simbolo="$" className="text-fg-2" />
          </p>
        </div>
        <div className="flex flex-col gap-6 desk:col-span-7">
          <span className="eyebrow">Falta</span>
          <Money value={pendiente} simbolo="$" size="xl" roll />
          <ul className="flex flex-col">
            {MONEDAS.filter((m) => m.codigo !== "USD").map((m) => (
              <li key={m.id} className="flex items-baseline justify-between border-t border-line py-4">
                <span className="text-sm text-fg-3">{m.codigo}</span>
                <Money value={fromPrincipal(pendiente, m.tasa, m.operacion)} simbolo={m.simbolo} size="s" roll />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}

/* ------------------------------------------------------------------ cocina */
type EstadoPlato = "en_cocina" | "preparando" | "listo";

function Cocina() {
  // Puede diferir entre servidor y cliente: Timer no lo pinta hasta después de hidratar
  const [since] = useState(() => {
    const hace = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
    return { calma: hace(3), media: hace(11), tensa: hace(17) };
  });
  return (
    <Section
      id="cocina"
      n="04"
      title="Cocina"
      lead="El timer se tensa sin semáforo: la línea engrosa y vira a ocre con los minutos. Toca un plato para avanzarlo."
    >
      <div className="grid gap-px overflow-hidden rounded-sheet bg-line tablet:grid-cols-3">
        <KdsCard mesa="Mesa 3" since={since.calma} platos={["Hamburguesa #1", "Papas #1"]} />
        <KdsCard mesa="Terraza 2" since={since.media} platos={["Pasta #1", "Pasta #2", "Ensalada #1"]} />
        <KdsCard mesa="Para llevar" cliente="Luis" since={since.tensa} platos={["Hamburguesa #1"]} />
      </div>
    </Section>
  );
}

const ESTADO_LABEL: Record<EstadoPlato, string> = { en_cocina: "Nuevo", preparando: "Preparando", listo: "Listo" };
const SIGUIENTE: Record<EstadoPlato, EstadoPlato> = { en_cocina: "preparando", preparando: "listo", listo: "listo" };

function KdsCard({ mesa, cliente, since, platos }: { mesa: string; cliente?: string; since: string; platos: string[] }) {
  const [estados, setEstados] = useState<Record<string, EstadoPlato>>(() => Object.fromEntries(platos.map((p) => [p, "en_cocina"])));
  return (
    <article className="grain flex flex-col gap-6 bg-sunken p-6">
      <Timer since={since} />
      <header className="flex items-baseline justify-between gap-3">
        <h3 className="font-display text-display-m">{mesa}</h3>
        {cliente && <span className="text-base text-fg-2">{cliente}</span>}
      </header>
      <ul className="flex flex-col">
        {platos.map((p) => {
          const estado = estados[p] ?? "en_cocina";
          return (
            <li key={p}>
              <motion.button
                type="button"
                whileTap={tap}
                transition={snappy}
                disabled={estado === "listo"}
                onClick={() => setEstados((s) => ({ ...s, [p]: SIGUIENTE[estado] }))}
                className="flex min-h-16 w-full items-center justify-between gap-4 border-t border-line text-left"
              >
                <span className={cn("text-title font-medium transition-colors", estado === "listo" && "text-fg-3 line-through decoration-1")}>
                  {p}
                </span>
                <StatusDot tone={estado === "listo" ? "ok" : estado === "preparando" ? "neutral" : "muted"}>{ESTADO_LABEL[estado]}</StatusDot>
              </motion.button>
            </li>
          );
        })}
      </ul>
    </article>
  );
}

/* ------------------------------------------------------------------ componentes */
function Componentes() {
  const [vista, setVista] = useState<"dia" | "mes" | "anio">("dia");
  const [qr, setQr] = useState(true);
  const [sheet, setSheet] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [palette, setPalette] = useState(false);
  useCommandHotkey(() => setPalette((o) => !o));

  const comandos: CommandItem[] = [
    { id: "c-128", label: "Comanda 128", hint: "Terraza 2 · $ 48,50", group: "Comandas", onSelect: () => toast({ title: "Abriendo comanda 128" }) },
    { id: "m-4", label: "Mesa 4", hint: "Ocupada", group: "Mesas", onSelect: () => toast({ title: "Ir a Mesa 4" }) },
    { id: "cl-ana", label: "Ana Pérez", hint: "V-18.204.551", group: "Clientes", onSelect: () => toast({ title: "Ana Pérez" }) },
    { id: "a-cobrar", label: "Cobrar Mesa 4", group: "Acciones", keywords: ["pagar", "caja"], onSelect: () => toast({ title: "Caja · Mesa 4" }) },
  ];

  return (
    <Section id="componentes" n="05" title="Componentes" lead="Pocas piezas, siempre las mismas. Sin bordes alrededor de todo: líneas finas, aire y tamaño.">
      <div className="grid gap-x-16 gap-y-20 desk:grid-cols-2">
        <Demo title="Botones">
          <div className="flex flex-wrap items-center gap-3">
            <Button>Enviar a cocina</Button>
            <Button variant="line">Dividir cuenta</Button>
            <Button variant="ghost">Cancelar</Button>
            <Button variant="danger">Eliminar pago</Button>
            <Button loading>Cobrar</Button>
          </div>
          <Button size="lg" className="w-full">
            Marcar listo
          </Button>
        </Demo>

        <Demo title="Campos">
          <Field label="Correo" type="email" placeholder="ana@turestaurante.com" autoComplete="off" />
          <Field label="Contraseña" type="password" defaultValue="corta" error="Mínimo 10 caracteres, con mayúsculas, minúsculas y números." />
        </Demo>

        <Demo title="Selección">
          <Segmented
            label="Agrupar ventas"
            value={vista}
            onChange={setVista}
            options={[
              { value: "dia", label: "Día" },
              { value: "mes", label: "Mes" },
              { value: "anio", label: "Año" },
            ]}
          />
          <Switch checked={qr} onCheckedChange={setQr} label="Pedidos por QR en esta mesa" />
        </Demo>

        <Demo title="Estado">
          <div className="flex flex-col gap-5">
            {[
              { mesa: "Mesa 1", tone: "muted" as Tone, label: "Libre", v: 0, m: 0 },
              { mesa: "Mesa 4", tone: "neutral" as Tone, label: "En cocina · 1 de 4", v: 1, m: 4 },
              { mesa: "Terraza 2", tone: "ok" as Tone, label: "2 por servir", v: 3, m: 3 },
              { mesa: "Barra", tone: "warn" as Tone, label: "Por cobrar", v: 2, m: 2 },
            ].map((r) => (
              <div key={r.mesa} className="flex flex-col gap-2">
                <div className="flex items-baseline justify-between">
                  <span className="text-title font-medium">{r.mesa}</span>
                  <StatusDot tone={r.tone}>{r.label}</StatusDot>
                </div>
                <ProgressLine value={r.v} max={r.m} tone={r.tone} label={`${r.mesa}: ${r.label}`} />
              </div>
            ))}
          </div>
        </Demo>

        <Demo title="Capas">
          <div className="flex flex-wrap gap-3">
            <Button variant="line" onClick={() => setSheet(true)}>
              Abrir sheet
            </Button>
            <Button variant="line" onClick={() => setDialog(true)}>
              Confirmar
            </Button>
            <Button variant="line" onClick={() => setPalette(true)}>
              Buscar <kbd className="ml-1 text-sm text-fg-3">⌘K</kbd>
            </Button>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              variant="ghost"
              onClick={() =>
                toast({ title: "Stock bajo de Carne molida", description: "Quedan 50 g (mínimo 60 g)", tone: "warn", duration: 8000 })
              }
            >
              Toast de stock
            </Button>
            <Button variant="ghost" onClick={() => toast({ title: "Pago registrado", description: "Bs 1.864,83 · Pago móvil", tone: "ok" })}>
              Toast de pago
            </Button>
          </div>
        </Demo>

        <Demo title="Carga">
          <Loading label="Cargando comandas">
            <div className="flex flex-col gap-5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex items-center justify-between border-b border-line pb-5">
                  <div className="flex flex-col gap-2">
                    <Skeleton className="h-5 w-28" />
                    <Skeleton className="h-3.5 w-40" />
                  </div>
                  <Skeleton className="h-7 w-20" />
                </div>
              ))}
            </div>
          </Loading>
        </Demo>

        <div className="desk:col-span-2">
          <Demo title="Tabla">
            <Table>
              <thead>
                <tr>
                  <Th>Venta</Th>
                  <Th>Mesa</Th>
                  <Th>Cliente</Th>
                  <Th align="right">Platos</Th>
                  <Th align="right">Total</Th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["#1042", "Terraza 2", "Ana Pérez", "5", "48.50"],
                  ["#1041", "—", "Luis (para llevar)", "1", "9.00"],
                  ["#1040", "Mesa 4", "—", "8", "104.25"],
                ].map(([id, mesa, cliente, platos, total]) => (
                  <Tr key={id}>
                    <Td className="font-medium">{id}</Td>
                    <Td className="text-fg-2">{mesa}</Td>
                    <Td className="text-fg-2">{cliente}</Td>
                    <Td align="right">{platos}</Td>
                    <Td align="right">
                      <Money value={total ?? "0"} simbolo="$" />
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Demo>
        </div>

        <div className="desk:col-span-2">
          <Demo title="Vacío">
            <EmptyState
              title="Sala tranquila"
              description="No hay comandas abiertas. Las que lleguen por QR aparecerán aquí al instante."
              action={<Button variant="line">Abrir comanda</Button>}
              className="py-6"
            />
          </Demo>
        </div>
      </div>

      <Sheet
        open={sheet}
        onOpenChange={setSheet}
        title="Tu pedido"
        description="Mesa 4 · 3 platos"
        footer={
          <Button size="lg" className="w-full" onClick={() => setSheet(false)}>
            Pedir · $ 31,00
          </Button>
        }
      >
        <ul className="flex flex-col">
          {[
            ["Hamburguesa doble", "14.00"],
            ["Papas rústicas", "6.50"],
            ["Limonada de coco", "10.50"],
          ].map(([n, p]) => (
            <li key={n} className="flex items-baseline justify-between border-b border-line py-4">
              <span className="text-title">{n}</span>
              <Money value={p ?? "0"} simbolo="$" />
            </li>
          ))}
        </ul>
      </Sheet>

      <Dialog
        open={dialog}
        onOpenChange={setDialog}
        title="¿Cancelar la comanda 128?"
        description="Se libera el stock reservado y la mesa queda libre. No se puede deshacer."
        actions={
          <>
            <Button variant="ghost" onClick={() => setDialog(false)}>
              Volver
            </Button>
            <Button
              onClick={() => {
                setDialog(false);
                toast({ title: "Comanda 128 cancelada", tone: "err" });
              }}
            >
              Cancelar comanda
            </Button>
          </>
        }
      />

      <CommandPalette open={palette} onOpenChange={setPalette} items={comandos} />
    </Section>
  );
}

function Demo({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <h3 className="eyebrow">{title}</h3>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ movimiento */
type Paso = "en_cocina" | "preparando" | "listo";
const PASOS: { id: Paso; label: string }[] = [
  { id: "listo", label: "Listo" },
  { id: "preparando", label: "Preparando" },
  { id: "en_cocina", label: "En cocina" },
];

function Movimiento() {
  const [platos, setPlatos] = useState<{ id: string; nombre: string; estado: Paso }[]>([
    { id: "1", nombre: "Hamburguesa #1", estado: "preparando" },
    { id: "2", nombre: "Hamburguesa #2", estado: "en_cocina" },
    { id: "3", nombre: "Limonada #1", estado: "listo" },
    { id: "4", nombre: "Papas #1", estado: "en_cocina" },
  ]);
  const listos = platos.filter((p) => p.estado === "listo").length;

  const avanzar = () =>
    setPlatos((ps) => {
      const i = ps.findIndex((p) => p.estado !== "listo");
      if (i === -1) return ps.map((p) => ({ ...p, estado: "en_cocina" as Paso }));
      return ps.map((p, j) => (j === i ? { ...p, estado: p.estado === "en_cocina" ? "preparando" : "listo" } : p));
    });

  return (
    <Section
      id="movimiento"
      n="06"
      title="Movimiento"
      lead="Resortes rápidos, de 150 a 350 ms. Cuando un plato cambia de estado, sube a su grupo. Con movimiento reducido todo pasa a un fundido corto."
    >
      <div className="grid gap-16 desk:grid-cols-12">
        <div className="flex flex-col gap-8 desk:col-span-5">
          <p className="font-display text-display-l">
            {listos} de {platos.length}
            <span className="block font-sans text-lead font-normal text-fg-2">platos listos</span>
          </p>
          <Button variant="line" onClick={avanzar} className="self-start">
            Simular evento de cocina
          </Button>
          <dl className="grid grid-cols-3 gap-4 border-t border-line pt-6 text-sm">
            {[
              ["snappy", "520 / 38", "Toques"],
              ["smooth", "300 / 32", "Layout"],
              ["sheet", "380 / 40", "Capas"],
            ].map(([n, v, u]) => (
              <div key={n} className="flex flex-col gap-1">
                <dt className="font-medium text-fg">{n}</dt>
                <dd className="tabular text-fg-3">{v}</dd>
                <dd className="text-fg-3">{u}</dd>
              </div>
            ))}
          </dl>
        </div>
        <LayoutGroup>
          <div className="flex flex-col gap-8 desk:col-span-7">
            {PASOS.map((paso) => {
              const grupo = platos.filter((p) => p.estado === paso.id);
              return (
                <motion.div layout transition={smooth} key={paso.id} className="flex flex-col gap-2">
                  <motion.h3 layout="position" transition={smooth} className="eyebrow">
                    {paso.label}
                  </motion.h3>
                  <ul className="flex flex-col">
                    <AnimatePresence initial={false} mode="popLayout">
                      {grupo.map((p) => (
                        <motion.li
                          key={p.id}
                          layoutId={`plato-${p.id}`}
                          transition={smooth}
                          className="flex items-center justify-between border-t border-line py-4"
                        >
                          <span className={cn("text-title font-medium", p.estado === "listo" ? "text-fg" : "text-fg-2")}>{p.nombre}</span>
                          <StatusDot tone={p.estado === "listo" ? "ok" : p.estado === "preparando" ? "neutral" : "muted"}>{paso.label}</StatusDot>
                        </motion.li>
                      ))}
                    </AnimatePresence>
                    {grupo.length === 0 && (
                      <motion.li layout className="border-t border-line py-4 text-sm text-fg-4">
                        —
                      </motion.li>
                    )}
                  </ul>
                </motion.div>
              );
            })}
          </div>
        </LayoutGroup>
      </div>
    </Section>
  );
}
