"use client";

import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { meKey } from "@/features/auth/useMe";
import { api } from "@/lib/api/client";
import { ApiError, describeError, type ErrorView } from "@/lib/api/errors";
import { MeOut } from "@/lib/api/schemas";
import { smooth } from "@/lib/motion";
import { useQueryClient } from "@tanstack/react-query";

type StepId = "token" | "admin" | "sucursal" | "moneda" | "revisar";

interface Plan {
  plan: string | null;
  vence_en: string | null;
  limites: Record<string, number | null>;
}

interface Moneda {
  codigo: string;
  nombre: string;
  simbolo: string;
}

const MONEDAS: Moneda[] = [
  { codigo: "USD", nombre: "Dólar estadounidense", simbolo: "$" },
  { codigo: "EUR", nombre: "Euro", simbolo: "€" },
  { codigo: "VES", nombre: "Bolívar", simbolo: "Bs" },
  { codigo: "COP", nombre: "Peso colombiano", simbolo: "$" },
  { codigo: "MXN", nombre: "Peso mexicano", simbolo: "$" },
];
const ZONA_INICIAL = "America/Caracas";
const ZONAS: [string, string][] = [
  ["America/Caracas", "Venezuela"],
  ["America/Bogota", "Colombia"],
  ["America/Mexico_City", "México"],
  ["America/Lima", "Perú"],
  ["America/Panama", "Panamá"],
  ["America/Santiago", "Chile"],
  ["America/Argentina/Buenos_Aires", "Argentina"],
  ["Europe/Madrid", "España"],
];
const ETIQUETA_LIMITE: Record<string, string> = {
  max_sucursales: "sucursales",
  max_salas: "salas",
  max_mesas: "mesas",
  max_productos: "productos",
  max_usuarios: "usuarios",
};

function passwordError(p: string): string | null {
  if (p.length < 10) return "Mínimo 10 caracteres.";
  if (p.toLowerCase() === p || p.toUpperCase() === p || !/\d/.test(p)) return "Combina mayúsculas, minúsculas y números.";
  return null;
}

