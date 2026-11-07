import "server-only";

import { EncryptJWT, jwtDecrypt } from "jose";
import { cookies } from "next/headers";
import { env } from "./env";

/**
 * Sesión del personal: el access y el refresh token viven en UNA cookie httpOnly,
 * cifrada (JWE, A256GCM). El navegador la guarda pero no puede leerla ni usarla
 * contra la API: solo el BFF la descifra.
 */
export const SESSION_COOKIE = "rs_session";

export interface Session {
  access: string;
  refresh: string;
  /** epoch ms en que vence el access token */
  accessExp: number;
}

const REFRESH_DAYS = 7;
let keyPromise: Promise<Uint8Array> | null = null;

function key() {
  keyPromise ??= crypto.subtle
    .digest("SHA-256", new TextEncoder().encode(env.sessionSecret))
    .then((buf) => new Uint8Array(buf));
  return keyPromise;
}

export async function sealSession(s: Session): Promise<string> {
  return new EncryptJWT({ a: s.access, r: s.refresh, e: s.accessExp })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime(`${REFRESH_DAYS}d`)
    .encrypt(await key());
}

export async function openSession(token: string | undefined): Promise<Session | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtDecrypt(token, await key());
    const { a, r, e } = payload;
    if (typeof a !== "string" || typeof r !== "string" || typeof e !== "number") return null;
    return { access: a, refresh: r, accessExp: e };
  } catch {
    return null;
  }
}

export async function readSession(): Promise<Session | null> {
  return openSession((await cookies()).get(SESSION_COOKIE)?.value);
}

export async function writeSession(s: Session): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, await sealSession(s), {
    httpOnly: true,
    secure: env.cookieSecure,
    sameSite: "strict",
    path: "/",
    maxAge: REFRESH_DAYS * 24 * 3600,
  });
}

export async function clearSession(): Promise<void> {
  (await cookies()).delete({ name: SESSION_COOKIE, path: "/" });
}
