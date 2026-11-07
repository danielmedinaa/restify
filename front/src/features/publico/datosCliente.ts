/** Validación de nombre y teléfono del cliente, igual a la del backend (schemas/fiscal.py). */

const LETRA = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/g;

export function nombreValido(v: string): boolean {
  const limpio = v.replace(/\s+/g, " ").trim();
  return /^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .-]{2,60}$/.test(limpio) && (limpio.match(LETRA)?.length ?? 0) >= 2;
}

/** Celular venezolano en cualquier formato (0412 123 4567, +58 412…) o número extranjero con +código. */
export function telefonoValido(v: string): boolean {
  const d = v.replace(/[\s().-]/g, "");
  return /^(?:\+?58)?0?4(?:12|14|16|22|24|26)\d{7}$/.test(d) || /^\+[1-9]\d{7,14}$/.test(d);
}