export function SetupWizard({ requiereToken }: { requiereToken: boolean }) {
  const router = useRouter();
  const qc = useQueryClient();
  const pasos: StepId[] = [...(requiereToken ? (["token"] as const) : []), "admin", "sucursal", "moneda", "revisar"];
  const [i, setI] = useState(0);
  const paso: StepId = pasos[i] ?? "admin";

  const [token, setToken] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [admin, setAdmin] = useState({ nombre: "", email: "", password: "", repetir: "" });
  const [suc, setSuc] = useState({ nombre: "", direccion: "", telefono: "", rif: "", razon_social: "", domicilio_fiscal: "" });
  const [moneda, setMoneda] = useState<Moneda>({ codigo: "USD", nombre: "Dólar estadounidense", simbolo: "$" });
  const [zona, setZona] = useState(ZONA_INICIAL);
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [error, setError] = useState<ErrorView | null>(null);
  const [pending, setPending] = useState(false);

  const volver = () => {
    setError(null);
    setErrores({});
    setI((n) => Math.max(0, n - 1));
  };
  const avanzar = () => {
    setError(null);
    setErrores({});
    setI((n) => n + 1);
  };

  async function siguiente(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (paso === "token") return validarToken();
    if (paso === "admin") {
      const er: Record<string, string> = {};
      if (admin.nombre.trim().length < 2) er.nombre = "Escribe tu nombre.";
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(admin.email.trim())) er.email = "Correo no válido.";
      const pe = passwordError(admin.password);
      if (pe) er.password = pe;
      else if (admin.password !== admin.repetir) er.repetir = "Las contraseñas no coinciden.";
      setErrores(er);
      return Object.keys(er).length ? undefined : avanzar();
    }
    if (paso === "sucursal") {
      if (suc.nombre.trim().length < 2) return setErrores({ nombre: "Escribe el nombre de tu primer local." });
      return avanzar();
    }
    if (paso === "moneda") {
      const er: Record<string, string> = {};
      if (!/^[A-Z0-9]{2,10}$/.test(moneda.codigo)) er.codigo = "Código en mayúsculas (ej. USD).";
      if (!moneda.nombre.trim()) er.nombre = "Escribe el nombre.";
      if (!moneda.simbolo.trim()) er.simbolo = "Escribe el símbolo.";
      setErrores(er);
      return Object.keys(er).length ? undefined : avanzar();
    }
    return terminar();
  }

  async function validarToken() {
    if (token.trim().length < 10) return setErrores({ token: "Pega el token completo." });
    setPending(true);
    try {
      setPlan(await api<undefined>("/public/setup/token", { method: "POST", app: "public", body: { token: token.trim() } }) as Plan);
      avanzar();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && typeof err.detail === "string") setErrores({ token: err.detail });
      else setError(describeError(err));
    } finally {
      setPending(false);
    }
  }

  async function terminar() {
    setPending(true);
    const vacio = (v: string) => (v.trim() ? v.trim() : null);
    try {
      await api("/public/setup/completar", {
        method: "POST",
        app: "public",
        body: {
          token: requiereToken ? token.trim() : null,
          admin: { nombre: admin.nombre.trim(), email: admin.email.trim(), password: admin.password },
          sucursal: {
            nombre: suc.nombre.trim(),
            direccion: vacio(suc.direccion),
            telefono: vacio(suc.telefono),
            rif: vacio(suc.rif),
            razon_social: vacio(suc.razon_social),
            domicilio_fiscal: vacio(suc.domicilio_fiscal),
          },
          moneda: { codigo: moneda.codigo.trim(), nombre: moneda.nombre.trim(), simbolo: moneda.simbolo.trim() },
          zona_horaria: zona,
        },
      });
      // Todo listo: entra directo con el administrador recién creado
      const res = await fetch("/bff/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json", "x-restify": "1" },
        body: JSON.stringify({ email: admin.email.trim(), password: admin.password }),
      });
      const me = MeOut.safeParse(await res.json().catch(() => null));
      if (res.ok && me.success) {
        qc.setQueryData(meKey, me.data);
        router.replace("/panel");
      } else {
        router.replace("/login");
      }
    } catch (err) {
      setError(describeError(err));
      setPending(false);
    }
  }

  const titulos: Record<StepId, [string, string]> = {
    token: ["Ingresa tu token", "Te lo entregó RESTIFY al contratar. Identifica tu cuenta y tu plan."],
    admin: ["Tu cuenta de administrador", "Con ella manejarás todo el sistema."],
    sucursal: ["Tu primer local", "Podrás agregar más sucursales después, según tu plan."],
    moneda: ["Moneda y zona horaria", "La moneda principal es en la que defines los precios."],
    revisar: ["Revisa y termina", "Así quedará tu sistema."],
  };

  return (
    <>
      <div className="flex flex-col gap-3">
        <span className="eyebrow">
          Paso {i + 1} de {pasos.length}
        </span>
        <div className="flex gap-1.5" aria-hidden>
          {pasos.map((p, n) => (
            <span key={p} className={`h-0.5 flex-1 transition-colors ${n <= i ? "bg-paper" : "bg-line-strong"}`} />
          ))}
        </div>
        <h1 className="font-display text-display-l">{titulos[paso][0]}</h1>
        <p className="text-base text-fg-2">{titulos[paso][1]}</p>
      </div>

      <form onSubmit={siguiente} className="flex flex-col gap-8" noValidate>
        {paso === "token" && (
          <>
            <Field label="Token" name="token" value={token} onChange={(e) => setToken(e.target.value)} error={errores.token} autoComplete="off" spellCheck={false} autoFocus placeholder="rst_…" />
          </>
        )}

        {paso === "admin" && (
          <>
            {plan && (
              <p className="border-l-2 border-ok pl-4 text-base text-fg-2">
                Token válido{plan.plan ? <> · plan <strong className="text-fg">{plan.plan}</strong></> : null}
                {Object.entries(plan.limites).some(([, v]) => v !== null) && (
                  <span className="block text-sm text-fg-3">
                    Incluye hasta{" "}
                    {Object.entries(plan.limites)
                      .filter(([, v]) => v !== null)
                      .map(([k, v]) => `${v} ${ETIQUETA_LIMITE[k] ?? k}`)
                      .join(", ")}
                    .
                  </span>
                )}
              </p>
            )}
            <Field label="Tu nombre" value={admin.nombre} onChange={(e) => setAdmin({ ...admin, nombre: e.target.value })} error={errores.nombre} autoComplete="name" autoFocus />
            <Field label="Correo" type="email" value={admin.email} onChange={(e) => setAdmin({ ...admin, email: e.target.value })} error={errores.email} autoComplete="username" />
            <Field label="Contraseña" type="password" value={admin.password} onChange={(e) => setAdmin({ ...admin, password: e.target.value })} error={errores.password} hint="Mínimo 10 caracteres con mayúsculas, minúsculas y números." autoComplete="new-password" />
            <Field label="Repite la contraseña" type="password" value={admin.repetir} onChange={(e) => setAdmin({ ...admin, repetir: e.target.value })} error={errores.repetir} autoComplete="new-password" />
          </>
        )}

        {paso === "sucursal" && (
          <>
            <Field label="Nombre del local" value={suc.nombre} onChange={(e) => setSuc({ ...suc, nombre: e.target.value })} error={errores.nombre} placeholder="Ej. Centro" autoFocus />
            <Field label="Dirección (opcional)" value={suc.direccion} onChange={(e) => setSuc({ ...suc, direccion: e.target.value })} />
            <Field label="Teléfono (opcional)" type="tel" value={suc.telefono} onChange={(e) => setSuc({ ...suc, telefono: e.target.value })} />
            <p className="eyebrow pt-2">Datos fiscales · opcional, para facturar</p>
            <Field label="RIF" value={suc.rif} onChange={(e) => setSuc({ ...suc, rif: e.target.value.toUpperCase() })} placeholder="J-12345678-9" />
            <Field label="Razón social" value={suc.razon_social} onChange={(e) => setSuc({ ...suc, razon_social: e.target.value })} />
            <Field label="Domicilio fiscal" value={suc.domicilio_fiscal} onChange={(e) => setSuc({ ...suc, domicilio_fiscal: e.target.value })} />
          </>
        )}

        {paso === "moneda" && (
          <>
            <Select
              label="Moneda principal"
              value={MONEDAS.find((m) => m.codigo === moneda.codigo)?.codigo ?? "otra"}
              onChange={(e) => setMoneda(MONEDAS.find((m) => m.codigo === e.target.value) ?? { codigo: "", nombre: "", simbolo: "" })}
            >
              {MONEDAS.map((m) => (
                <option key={m.codigo} value={m.codigo}>
                  {m.nombre} ({m.codigo})
                </option>
              ))}
              <option value="otra">Otra…</option>
            </Select>
            {!MONEDAS.some((m) => m.codigo === moneda.codigo) && (
              <>
                <Field label="Código" value={moneda.codigo} onChange={(e) => setMoneda({ ...moneda, codigo: e.target.value.toUpperCase() })} error={errores.codigo} placeholder="USD" />
                <Field label="Nombre" value={moneda.nombre} onChange={(e) => setMoneda({ ...moneda, nombre: e.target.value })} error={errores.nombre} />
                <Field label="Símbolo" value={moneda.simbolo} onChange={(e) => setMoneda({ ...moneda, simbolo: e.target.value })} error={errores.simbolo} />
              </>
            )}
            <Select label="Zona horaria" value={zona} onChange={(e) => setZona(e.target.value)} hint="Define qué es «hoy» en tus ventas.">
              {ZONAS.map(([v, n]) => (
                <option key={v} value={v}>
                  {n} ({v.split("/").at(-1)?.replace("_", " ")})
                </option>
              ))}
            </Select>
            <p className="text-sm text-fg-3">Otras monedas y sus tasas las agregas después, desde Administración.</p>
          </>
        )}

        {paso === "revisar" && (
          <dl className="flex flex-col gap-4 text-base">
            {([
              ["Administrador", `${admin.nombre} · ${admin.email}`],
              ["Primer local", [suc.nombre, suc.direccion].filter(Boolean).join(" · ")],
              ["Datos fiscales", [suc.rif, suc.razon_social].filter(Boolean).join(" · ") || "—"],
              ["Moneda principal", `${moneda.nombre} (${moneda.codigo}, ${moneda.simbolo})`],
              ["Zona horaria", zona],
              ...(plan?.plan ? [["Plan", plan.plan] as [string, string]] : []),
            ] as [string, string][]).map(([k, v]) => (
              <div key={k} className="flex flex-col gap-0.5 border-b border-line pb-3">
                <dt className="eyebrow">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        )}

        <AnimatePresence initial={false}>
          {error && (
            <motion.div role="alert" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} transition={smooth} className="overflow-hidden">
              <div className="flex gap-3 border-l-2 border-err pl-4">
                <div className="flex flex-col gap-0.5">
                  <p className="text-base font-medium">{error.title}</p>
                  {error.description && <p className="text-sm text-fg-2">{error.description}</p>}
                  {error.items?.map((it) => (
                    <p key={it} className="text-sm text-fg-2">
                      {it}
                    </p>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex gap-3">
          {i > 0 && (
            <Button type="button" variant="line" size="lg" onClick={volver} disabled={pending}>
              Atrás
            </Button>
          )}
          <Button type="submit" size="lg" loading={pending} className="flex-1">
            {paso === "revisar" ? "Terminar y entrar" : "Continuar"}
          </Button>
        </div>
      </form>
    </>
  );
}
