"use client";

/**
 * Toast — a single ephemeral confirmation with an optional action (e.g. Undo).
 * Announced politely, never steals focus, auto-dismisses. Controlled by the
 * parent so there's one at a time.
 */

import { useEffect } from "react";

export function Toast({
  open,
  message,
  actionLabel,
  onAction,
  onDismiss,
  duration = 5000,
}: {
  open: boolean;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  onDismiss: () => void;
  duration?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(onDismiss, duration);
    return () => window.clearTimeout(t);
  }, [open, duration, onDismiss]);

  if (!open) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-full border border-border-strong bg-p-900 px-4 py-2.5 text-p-0 shadow-e3"
    >
      <span className="type-subhead">{message}</span>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="type-subhead text-accent-300 underline-offset-2 hover:underline"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
