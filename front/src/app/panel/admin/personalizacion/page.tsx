"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { useRef, useState } from "react";
import { ListError, ListLoading, SinAcceso } from "@/components/layout/Estados";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ErrorBox } from "@/components/ui/ErrorBox";
import { Field } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Segmented";
import { toast } from "@/components/ui/Toast";
import { useMe } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { EstadoPersonalizacionOut, type FuenteMarcaT, type Tema } from "@/lib/api/schemas";
import { BASE, contraste, esHex, fuentesCss, TEMAS_LISTOS, variablesColores } from "@/lib/tema";

const KEY = ["personalizacion"];
type Colores = Tema["colores"];
type Rol = "titulo" | "texto";

export default function PersonalizacionPage() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const estado = useQuery({ queryKey: KEY, queryFn: () => api("/personalizacion", { schema: EstadoPersonalizacionOut }), enabled: !!me?.es_superadmin });
  const [error, setError] = useState<ErrorView | null>(null);

  /** Todas las acciones devuelven el estado nuevo: se guarda tal cual y se avisa. */
  const accion = useMutation({
    mutationFn: ({ ruta, metodo = "POST", body }: { ruta: string; metodo?: "POST" | "PUT" | "DELETE"; body?: unknown; aviso: string }) =>
      api(`/personalizacion${ruta}`, { method: metodo, body, schema: EstadoPersonalizacionOut }),
    onSuccess: (d, v) => {
      qc.setQueryData(KEY, d);
      setError(null);
      toast({ title: v.aviso, description: "Se aplica en todo el sistema en unos segundos.", tone: "ok", duration: 3500 });
    },
    onError: (e) => setError(describeError(e)),
  });
  const ejecutar = (ruta: string, aviso: string, metodo: "POST" | "PUT" | "DELETE" = "POST", body?: unknown) => accion.mutate({ ruta, metodo, body, aviso });

  if (!me?.es_superadmin) return <SinAcceso />;
  if (estado.isPending) return <ListLoading />;
  if (estado.isError) return <ListError error={estado.error} />;
  const { disponible, plan, tema } = estado.data;
  const ocupado = accion.isPending;

  return (
    <>
      <style>{fuentesCss(tema)}</style>
      <PageHeader
        eyebrow="Solo superadmin"
        title="Personalización"
        actions={
          <Button
            variant="line"
            disabled={ocupado}
            onClick={() => {
              if (window.confirm("¿Volver a RESTIFY? Se quitarán tu logo, tus colores y tus tipografías (títulos y textos).")) ejecutar("", "Tema original restablecido", "DELETE");
            }}
          >
            Volver a RESTIFY
          </Button>
        }
      />
      <p className="-mt-6 mb-10 max-w-2xl text-base text-fg-2">
        El logo, los colores y la tipografía de tu restaurante en la carta pública, el seguimiento del pedido, las facturas y todo el sistema. El sello de RESTIFY se mantiene en el panel interno.
      </p>
      {!disponible && (
        <div className="mb-10 flex max-w-2xl items-start gap-3 border border-line-strong p-4">
          <Lock aria-hidden className="mt-0.5 size-5 shrink-0 text-warn" />
          <p className="text-base text-fg-2">
            La personalización no está incluida en tu plan{plan ? ` ${plan}` : ""}. Pide a RESTIFY el cambio al plan que la incluye para activarla; mientras tanto se ve la marca de RESTIFY.
          </p>
        </div>
      )}
      {error && (
        <div className="mb-8 max-w-2xl">
          <ErrorBox error={error} onClose={() => setError(null)} />
        </div>
      )}
      <fieldset disabled={!disponible || ocupado} className="flex max-w-3xl flex-col gap-14 disabled:opacity-60">
        <Logo url={tema.logo_url} onSubir={(f) => ejecutar("/logo", "Logo actualizado", "POST", formLogo(f))} onQuitar={() => ejecutar("/logo", "Logo quitado", "DELETE")} />
        <PaletaColores
          key={JSON.stringify(tema.colores)}
          tema={tema}
          onGuardar={(c) => ejecutar("/colores", "Colores guardados", "PUT", c)}
          onRestablecer={() => ejecutar("/colores", "Colores restablecidos", "PUT", TEMAS_LISTOS[0]!.colores)}
        />
        {(["titulo", "texto"] as const).map((rol) => (
          <Tipografia
            key={rol}
            rol={rol}
            fuente={tema[rol]}
            onGoogle={(familia) => ejecutar(`/fuente/${rol}/google`, "Tipografía aplicada", "POST", { familia })}
            onArchivo={(f, familia) => ejecutar(`/fuente/${rol}/archivo`, "Tipografía aplicada", "POST", formFuente(f, familia))}
            onQuitar={() => ejecutar(`/fuente/${rol}`, "Tipografía restablecida", "DELETE")}
          />
        ))}
      </fieldset>
    </>
  );
}

