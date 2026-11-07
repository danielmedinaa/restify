import {
  Armchair,
  Bell,
  BookOpen,
  ChartColumn,
  ChefHat,
  History,
  Coins,
  KeyRound,
  LayoutGrid,
  Package,
  ReceiptText,
  ScanLine,
  Settings2,
  ShoppingCart,
  TrendingUp,
  Truck,
  Wallet,
  ShieldCheck,
  Store,
  Tags,
  UserCog,
  Users,
  UtensilsCrossed,
  Ruler,
  Wheat,
  type LucideIcon,
} from "lucide-react";
import { can } from "@/features/auth/useMe";
import type { Me, Modulo } from "@/lib/api/schemas";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Permiso de lectura que hace visible el ítem */
  modulo?: Modulo;
  superadmin?: boolean;
  /** Etapa del plan en que se construye (para la pantalla "en camino") */
  etapa: number;
  keywords?: string[];
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    label: "Operación",
    items: [
      { href: "/panel", label: "Sala", icon: LayoutGrid, modulo: "mesas", etapa: 3, keywords: ["mesas", "mapa"] },
      { href: "/panel/comandas", label: "Comandas", icon: ReceiptText, modulo: "comandas", etapa: 3, keywords: ["pedidos", "caja", "cobrar"] },
      { href: "/panel/caja-turno", label: "Turno de caja", icon: Wallet, modulo: "caja", etapa: 3, keywords: ["arqueo", "cierre", "abrir caja", "gaveta"] },
      { href: "/cocina", label: "Cocina", icon: ChefHat, modulo: "cocina", etapa: 4, keywords: ["kds", "pantalla de cocina"] },
      { href: "/panel/clientes", label: "Clientes", icon: Users, modulo: "clientes", etapa: 3 },
    ],
  },
  {
    label: "Inventario",
    items: [
      { href: "/panel/inventario", label: "Existencias", icon: Package, modulo: "inventario", etapa: 6, keywords: ["stock"] },
      { href: "/panel/reponer", label: "Reponer", icon: ScanLine, modulo: "inventario", etapa: 6, keywords: ["escanear", "código", "qr", "barras", "entrada"] },
      { href: "/panel/alertas", label: "Alertas", icon: Bell, modulo: "inventario", etapa: 6, keywords: ["stock bajo"] },
      { href: "/panel/insumos", label: "Insumos", icon: Wheat, modulo: "insumos", etapa: 6 },
      { href: "/panel/unidades", label: "Unidades", icon: Ruler, modulo: "insumos", etapa: 6, keywords: ["medida", "kilos", "litros", "cajas", "presentación"] },
      { href: "/panel/compras", label: "Compras", icon: ShoppingCart, modulo: "compras", etapa: 6, keywords: ["proveedor", "costo", "factura de compra"] },
      { href: "/panel/proveedores", label: "Proveedores", icon: Truck, modulo: "compras", etapa: 6 },
    ],
  },
  {
    label: "Catálogo",
    items: [
      { href: "/panel/productos", label: "Productos", icon: UtensilsCrossed, modulo: "productos", etapa: 6, keywords: ["menú", "platos"] },
      { href: "/panel/categorias", label: "Categorías", icon: Tags, modulo: "categorias", etapa: 6 },
      { href: "/panel/estaciones", label: "Estaciones", icon: ChefHat, modulo: "categorias", etapa: 6, keywords: ["cocina", "barra", "preparación"] },
      { href: "/panel/recetas", label: "Recetas", icon: BookOpen, modulo: "recetas", etapa: 6 },
    ],
  },
  {
    label: "Negocio",
    items: [
      { href: "/panel/ventas", label: "Ventas", icon: ChartColumn, modulo: "ventas", etapa: 6, keywords: ["reportes"] },
      { href: "/panel/rentabilidad", label: "Rentabilidad", icon: TrendingUp, modulo: "ventas", etapa: 6, keywords: ["margen", "costo", "food cost"] },
    ],
  },
  {
    label: "Administración",
    items: [
      { href: "/panel/admin/usuarios", label: "Usuarios", icon: UserCog, modulo: "usuarios", etapa: 7 },
      { href: "/panel/admin/roles", label: "Roles", icon: ShieldCheck, modulo: "roles", etapa: 7, keywords: ["permisos"] },
      { href: "/panel/admin/sucursales", label: "Sucursales", icon: Store, modulo: "sucursales", etapa: 7 },
      { href: "/panel/admin/monedas", label: "Monedas", icon: Coins, modulo: "monedas", etapa: 7, keywords: ["tasas"] },
      { href: "/panel/admin/mesas", label: "Mesas y QR", icon: Armchair, modulo: "mesas", etapa: 7 },
      { href: "/panel/admin/bitacora", label: "Bitácora", icon: History, modulo: "bitacora", etapa: 7, keywords: ["auditoría", "historial", "quién"] },
      { href: "/panel/admin/configuracion", label: "Configuración", icon: Settings2, superadmin: true, etapa: 7, keywords: ["ajustes", "env", "igtf", "cédula", "token", "zona horaria"] },
      { href: "/panel/admin/seguridad", label: "Seguridad", icon: KeyRound, superadmin: true, etapa: 7, keywords: ["api keys", "auditoría"] },
    ],
  },
];

export function visible(item: NavItem, me: Me | undefined): boolean {
  if (item.superadmin) return !!me?.es_superadmin;
  return item.modulo ? can(me, item.modulo, "leer") : true;
}

export function navFor(me: Me | undefined): NavGroup[] {
  return NAV.map((g) => ({ ...g, items: g.items.filter((i) => visible(i, me)) })).filter((g) => g.items.length > 0);
}

export function findNav(pathname: string): NavItem | undefined {
  return NAV.flatMap((g) => g.items).find((i) => i.href === pathname);
}

export function isActive(href: string, pathname: string): boolean {
  return href === "/panel" ? pathname === "/panel" : pathname === href || pathname.startsWith(`${href}/`);
}
