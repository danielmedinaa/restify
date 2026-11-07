"use client";

import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { meKey } from "@/features/auth/useMe";
import { ApiError, describeError, type ErrorView } from "@/lib/api/errors";
import { MeOut } from "@/lib/api/schemas";
import { smooth } from "@/lib/motion";
import { useQueryClient } from "@tanstack/react-query";

export function LoginForm({ next, notice }: { next: string; notice?: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<ErrorView | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/bff/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json", "x-restify": "1" },
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      const data: unknown = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = (data as { detail?: unknown } | null)?.detail;
        const err = new ApiError(res.status, detail ?? null, Number(res.headers.get("retry-after")) || null);
        // El backend no dice si el correo existe: el mensaje tampoco
        setError(res.status === 401 ? { title: "Correo o contraseña incorrectos", tone: "err" } : describeError(err));
        return;
      }
      const me = MeOut.safeParse(data);
      if (me.success) qc.setQueryData(meKey, me.data);
      router.replace(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-8" noValidate>
      {notice && !error && <p className="text-base text-fg-2">{notice}</p>}
      <Field label="Correo" name="email" type="email" autoComplete="username" required autoFocus />
      <Field label="Contraseña" name="password" type="password" autoComplete="current-password" required />
      <AnimatePresence initial={false}>
        {error && (
          <motion.div
            role="alert"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={smooth}
            className="overflow-hidden"
          >
            <div className="flex gap-3 border-l-2 border-err pl-4">
              <div className="flex flex-col gap-0.5">
                <p className="text-base font-medium">{error.title}</p>
                {error.description && <p className="text-sm text-fg-2">{error.description}</p>}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <Button type="submit" size="lg" loading={pending} className="w-full">
        Entrar
      </Button>
    </form>
  );
}