function formLogo(f: File) {
  const fd = new FormData();
  fd.append("archivo", f);
  return fd;
}
function formFuente(f: File, familia: string) {
  const fd = new FormData();
  fd.append("archivo", f);
  fd.append("familia", familia);
  return fd;
}

function Seccion({ titulo, children, nota }: { titulo: string; nota?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="font-display text-display-s">{titulo}</h2>
        {nota && <p className="pt-1 text-sm text-fg-3">{nota}</p>}
      </div>
      {children}
    </section>
  );
}

function Logo({ url, onSubir, onQuitar }: { url: string | null; onSubir: (f: File) => void; onQuitar: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <Seccion titulo="Logo" nota="PNG, JPG o WEBP de hasta 2 MB. Mejor con fondo transparente. No se aceptan SVG por seguridad.">
      <div className="flex flex-wrap items-center gap-6">
        <div className="grid h-24 min-w-40 place-items-center border border-line px-4">
          {url ? (
            // eslint-disable-next-line @next/next/no-img-element -- vista previa del logo guardado
            <img src={url} alt="Logo actual" className="max-h-20 w-auto object-contain" />
          ) : (
            <span className="text-sm text-fg-3">Sin logo propio</span>
          )}
        </div>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onSubir(f);
            e.target.value = "";
          }}
        />
        <Button variant="line" onClick={() => input.current?.click()}>
          {url ? "Cambiar logo" : "Subir logo"}
        </Button>
        {url && (
          <Button variant="ghost" onClick={onQuitar}>
            Quitar
          </Button>
        )}
      </div>
    </Seccion>
  );
}

const DEFECTO: Record<keyof Colores, string> = {
  fondo: BASE.fondo,
  texto: BASE.texto,
  acento: BASE.acento,
  texto_acento: "#1a1819",
  superficie: "#221f20",
  linea: "#3a3839",
  ok: "#93a68e",
  aviso: "#c4a978",
  error: "#cc8a7d",
};

const BASICOS: { k: keyof Colores; etiqueta: string; ayuda: string }[] = [
  { k: "fondo", etiqueta: "Fondo", ayuda: "El color de las pantallas." },
  { k: "texto", etiqueta: "Texto", ayuda: "Letras e íconos." },
  { k: "acento", etiqueta: "Acento", ayuda: "Botones y selección." },
];
const DETALLES: { k: keyof Colores; etiqueta: string; ayuda: string }[] = [
  { k: "texto_acento", etiqueta: "Texto del botón", ayuda: "Letra sobre el acento." },
  { k: "superficie", etiqueta: "Tarjetas", ayuda: "Paneles y ventanas." },
  { k: "linea", etiqueta: "Líneas", ayuda: "Bordes y separadores." },
  { k: "ok", etiqueta: "Correcto", ayuda: "Listo, pagado, disponible." },
  { k: "aviso", etiqueta: "Aviso", ayuda: "Pendiente, poco stock." },
  { k: "error", etiqueta: "Error", ayuda: "Problemas y anulaciones." },
];
const CAMPOS = [...BASICOS, ...DETALLES];

