"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState } from "react";
import { Toaster } from "@/components/ui/Toast";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      {/* "user": respeta prefers-reduced-motion en todas las animaciones de Motion */}
      <MotionConfig reducedMotion="user">
        {children}
        <Toaster />
      </MotionConfig>
    </QueryClientProvider>
  );
}
