import { cookies } from "next/headers";
import { PanelShell } from "@/features/panel/PanelShell";
import { SUCURSAL_COOKIE } from "@/features/panel/constants";

export default async function PanelLayout({ children }: { children: React.ReactNode }) {
  const raw = (await cookies()).get(SUCURSAL_COOKIE)?.value;
  const initialSucursalId = raw && /^\d+$/.test(raw) ? Number(raw) : null;
  return <PanelShell initialSucursalId={initialSucursalId}>{children}</PanelShell>;
}
