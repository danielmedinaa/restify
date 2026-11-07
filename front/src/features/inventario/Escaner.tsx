"use client";

import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { fade } from "@/lib/motion";

/** API nativa de Chrome/Android/Edge. iPhone no la tiene: ahí se usa @zxing/browser. */
interface DetectorNativo {
  detect(fuente: HTMLVideoElement): Promise<{ rawValue: string }[]>;
}
declare global {
  interface Window {
    BarcodeDetector?: { new (opts?: { formats?: string[] }): DetectorNativo; getSupportedFormats?: () => Promise<string[]> };
  }
}

const FORMATOS = ["qr_code", "ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "itf"];

/**
 * Cámara a pantalla completa que lee QR y códigos de barras. Entrega el primer
 * código que reconoce y se cierra sola. Necesita HTTPS (o localhost) para usar la cámara.
 */
export function Escaner({ abierto, onLeido, onCerrar }: { abierto: boolean; onLeido: (texto: string) => void; onCerrar: () => void }) {
  return <AnimatePresence>{abierto && <Camara key="camara" onLeido={onLeido} onCerrar={onCerrar} />}</AnimatePresence>;
}

function Camara({ onLeido, onCerrar }: { onLeido: (texto: string) => void; onCerrar: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(() =>
    typeof window !== "undefined" && !window.isSecureContext
      ? "La cámara solo funciona con HTTPS. Escribe el código o usa un lector de códigos de barras."
      : null,
  );

  useEffect(() => {
    if (!window.isSecureContext) return;
    let activo = true;
    let stream: MediaStream | null = null;
    let detener: (() => void) | null = null;
    const leido = (texto: string) => {
      if (!activo || !texto) return;
      activo = false;
      navigator.vibrate?.(40);
      onLeido(texto.trim());
    };

    (async () => {
      try {
        if (window.BarcodeDetector) {
          stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
          const v = video.current;
          if (!v || !activo) return;
          v.srcObject = stream;
          await v.play();
          const soportados = (await window.BarcodeDetector.getSupportedFormats?.()) ?? FORMATOS;
          const detector = new window.BarcodeDetector({ formats: FORMATOS.filter((f) => soportados.includes(f)) });
          const ciclo = async () => {
            if (!activo) return;
            try {
              const [codigo] = await detector.detect(v);
              if (codigo) return leido(codigo.rawValue);
            } catch {
              // fotograma no listo: se reintenta
            }
            setTimeout(ciclo, 180);
          };
          void ciclo();
        } else {
          const { BrowserMultiFormatReader } = await import("@zxing/browser");
          const lector = new BrowserMultiFormatReader();
          if (!video.current || !activo) return;
          const controles = await lector.decodeFromConstraints({ video: { facingMode: "environment" } }, video.current, (r) => {
            if (r) leido(r.getText());
          });
          detener = () => controles.stop();
          if (!activo) detener();
        }
      } catch (e) {
        const nombre = e instanceof DOMException ? e.name : "";
        setError(
          nombre === "NotAllowedError"
            ? "Permite el acceso a la cámara en tu navegador para escanear."
            : nombre === "NotFoundError"
              ? "No encontramos una cámara en este dispositivo."
              : "No se pudo abrir la cámara. Escribe el código a mano.",
        );
      }
    })();

    return () => {
      activo = false;
      detener?.();
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [onLeido]);

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label="Escanear código"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={fade}
      className="fixed inset-0 z-[60] flex flex-col bg-ink"
    >
      <video ref={video} playsInline muted className="absolute inset-0 h-full w-full object-cover" />
      {/* Marco de enfoque: oscurece todo menos el centro */}
      <div aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center">
        <div className="relative aspect-square w-[min(72vw,320px)] rounded-sheet shadow-[0_0_0_100vmax_rgb(10_9_9/0.62)]">
          <span className="absolute inset-0 rounded-sheet ring-2 ring-paper/80" />
          <motion.span
            className="absolute inset-x-6 h-px bg-paper"
            initial={{ top: "15%" }}
            animate={{ top: ["15%", "85%", "15%"] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
          />
        </div>
      </div>
      <div className="relative flex items-center justify-between p-4 pt-[max(1rem,env(safe-area-inset-top))]">
        <p className="text-lead font-medium">Apunta al código</p>
        <button type="button" onClick={onCerrar} aria-label="Cerrar cámara" className="grid size-11 place-items-center rounded-full bg-canvas/60 backdrop-blur-md">
          <X size={20} strokeWidth={1.5} />
        </button>
      </div>
      <p className="relative mt-auto px-6 pb-[max(2rem,env(safe-area-inset-bottom))] text-center text-base text-fg-2">
        {error ?? "QR de la etiqueta, código de barras del empaque o código interno."}
      </p>
    </motion.div>
  );
}
