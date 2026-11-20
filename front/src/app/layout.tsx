import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { BannerEntorno } from "@/components/layout/banner-entorno";
import { TemaProvider } from "@/components/TemaProvider";
import { obtenerTema } from "@/lib/server/tema";
import { temaCss } from "@/lib/tema";

export const metadata: Metadata = {
  title: { default: "Restify", template: "%s · Restify" },
  description: "Gestión de cocina y restaurante",
};

export const viewport: Viewport = {
  themeColor: "#1a1819",
  colorScheme: "dark",
  viewportFit: "cover",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const tema = await obtenerTema();
  const css = temaCss(tema);
  return (
    <html lang="es">
      <head>
        <link rel="preload" href="/fonts/GeneralSans-Variable.woff2" as="font" type="font/woff2" crossOrigin="" />
        {css && <style id="tema-marca" dangerouslySetInnerHTML={{ __html: css }} />}

      </head>
      <body>
        <TemaProvider tema={tema}>
          <Providers>{children}</Providers>
        </TemaProvider>
        <BannerEntorno />
        {/* Grano global, muy sutil, por encima de todo y sin capturar eventos */}
        <div aria-hidden className="pointer-events-none fixed inset-0 z-[70] opacity-[0.035] mix-blend-overlay [background-image:var(--grain)]" />
      </body>
    </html>
  );
}
