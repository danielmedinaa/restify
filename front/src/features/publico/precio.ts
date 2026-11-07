import Big from "big.js";
import type { Menu, MenuProducto } from "@/lib/api/schemas";
import type { LineaCarrito } from "./stores";

export interface MonedaVista {
  codigo: string;
  simbolo: string;
}

/** Moneda en que el cliente ve los precios: la elegida si existe, si no la principal. */
export function monedaVista(menu: Menu, elegida: string | null): MonedaVista {
  const lista = menu.monedas.filter((m) => m.activa);
  const m = lista.find((x) => x.codigo === elegida) ?? lista.find((x) => x.es_principal) ?? lista[0];
  return m ? { codigo: m.codigo, simbolo: m.simbolo } : { codigo: menu.moneda_principal, simbolo: "" };
}

/** Precio ya convertido por el backend (MenuProducto.precios); nunca se recalcula aquí. */
export function precioEn(p: MenuProducto, codigo: string): string {
  return p.precios.find((x) => x.moneda === codigo)?.monto ?? p.precio;
}

/** Total del carrito en una moneda: suma decimal exacta de los precios del backend. */
export function totalCarrito(lineas: LineaCarrito[], productos: Map<number, MenuProducto>, codigo: string): string {
  return lineas
    .reduce((acc, l) => {
      const p = productos.get(l.producto_id);
      return p ? acc.plus(new Big(precioEn(p, codigo)).times(l.cantidad)) : acc;
    }, new Big(0))
    .toFixed(2);
}

export function portada(p: MenuProducto) {
  return [...p.medios].sort((a, b) => Number(b.es_portada) - Number(a.es_portada) || a.orden - b.orden)[0];
}
