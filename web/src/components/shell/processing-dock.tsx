"use client";

/**
 * ProcessingDock — the never-wait anchor: a persistent glass pill (bottom-right,
 * every screen) that shows how many documents are in flight, so the user can
 * navigate freely while things process. Expands to a per-document list with live
 * Pipeline fill. Reads the shared documents feed + optimistic uploads; renders
 * nothing when idle.
 */

import { useState } from "react";
import { ChevronUp, Loader2, X } from "lucide-react";
import clsx from "clsx";

import { PipelineFill } from "@/components/upload/pipeline-fill";
import { useDocumentsFeed } from "@/features/upload/queries";
import { useUpload } from "@/features/upload/upload-context";
import { isProcessing } from "@/features/archive/taxonomy";

export function ProcessingDock() {
  const { data: docs } = useDocumentsFeed();
  const { pending } = useUpload();
  const [open, setOpen] = useState(false);

  const processing = (docs ?? []).filter((d) => isProcessing(d.status));
  const uploading = pending.filter((p) => p.state === "uploading");
  const count = processing.length + uploading.length;

  if (count === 0) return null;

  return (
    // bottom-20 on mobile clears the tab bar; lg gets the plain corner.
    <div className="fixed bottom-20 right-4 z-40 w-[min(20rem,calc(100vw-2rem))] lg:bottom-4">
      {open ? (
        <div className="mb-2 overflow-hidden rounded-xl border border-border bg-surface/85 shadow-e3 backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="type-subhead text-text-1">Processing</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Collapse"
              className="flex size-7 items-center justify-center rounded-md text-text-3 hover:bg-surface-2 hover:text-text-1"
            >
              <X aria-hidden className="size-4" />
            </button>
          </div>
          <ul className="max-h-72 divide-y divide-border overflow-y-auto">
            {uploading.map((p) => (
              <li key={p.id} className="flex flex-col gap-1 px-3 py-2.5">
                <span className="truncate type-callout text-text-1" title={p.name}>
                  {p.name}
                </span>
                <span className="flex items-center gap-1.5 type-caption text-text-3">
                  <Loader2 aria-hidden className="size-3 motion-safe:animate-spin" />
                  Uploading…
                </span>
              </li>
            ))}
            {processing.map((d) => (
              <li key={d.id} className="flex flex-col gap-1.5 px-3 py-2.5">
                <span className="truncate type-callout text-text-1" title={d.title ?? d.original_filename}>
                  {d.title?.trim() || d.original_filename}
                </span>
                <PipelineFill status={d.status} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-full border border-border bg-surface/85 px-4 py-2.5 shadow-e2 backdrop-blur-md transition-colors hover:bg-surface"
      >
        <Loader2 aria-hidden className="size-4 text-accent motion-safe:animate-spin" />
        <span className="type-subhead text-text-1">
          {count} processing
        </span>
        <ChevronUp
          aria-hidden
          className={clsx(
            "ml-auto size-4 text-text-3 transition-transform duration-[var(--dur-base)]",
            open && "rotate-180",
          )}
        />
      </button>
    </div>
  );
}
