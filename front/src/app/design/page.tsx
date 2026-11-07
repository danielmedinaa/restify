import type { Metadata } from "next";
import { Showcase } from "./Showcase";

export const metadata: Metadata = { title: "Sistema de diseño" };

export default function DesignPage() {
  return <Showcase />;
}