function Muestra({ k, etiqueta, ayuda, valor, onChange }: { k: keyof Colores; etiqueta: string; ayuda: string; valor: string | null; onChange: (v: string | null) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="eyebrow">{etiqueta}</span>
      <div className="flex items-center gap-3">
        <input
          type="color"
          aria-label={`Color de ${etiqueta.toLowerCase()}`}
          value={esHex(valor) ? valor : DEFECTO[k]}
          onChange={(e) => onChange(e.target.value)}
          className="h-11 w-14 cursor-pointer rounded-control border border-line-strong bg-transparent p-1"
        />
        <Field label="Código" aria-label={`Código de ${etiqueta.toLowerCase()}`} className="flex-1" placeholder={DEFECTO[k]} maxLength={7} value={valor ?? ""} onChange={(e) => onChange(e.target.value.trim() || null)} error={valor && !esHex(valor) ? "Usa #rrggbb" : null} />
      </div>
      <p className="text-sm text-fg-3">{ayuda}</p>
    </div>
  );
}

function PaletaColores({ tema, onGuardar, onRestablecer }: { tema: Tema; onGuardar: (c: Colores) => void; onRestablecer: () => void }) {
  const [c, setC] = useState<Colores>(tema.colores);
  const fondo = esHex(c.fondo) ? c.fondo : BASE.fondo;
  const texto = esHex(c.texto) ? c.texto : BASE.texto;
  const acento = esHex(c.acento) ? c.acento : BASE.acento;
  const invalido = CAMPOS.some(({ k }) => c[k] && !esHex(c[k]));
  const avisoTexto = contraste(texto, fondo) < 4.5 ? "El texto y el fondo se parecen demasiado: no se podría leer." : null;
  const avisoAcento = contraste(acento, fondo) < 3 ? "El acento casi no se distingue del fondo." : null;
  const avisoBoton = esHex(c.texto_acento) && contraste(c.texto_acento, acento) < 4.5 ? "La letra del botón no se lee sobre el acento." : null;
  const aviso = avisoTexto ?? avisoAcento ?? avisoBoton;
  const hayCambios = JSON.stringify(c) !== JSON.stringify(tema.colores);
  const vars: Record<string, string> = { ...variablesColores(c) };
  if (tema.titulo) vars["--font-display"] = '"Marca Titulo", "Gagalin", sans-serif';
  if (tema.texto) vars["--font-sans"] = '"Marca Texto", "General Sans", sans-serif';

  return (
    <Seccion titulo="Colores" nota="Parte de un tema listo y ajusta lo que quieras. Lo que dejes vacío se calcula solo a partir de los básicos.">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Temas listos">
        {TEMAS_LISTOS.map((m) => (
          <button
            key={m.nombre}
            type="button"
            onClick={() => setC(m.colores)}
            className="flex items-center gap-2 rounded-full border border-line-strong px-3 py-1.5 text-sm text-fg-2 transition-colors hover:bg-wash hover:text-fg"
          >
            <span aria-hidden className="flex">
              {[m.colores.fondo ?? BASE.fondo, m.colores.acento ?? BASE.acento, m.colores.texto ?? BASE.texto].map((col, i) => (
                <span key={i} className="-ml-1 size-4 rounded-full border border-line-strong first:ml-0" style={{ background: col }} />
              ))}
            </span>
            {m.nombre}
          </button>
        ))}
      </div>
      <div className="grid gap-6 tablet:grid-cols-3">
        {BASICOS.map((f) => (
          <Muestra key={f.k} {...f} valor={c[f.k]} onChange={(v) => setC({ ...c, [f.k]: v })} />
        ))}
      </div>
      <details className="group border-t border-line pt-4">
        <summary className="cursor-pointer text-base text-fg-2 hover:text-fg">Ajustar cada color a fondo</summary>
        <div className="grid gap-6 pt-6 tablet:grid-cols-3">
          {DETALLES.map((f) => (
            <Muestra key={f.k} {...f} valor={c[f.k]} onChange={(v) => setC({ ...c, [f.k]: v })} />
          ))}
        </div>
      </details>
      {aviso && <p className="text-sm text-warn">{aviso}</p>}
      <div style={vars as React.CSSProperties} className="flex flex-col gap-4 rounded-sheet border border-line bg-canvas p-6 text-fg">
        <span className="eyebrow">Vista previa</span>
        <p className="font-display text-display-s">Hamburguesa clásica</p>
        <div className="flex items-center justify-between gap-4 rounded-control border border-line bg-raised p-4">
          <div>
            <p className="text-base font-medium">Combo de la casa</p>
            <p className="text-sm text-fg-2">Carne, queso y papas fritas.</p>
          </div>
          <span className="text-base font-medium">Bs 3.500,00</span>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <span className="inline-flex h-10 items-center rounded-control bg-paper px-4 text-base font-medium text-ink">Pedir ahora</span>
          <span className="inline-flex h-10 items-center rounded-control border border-line-strong px-4 text-base text-fg">Ver carta</span>
          <span className="flex items-center gap-3 text-sm">
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-ok" />Listo</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-warn" />Pendiente</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-err" />Anulado</span>
          </span>
        </div>
      </div>
      <div className="flex gap-3">
        <Button disabled={!hayCambios || invalido || !!aviso} onClick={() => onGuardar(c)}>
          Guardar colores
        </Button>
        <Button variant="ghost" onClick={onRestablecer}>
          Restablecer solo los colores
        </Button>
      </div>
    </Seccion>
  );
}

