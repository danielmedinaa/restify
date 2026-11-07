"use client";

import { SinAcceso } from "@/components/layout/Estados";
import { can, useMe } from "@/features/auth/useMe";
import { Reponer } from "@/features/inventario/Reponer";

export default function ReponerPage() {
  const { data: me } = useMe();
  if (!can(me, "inventario")) return <SinAcceso />;
  return <Reponer />;
}
