"use client";

/** Client-side provider stack mounted once in the root layout. */

import { AccountProvider } from "@/lib/account/account-context";
import { QueryProvider } from "@/lib/query/query-provider";
import { UploadProvider } from "@/features/upload/upload-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryProvider>
      <AccountProvider>
        <UploadProvider>{children}</UploadProvider>
      </AccountProvider>
    </QueryProvider>
  );
}
