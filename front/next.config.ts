import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // La cámara se permite en el propio sitio: la usa el escáner de Reponer (QR y códigos de barras)
  { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=(), payment=()" },
];

const config: NextConfig = {
  // Permite compilar en otra carpeta sin pisar la de un `next dev` que esté corriendo
  distDir: process.env.NEXT_DIST_DIR || ".next",
  output: "standalone",
  poweredByHeader: false,
  // Solo desarrollo: permite abrir el dev server desde otros dispositivos de la red
  // (p. ej. DEV_ALLOWED_ORIGINS=192.168.1.20 para probar en el teléfono)
  allowedDevOrigins: process.env.DEV_ALLOWED_ORIGINS?.split(",").map((s) => s.trim()).filter(Boolean),
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async redirects() {
    return [{ source: "/", destination: "/panel", permanent: false }];
  },
};

export default config;
