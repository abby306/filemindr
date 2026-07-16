"use client";

/**
 * Connection indicator — pings `GET /api/v1/me` through the account-bound
 * request seam. Doubles as the shell's proof that auth + scoping headers reach
 * the FastAPI API and that the dev rewrite / CORS path works. Re-queries when
 * the active account changes.
 */

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";

import { useAccount } from "@/lib/account/account-context";

interface MeResponse {
  user?: { email?: string };
  account?: { name?: string };
}

export function BackendStatus() {
  const { account, request } = useAccount();

  const { status } = useQuery({
    queryKey: ["me", account.id],
    queryFn: () => request<MeResponse>("/api/v1/me"),
    retry: 0,
    staleTime: 60_000,
  });

  const label =
    status === "pending" ? "Connecting…" : status === "error" ? "Offline" : "Connected";
  const tone =
    status === "pending"
      ? "bg-idle"
      : status === "error"
        ? "bg-danger"
        : "bg-ok";

  return (
    <span
      className="flex items-center gap-2 type-caption text-on-ink-muted"
      role="status"
      aria-live="polite"
      title={`API ${label}`}
    >
      <span aria-hidden className={clsx("size-2 rounded-full", tone)} />
      {label}
    </span>
  );
}
