import type { Metadata } from "next";
import { cookies } from "next/headers";
import { SUCURSAL_COOKIE } from "@/features/panel/constants";
import { KdsScreen } from "@/features/cocina/KdsScreen";

export const metadata: Metadata = { title: "Cocina" };

export default async function CocinaPage() {
  const raw = (await cookies()).get(SUCURSAL_COOKIE)?.value;
  return <KdsScreen initialSucursalId={raw && /^\d+$/.test(raw) ? Number(raw) : null} />;
}
