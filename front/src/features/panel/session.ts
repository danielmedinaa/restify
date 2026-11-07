"use client";

/** Cierra la sesión en el BFF (revoca el refresh en el backend y borra la cookie). */
export async function logout(): Promise<void> {
  await fetch("/bff/auth/logout", { method: "POST", headers: { "x-restify": "1" } }).catch(() => null);
}
