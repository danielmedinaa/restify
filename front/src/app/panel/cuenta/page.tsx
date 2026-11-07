"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { useMe } from "@/features/auth/useMe";
import { logout } from "@/features/panel/session";
import { api } from "@/lib/api/client";
import { ApiError, describeError } from "@/lib/api/errors";

/** Mismas reglas que el backend (app/schemas/usuarios.py: _validar_password). */
function passwordProblem(p: string): string | null {
  if (p.length < 10) return "Debe tener al menos 10 caracteres.";
  if (p.toLowerCase() === p || p.toUpperCase() === p || !/\d/.test(p)) return "Combina mayúsculas, minúsculas y números.";
  return null;
}

export default function CuentaPage() {
  const router = useRouter();
  const { data: me } = useMe();
  const [errors, setErrors] = useState<{ actual?: string; nueva?: string; repetir?: string; general?: string }>({});
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const actual = String(f.get("actual") ?? "");
    const nueva = String(f.get("nueva") ?? "");
    const repetir = String(f.get("repetir") ?? "");
    const next = {
      actual: actual ? undefined : "Escribe tu contraseña actual.",
      nueva: passwordProblem(nueva) ?? undefined,
      repetir: nueva === repetir ? undefined : "No coincide con la nueva.",
    };
    setErrors(next);
    if (next.actual || next.nueva || next.repetir) return;

    setPending(true);
    try {
      await api("/auth/cambiar-password", { method: "POST", body: { password_actual: actual, password_nueva: nueva } });
      // El backend revoca todas las sesiones: hay que volver a entrar
      await logout();
      router.replace("/login?motivo=password");
    } catch (err) {
      // 401 aquí significa contraseña actual incorrecta (la sesión sigue viva)
      if (err instanceof ApiError && err.status === 401) setErrors({ actual: "No es tu contraseña actual." });
      else setErrors({ general: describeError(err).title });
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow={me?.email} title="Mi cuenta" />
      <div className="grid gap-16 desk:grid-cols-12">
        <dl className="flex flex-col desk:col-span-5">
          {[
            ["Nombre", me?.nombre],
            ["Rol", me?.es_superadmin ? "Superadmin" : (me?.rol?.nombre ?? "Sin rol")],
            ["Sucursales", me?.es_superadmin ? "Todas" : me?.sucursales.map((s) => s.nombre).join(", ") || "Ninguna"],
          ].map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-6 border-b border-line py-4">
              <dt className="text-sm text-fg-3">{k}</dt>
              <dd className="text-right text-base">{v}</dd>
            </div>
          ))}
        </dl>
        <form onSubmit={onSubmit} noValidate className="flex max-w-md flex-col gap-8 desk:col-span-6 desk:col-start-7">
          <h2 className="text-h3 font-medium">Cambiar contraseña</h2>
          <Field label="Contraseña actual" name="actual" type="password" autoComplete="current-password" error={errors.actual} />
          <Field
            label="Nueva"
            name="nueva"
            type="password"
            autoComplete="new-password"
            hint="10 caracteres o más, con mayúsculas, minúsculas y números."
            error={errors.nueva}
          />
          <Field label="Repite la nueva" name="repetir" type="password" autoComplete="new-password" error={errors.repetir} />
          {errors.general && (
            <p role="alert" className="text-base text-err">
              {errors.general}
            </p>
          )}
          <p className="text-sm text-fg-3">Al cambiarla se cierran tus sesiones en todos los dispositivos.</p>
          <Button type="submit" loading={pending} className="self-start">
            Cambiar contraseña
          </Button>
        </form>
      </div>
    </>
  );
}
