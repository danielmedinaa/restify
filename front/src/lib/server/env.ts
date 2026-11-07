import "server-only";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Falta la variable de entorno ${name}`);
  return value;
}

/** Variables del servidor. Nunca se importan desde código de cliente. */
export const env = {
  apiUrl: (process.env.API_URL ?? "http://localhost:8010").replace(/\/$/, ""),
  get panelKey() {
    return required("PANEL_API_KEY");
  },
  get publicKey() {
    return required("PUBLIC_API_KEY");
  },
  get kitchenKey() {
    return process.env.KITCHEN_API_KEY || required("PANEL_API_KEY");
  },
  get sessionSecret() {
    const s = required("SESSION_SECRET");
    if (s.length < 32) throw new Error("SESSION_SECRET debe tener al menos 32 caracteres");
    return s;
  },
  /** false solo para probar desde otro dispositivo por http en la red local. */
  cookieSecure: process.env.COOKIE_SECURE !== "false",
};
