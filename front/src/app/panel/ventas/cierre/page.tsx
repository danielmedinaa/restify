import type { Metadata } from "next";
import { CierreDia } from "@/features/ventas/CierreDia";

export const metadata: Metadata = { title: "Cierre del día" };

export default function CierrePage() {
  return <CierreDia />;
}