function Tipografia({ rol, fuente, onGoogle, onArchivo, onQuitar }: { rol: Rol; fuente: FuenteMarcaT | null; onGoogle: (f: string) => void; onArchivo: (f: File, familia: string) => void; onQuitar: () => void }) {
  const [modo, setModo] = useState<"google" | "archivo">("google");
  const [familia, setFamilia] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const titulo = rol === "titulo" ? "Tipografía de los títulos" : "Tipografía de los textos";
  const nombreFuente = rol === "titulo" ? "Marca Titulo" : "Marca Texto";

  return (
    <Seccion titulo={titulo} nota={rol === "titulo" ? "Nombres de platos, encabezados y cifras grandes." : "Párrafos, botones, tablas y todo el resto."}>
      <div className="flex flex-col gap-1 border border-line p-4">
        <span className="eyebrow">{fuente ? `${fuente.familia} · ${fuente.origen === "google" ? "Google Fonts" : "archivo propio"}` : "Por defecto de RESTIFY"}</span>
        <p className="text-display-s leading-tight" style={fuente ? { fontFamily: `"${nombreFuente}", sans-serif` } : { fontFamily: rol === "titulo" ? "var(--font-display)" : "var(--font-sans)" }}>
          Hamburguesa clásica 0123456789
        </p>
      </div>
      <Segmented
        label="Origen de la fuente"
        value={modo}
        onChange={setModo}
        options={[
          { value: "google", label: "Google Fonts" },
          { value: "archivo", label: "Subir archivo" },
        ]}
      />
      <div className="flex flex-wrap items-end gap-4">
        <Field
          label={modo === "google" ? "Nombre en Google Fonts" : "Nombre de la fuente"}
          hint={modo === "google" ? "Tal cual aparece en fonts.google.com, por ejemplo Playfair Display." : "Para identificarla. Sube WOFF2, WOFF, OTF o TTF (hasta 3 MB)."}
          className="w-72"
          value={familia}
          maxLength={60}
          onChange={(e) => setFamilia(e.target.value)}
        />
        {modo === "archivo" && (
          <>
            <input ref={input} type="file" accept=".woff2,.woff,.otf,.ttf" hidden onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
            <Button variant="line" onClick={() => input.current?.click()}>
              {archivo ? archivo.name : "Elegir archivo"}
            </Button>
          </>
        )}
        <Button disabled={familia.trim().length < 2 || (modo === "archivo" && !archivo)} onClick={() => (modo === "google" ? onGoogle(familia.trim()) : onArchivo(archivo!, familia.trim()))}>
          Aplicar
        </Button>
        {fuente && (
          <Button variant="ghost" onClick={onQuitar}>
            Quitar
          </Button>
        )}
      </div>
      {modo === "archivo" && <p className="text-sm text-fg-3">Asegúrate de que la licencia de la fuente permita usarla en sitios web.</p>}
    </Seccion>
  );
}
