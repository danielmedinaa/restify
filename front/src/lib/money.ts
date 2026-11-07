import Big from "big.js";

/**
 * El dinero llega del backend como string decimal ("1234.50"). Nunca se pasa a float:
 * para mostrar se formatea el string, y la única aritmética del cliente (vista previa
 * de caja) usa big.js replicando el redondeo del backend (ROUND_HALF_UP a 2 decimales).
 */

Big.DP = 28; // misma precisión que el contexto Decimal de Python
Big.RM = Big.roundHalfUp;

const MILES = ".";
const DECIMAL = ",";

export type Operacion = "multiplicar" | "dividir";

export function formatAmount(value: string, decimals = 2): string {
  const raw = value.trim();
  const negative = raw.startsWith("-");
  const [intPart = "0", fracPart = ""] = raw.replace(/^[-+]/, "").split(".");
  const int = (intPart.replace(/^0+(?=\d)/, "") || "0").replace(/\B(?=(\d{3})+(?!\d))/g, MILES);
  const frac = fracPart.padEnd(decimals, "0").slice(0, decimals);
  return `${negative ? "-" : ""}${int}${decimals > 0 ? DECIMAL + frac : ""}`;
}

export function formatMoney(value: string, simbolo?: string): string {
  const amount = formatAmount(value);
  return simbolo ? `${simbolo} ${amount}` : amount;
}

/** Acepta lo que escribe una persona ("1.234,5" o "1234.5") y devuelve "1234.5", o null. */
export function parseAmountInput(input: string): string | null {
  const s = input.replace(/\s/g, "");
  if (!s) return null;
  const lastComma = s.lastIndexOf(",");
  const lastDot = s.lastIndexOf(".");
  const decimalSep = lastComma > lastDot ? "," : lastDot > -1 && s.length - lastDot - 1 <= 2 ? "." : null;
  let normalized = s;
  if (decimalSep === ",") normalized = s.replace(/\./g, "").replace(",", ".");
  else if (decimalSep === ".") normalized = s.replace(/,/g, "");
  else normalized = s.replace(/[.,]/g, "");
  return /^\d+(\.\d{0,2})?$/.test(normalized) ? normalized.replace(/\.$/, "") : null;
}

const q2 = (b: Big) => b.round(2, Big.roundHalfUp).toFixed(2);

/** Monto en la moneda indicada -> moneda principal (app/services/monedas.py: a_principal). */
export function toPrincipal(monto: string, tasa: string, operacion: Operacion): string {
  const m = new Big(monto);
  return q2(operacion === "multiplicar" ? m.div(tasa) : m.times(tasa));
}

/** Moneda principal -> moneda indicada (app/services/monedas.py: desde_principal). */
export function fromPrincipal(monto: string, tasa: string, operacion: Operacion): string {
  const m = new Big(monto);
  return q2(operacion === "multiplicar" ? m.times(tasa) : m.div(tasa));
}

/** a - b sin bajar de cero, en string. */
export function remaining(total: string, paid: string): string {
  const r = new Big(total).minus(paid);
  return r.lt(0) ? "0.00" : r.toFixed(2);
}

/** ¿El monto es mayor que cero? (comparación decimal exacta, sin float) */
export function isPositive(value: string): boolean {
  return new Big(value).gt(0);
}

/**
 * Monto en la moneda indicada que cubre EXACTAMENTE `pendiente` (moneda principal).
 * Redondea hacia arriba al centavo para que, al volver a la principal con el
 * redondeo del backend, no quede 0,01 por cobrar.
 */
export function coverIn(pendiente: string, tasa: string, operacion: Operacion): string {
  const p = new Big(pendiente);
  const raw = operacion === "multiplicar" ? p.times(tasa) : p.div(tasa);
  let m = raw.round(2, Big.roundUp);
  while (new Big(toPrincipal(m.toFixed(2), tasa, operacion)).lt(p)) m = m.plus("0.01");
  return m.toFixed(2);
}

/** a - b (puede ser negativo), en string con 2 decimales. */
export function minus(a: string, b: string): string {
  return new Big(a).minus(b).toFixed(2);
}

/**
 * IGTF dentro de un pago en divisas (app/services/comandas.py: registrar_pago): el pago lleva
 * el impuesto incluido, así que lo que abona a la cuenta es pago − q2(pago · pct / (100 + pct)).
 */
export function abonoConIgtf(montoPrincipal: string, pct: string): string {
  const m = new Big(montoPrincipal);
  return m.minus(q2(m.times(pct).div(new Big(100).plus(pct)))).toFixed(2);
}

/** Pago en moneda principal que, quitándole el IGTF, cubre exactamente `pendiente`. */
export function cubrirConIgtf(pendiente: string, pct: string): string {
  const p = new Big(pendiente);
  let m = p.times(new Big(100).plus(pct)).div(100).round(2, Big.roundDown);
  while (new Big(abonoConIgtf(m.toFixed(2), pct)).lt(p)) m = m.plus("0.01");
  return m.toFixed(2);
}
