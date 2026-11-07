"use client";

import { Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import type { Mensaje } from "@/lib/api/schemas";

/** Conversación entre la mesa y caja. `yo` dice de qué lado se escribe desde esta pantalla. */
export function ChatPanel({
  mensajes,
  yo,
  onEnviar,
  enviando,
  vacio,
}: {
  mensajes: Mensaje[];
  yo: Mensaje["autor"];
  onEnviar: (texto: string) => void;
  enviando?: boolean;
  vacio: string;
}) {
  const [texto, setTexto] = useState("");
  const fin = useRef<HTMLDivElement>(null);
  useEffect(() => {
    fin.current?.scrollIntoView({ block: "end" });
  }, [mensajes.length]);

  function enviar() {
    const t = texto.trim();
    if (!t) return;
    onEnviar(t);
    setTexto("");
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex max-h-72 flex-col gap-2 overflow-y-auto" aria-live="polite">
        {mensajes.length === 0 && <li className="text-sm text-fg-3">{vacio}</li>}
        {mensajes.map((m) => (
          <li key={m.id} className={cn("flex max-w-[85%] flex-col gap-0.5 rounded-sheet px-3 py-2", m.autor === yo ? "self-end bg-wash" : "self-start bg-sunken")}>
            {m.autor !== yo && m.autor_nombre && <span className="text-xs text-fg-3">{m.autor_nombre}</span>}
            <span className="whitespace-pre-wrap break-words text-base">{m.texto}</span>
          </li>
        ))}
        <div ref={fin} />
      </ul>
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          enviar();
        }}
      >
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          maxLength={500}
          placeholder="Escribe un mensaje…"
          aria-label="Mensaje"
          className="h-11 min-w-0 flex-1 border-b border-line-strong bg-transparent text-base outline-none placeholder:text-fg-4 focus:border-paper"
        />
        <Button type="submit" size="sm" disabled={enviando || !texto.trim()} aria-label="Enviar mensaje">
          <Send size={16} strokeWidth={1.5} aria-hidden />
        </Button>
      </form>
    </div>
  );
}
