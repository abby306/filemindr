"use client";

/**
 * Sheet — the mobile bottom sheet: scrim + a rounded panel that slides up
 * (240ms, --dur-sheet) and respects the home-indicator safe area. Dismiss via
 * the scrim, the close button, or Escape; body scroll locks while open. The
 * close button takes focus on open so keyboard/screen-reader users land inside
 * the dialog.
 */

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import clsx from "clsx";

import { usePresence } from "@/lib/use-presence";

export function Sheet({
  open,
  onClose,
  title,
  children,
  tall,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  /** Fixed 85dvh panel (e.g. the document source); default hugs its content. */
  tall?: boolean;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const { mounted, state } = usePresence(open, 180);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!mounted) return null;
  const closing = state === "closing";

  return (
    <div className="fixed inset-0 z-50">
      <div
        onClick={onClose}
        aria-hidden
        className={clsx(
          "absolute inset-0 bg-p-950/40",
          closing ? "animate-fade-out" : "animate-fade-in",
        )}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={clsx(
          "absolute inset-x-0 bottom-0 flex flex-col rounded-t-xl border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] shadow-e3",
          closing ? "animate-sheet-down" : "animate-sheet-up",
          tall ? "h-[85dvh]" : "max-h-[70dvh]",
        )}
      >
        <span aria-hidden className="mx-auto mt-2 h-1 w-8 rounded-full bg-border-strong" />
        <div className="flex items-center justify-between py-1 pl-4 pr-2">
          <span className="type-title3 text-text-1">{title}</span>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={`Close ${title}`}
            className="pressable flex size-11 items-center justify-center rounded-md text-text-3 transition-colors hover:bg-surface-2 hover:text-text-1"
          >
            <X aria-hidden className="size-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">{children}</div>
      </div>
    </div>
  );
}
