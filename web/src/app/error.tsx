"use client";

/** Route error boundary — a calm, recoverable error state (direction, not mood). */

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-full flex-col items-center justify-center px-6 py-16 text-center">
      <span className="flex size-12 items-center justify-center rounded-lg bg-surface-2 text-danger">
        <AlertTriangle aria-hidden className="size-6" strokeWidth={1.5} />
      </span>
      <h1 className="mt-4 type-title2 text-text-1">Something went wrong</h1>
      <p className="mt-1 max-w-sm type-callout text-text-2">
        This screen hit an unexpected error. You can try again — nothing was lost.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-5 min-h-11 rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
      >
        Try again
      </button>
    </div>
  );
}
