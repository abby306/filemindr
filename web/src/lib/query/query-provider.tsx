"use client";

/**
 * TanStack Query provider. One QueryClient per browser session; conservative
 * defaults suited to the never-wait model (short stale time, retry-once). The
 * ~1s polling for in-flight document processing is set per-query at call sites,
 * not globally.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}
