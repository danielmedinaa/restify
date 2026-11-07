/** "1500.000" -> "1.500" (cantidades de stock: decimales solo si los hay). */
export function cantidad(v: string): string {
  const [ent = "0", dec = ""] = v.split(".");
  const d = dec.replace(/0+$/, "");
  const e = ent.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return d ? `${e},${d}` : e;
}
