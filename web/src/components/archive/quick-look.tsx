"use client";

/**
 * QuickLook — peek a document without leaving the directory (Space, or the
 * per-row eye button). A centered modal: first page + card, an "Open document"
 * link to the full view, dismiss via Escape / scrim / close. Enter and exit
 * animate via usePresence; the last doc is held through the exit so the content
 * doesn't blank mid-animation.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, X } from "lucide-react";
import clsx from "clsx";

import { DocumentPreview } from "@/components/archive/document-preview";
import { usePresence } from "@/lib/use-presence";
import type { DocumentSummary } from "@/lib/api/types";

export function QuickLook({
  doc,
  onClose,
}: {
  doc: DocumentSummary | null;
  onClose: () => void;
}) {
  const { mounted, state } = usePresence(doc != null, 160);

  // Hold the last doc through the exit animation (doc goes null on close).
  const [shown, setShown] = useState<DocumentSummary | null>(doc);
  if (doc && doc !== shown) setShown(doc);

  useEffect(() => {
    if (!doc) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [doc, onClose]);

  if (!mounted || !shown) return null;
  const closing = state === "closing";
  const title = shown.title?.trim() || shown.original_filename;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        aria-hidden
        onClick={onClose}
        className={clsx(
          "absolute inset-0 bg-p-950/50",
          closing ? "animate-fade-out" : "animate-fade-in",
        )}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Quick look: ${title}`}
        className={clsx(
          "relative flex max-h-[86dvh] w-full max-w-md flex-col overflow-hidden rounded-xl border border-border-strong bg-surface shadow-e3",
          closing ? "animate-pop-out" : "animate-pop-in",
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <span className="truncate type-subhead text-text-1">Quick look</span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close quick look"
            className="pressable flex size-8 items-center justify-center rounded-md text-text-3 transition-colors hover:bg-surface-2 hover:text-text-1"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <DocumentPreview doc={shown} size="look" />
        </div>

        <div className="border-t border-border p-3">
          <Link
            href={`/documents/${shown.id}`}
            className="pressable flex min-h-10 items-center justify-center gap-2 rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
          >
            <ExternalLink aria-hidden className="size-4" />
            Open document
          </Link>
        </div>
      </div>
    </div>
  );
}
