"use client";

/**
 * UploadingCard — the optimistic card for a file mid-POST (spinner) or one that
 * failed validation/upload (error, with retry + dismiss). Matches the manila
 * DocumentCard shape so the transition to a real card is seamless.
 */

import { AlertCircle, Loader2 } from "lucide-react";

import { formatBytes } from "@/lib/format";
import type { PendingUpload } from "@/features/upload/upload-context";

export function UploadingCard({
  entry,
  onRetry,
  onDismiss,
}: {
  entry: PendingUpload;
  onRetry: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  const isError = entry.state === "error";
  const size = formatBytes(entry.size);

  return (
    <div
      className={
        "animate-materialize flex flex-col overflow-hidden rounded-lg border bg-card shadow-e1 " +
        (isError ? "border-danger/40" : "border-border")
      }
    >
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="type-record truncate text-text-1" title={entry.name}>
          {entry.name}
        </h3>

        {isError ? (
          <>
            <p className="flex items-start gap-1.5 type-callout text-danger">
              <AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0" />
              {entry.error}
            </p>
            <div className="mt-auto flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => onRetry(entry.id)}
                className="min-h-9 rounded-md bg-accent px-3 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={() => onDismiss(entry.id)}
                className="min-h-9 rounded-md px-3 type-subhead text-text-2 transition-colors hover:bg-surface-2 hover:text-text-1"
              >
                Dismiss
              </button>
            </div>
          </>
        ) : (
          <div className="mt-auto flex flex-col gap-1.5 pt-1">
            <span aria-hidden className="relative h-1 w-full max-w-40 overflow-hidden rounded-full bg-surface-2">
              <span className="animate-seg-shimmer absolute inset-0 rounded-full" />
            </span>
            <span className="flex items-center gap-2 type-caption text-text-3">
              <Loader2 aria-hidden className="size-3.5 motion-safe:animate-spin" />
              Uploading{size ? ` · ${size}` : ""}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
