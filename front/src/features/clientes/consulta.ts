import { api } from "@/lib/api/client";
import { ConsultaCedulaOut } from "@/lib/api/schemas";

export type ConsultaCedula = { nombre: string; rif: string | null; zona: string | null };

/**
 * Nombre de una persona por su cédula (servicio externo opcional del backend). Devuelve null
 * si no aparece, si el servicio no está configurado (503) o si falla: nunca bloquea el formulario.
 */
export async function consultarCedula(tipo: string | null, documento: string): Promise<ConsultaCedula | null> {
  const numero = documento.replace(/[\s.-]/g, "").toUpperCase().replace(/^[VEJGP]/, "");
  if ((tipo !== "V" && tipo !== "E") || !/^\d{5,10}$/.test(numero)) return null;
  try {
    return await api("/clientes/consulta-externa", { query: { tipo, numero }, schema: ConsultaCedulaOut.nullable() });
  } catch {
    return null;
  }
}
