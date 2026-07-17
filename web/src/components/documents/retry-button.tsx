"use client";

/** RetryButton — re-drive a failed document through the pipeline. The server
 *  resets it to `received`, so the row/card flips straight back to the live
 *  pipeline (and the never-wait polling picks it up). */

import { RotateCcw } from "lucide-react";
import clsx from "clsx";

import { useReprocess } from "@/features/documents/queries";

export function RetryButton({
  documentId,
  label = "Retry",
  className,
}: {
  documentId: string;
  label?: string;
  className?: string;
}) {
  const reprocess = useReprocess();
  return (
    <button
      type="button"
      disabled={reprocess.isPending}
      onClick={(e) => {
        // Rows/cards are links — retrying must not navigate.
        e.preventDefault();
        e.stopPropagation();
        reprocess.mutate(documentId);
      }}
      className={clsx(
        "inline-flex min-h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 type-caption font-medium text-text-1 transition-colors hover:border-accent-300 hover:bg-accent-50 disabled:opacity-50",
        className,
      )}
    >
      <RotateCcw aria-hidden className="size-3.5" />
      {reprocess.isPending ? "Retrying…" : label}
    </button>
  );
}
