import type { FuenteMarcaT, Tema } from "@/lib/api/schemas";

/**
 * CSS de la marca del restaurante a partir del tema guardado. Lo que llega del backend ya
 * viene validado, pero aquí se vuelve a filtrar todo con listas estrictas: este texto se
 * inyecta en un <style>, así que nada que no cuadre con estos patrones pasa.
 */
const HEX = /^#[0-9a-f]{6}$/;
const URL_MEDIA = /^\/media\/[A-Za-z0-9._-]+$/;
const PESO = /^[0-9]{3}( [0-9]{3})?$/;
const RANGO = /^[0-9A-Fa-f+?,\- U]+$/;
const FORMATOS = new Set(["woff2", "woff", "opentype", "truetype"]);
const FAMILIA = /^[A-Za-z0-9 ]{2,60}$/;

/** Temas listos: un clic y se rellena toda la paleta (después se puede ajustar color por color). */
export const TEMAS_LISTOS: { nombre: string; colores: Tema["colores"] }[] = [
  { nombre: "RESTIFY (oscuro)", colores: { fondo: null, texto: null, acento: null, texto_acento: null, superficie: null, linea: null, ok: null, aviso: null, error: null } },
  { nombre: "Crema y vino", colores: { fondo: "#f7f1e8", texto: "#2b1d1a", acento: "#8c2f39", texto_acento: "#ffffff", superficie: "#efe5d6", linea: "#dccdb8", ok: "#4f7a4a", aviso: "#b07a1f", error: "#b3261e" } },
  { nombre: "Blanco y verde", colores: { fondo: "#fafbf8", texto: "#16241b", acento: "#1f7a4d", texto_acento: "#ffffff", superficie: "#eef3ec", linea: "#d5e0d3", ok: "#1f7a4d", aviso: "#b07a1f", error: "#b3261e" } },
  { nombre: "Carbón y naranja", colores: { fondo: "#161616", texto: "#f4f1ec", acento: "#ff7a1a", texto_acento: "#1a0e03", superficie: "#212121", linea: "#343434", ok: "#7fb069", aviso: "#e0b04a", error: "#e5675b" } },
  { nombre: "Medianoche azul", colores: { fondo: "#0f1624", texto: "#e9eefb", acento: "#5b8def", texto_acento: "#06122b", superficie: "#172036", linea: "#27334f", ok: "#6cc59a", aviso: "#e2b857", error: "#ee7d7d" } },
  { nombre: "Bosque", colores: { fondo: "#12201a", texto: "#eaf2ec", acento: "#c9e265", texto_acento: "#14210a", superficie: "#1a2c24", linea: "#2b4236", ok: "#8fd19e", aviso: "#e5c26a", error: "#e58a7d" } },
];

export const BASE = { fondo: "#1a1819", texto: "#ffffff", acento: "#ffffff" } as const;

function rgb(h: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
}

export function luminancia(h: string): number {
  const [r, g, b] = rgb(h).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contraste(a: string, b: string): number {
  const [hi, lo] = [luminancia(a), luminancia(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

export function esHex(v: string | null | undefined): v is string {
  return !!v && HEX.test(v.toLowerCase());
}

/** Variables CSS de los colores (vacío si no se personalizó ninguno). */
export function variablesColores(c: Tema["colores"]): Record<string, string> {
  if (!Object.values(c).some(esHex)) return {};
  const fondo = esHex(c.fondo) ? c.fondo.toLowerCase() : BASE.fondo;
  const texto = esHex(c.texto) ? c.texto.toLowerCase() : BASE.texto;
  const acento = esHex(c.acento) ? c.acento.toLowerCase() : BASE.acento;
  const oscuro = luminancia(fondo) < 0.4;
  // Texto sobre los botones de acento: el color de fondo si se lee bien, si no negro o blanco
  const auto = contraste(acento, fondo) >= 4.5 ? fondo : luminancia(acento) > 0.4 ? "#000000" : "#ffffff";
  const ink = esHex(c.texto_acento) ? c.texto_acento.toLowerCase() : auto;
  const superficie = esHex(c.superficie) ? c.superficie.toLowerCase() : null;
  const linea = esHex(c.linea) ? c.linea.toLowerCase() : null;
  const [r, g, b] = rgb(texto);
  const t = (a: number) => `rgb(${r} ${g} ${b} / ${a})`;
  const [fr, fg, fb] = rgb(fondo);
  return {
    "--color-canvas": fondo,
    "--color-ink": ink,
    "--color-paper": acento,
    "--color-raised": superficie ?? `color-mix(in srgb, ${texto} 4%, ${fondo})`,
    "--color-overlay": superficie ? `color-mix(in srgb, ${texto} 5%, ${superficie})` : `color-mix(in srgb, ${texto} 7%, ${fondo})`,
    "--color-sunken": oscuro ? `color-mix(in srgb, #000000 25%, ${fondo})` : `color-mix(in srgb, ${texto} 5%, ${fondo})`,
    "--color-fg": t(0.94),
    "--color-fg-2": t(0.68),
    "--color-fg-3": t(0.52),
    "--color-fg-4": t(0.32),
    "--color-line": linea ?? t(0.1),
    "--color-line-strong": linea ? `color-mix(in srgb, ${texto} 14%, ${linea})` : t(0.2),
    "--color-wash": t(0.04),
    "--color-wash-strong": t(0.08),
    "--color-veil": `rgb(${fr} ${fg} ${fb} / 0.72)`,
    ...(esHex(c.ok) ? { "--color-ok": c.ok.toLowerCase() } : {}),
    ...(esHex(c.aviso) ? { "--color-warn": c.aviso.toLowerCase() } : {}),
    ...(esHex(c.error) ? { "--color-err": c.error.toLowerCase() } : {}),
  };
}

function carasCss(familia: string, f: FuenteMarcaT): string {
  return f.caras
    .filter((c) => URL_MEDIA.test(c.url) && PESO.test(c.peso) && (c.estilo === "normal" || c.estilo === "italic") && FORMATOS.has(c.formato))
    .map((c) => {
      const rango = c.rango && RANGO.test(c.rango) ? `unicode-range:${c.rango};` : "";
      return `@font-face{font-family:"${familia}";src:url("${c.url}") format("${c.formato}");font-weight:${c.peso};font-style:${c.estilo};font-display:swap;${rango}}`;
    })
    .join("");
}

/** Solo los @font-face (la pantalla de personalización los usa para mostrar la vista previa). */
export function fuentesCss(t: Pick<Tema, "titulo" | "texto">): string {
  return (t.titulo ? carasCss("Marca Titulo", t.titulo) : "") + (t.texto ? carasCss("Marca Texto", t.texto) : "");
}

export function temaCss(t: Tema): string {
  const vars = Object.entries(variablesColores(t.colores));
  const fuentes: string[] = [];
  if (t.titulo && FAMILIA.test(t.titulo.familia) && t.titulo.caras.length) {
    fuentes.push(`--font-display:"Marca Titulo","Gagalin","General Sans",ui-sans-serif,sans-serif`);
  }
  if (t.texto && FAMILIA.test(t.texto.familia) && t.texto.caras.length) {
    fuentes.push(`--font-sans:"Marca Texto","General Sans",ui-sans-serif,sans-serif`);
  }
  const base = vars.length && !(luminancia(variablesColores(t.colores)["--color-canvas"]!) < 0.4) ? "color-scheme:light;" : "";
  const decl = [...vars.map(([k, v]) => `${k}:${v}`), ...fuentes].join(";");
  const raiz = decl || base ? `:root{${base}${decl}}` : "";
  return fuentesCss(t) + raiz;
}
