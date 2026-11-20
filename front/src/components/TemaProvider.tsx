"use client";

import { createContext, useContext } from "react";
import { TEMA_VACIO, type Tema } from "@/lib/api/schemas";

const TemaContext = createContext<Tema>(TEMA_VACIO);

/** El tema de la marca del restaurante, ya resuelto en el servidor (sin parpadeos). */
export function TemaProvider({ tema, children }: { tema: Tema; children: React.ReactNode }) {
  return <TemaContext.Provider value={tema}>{children}</TemaContext.Provider>;
}

export const useTema = () => useContext(TemaContext);
