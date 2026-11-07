import type { TipoDocumento } from "@/lib/api/schemas";

/** "J123456789" -> "J-12345678-9" · "V12345678" -> "V-12345678" (mismo formato que el backend). */
export function formatoRif(rif: string): string {
  return formatoDocumento(rif.slice(0, 1) as TipoDocumento, rif.slice(1));
}

export function formatoDocumento(tipo: TipoDocumento | null, numero: string | null): string {
  if (!numero) return "";
  if ((tipo === "J" || tipo === "G") && numero.length >= 9) return `${tipo}-${numero.slice(0, -1)}-${numero.slice(-1)}`;
  return tipo ? `${tipo}-${numero}` : numero;
}

export const TIPO_DOCUMENTO_LABEL: Record<TipoDocumento, string> = {
  V: "V · Venezolano",
  E: "E · Extranjero",
  J: "J · Jurídico",
  G: "G · Gobierno",
  P: "P · Pasaporte",
};
