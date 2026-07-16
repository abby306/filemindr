/**
 * StatusBadge — colored dot + label for a document's pipeline status. Color is
 * never the sole signal (the label carries it). Labels come from STATUS_META.
 */

import clsx from "clsx";

import { STATUS_META, type StatusTone } from "@/features/archive/taxonomy";
import type { DocumentStatus } from "@/lib/api/types";

const DOT: Record<StatusTone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
  idle: "bg-idle",
  accent: "bg-accent",
};

const TEXT: Record<StatusTone, string> = {
  ok: "text-ok",
  warn: "text-warn-text",
  danger: "text-danger",
  idle: "text-text-3",
  accent: "text-accent-text",
};

export function StatusBadge({
  status,
  animate,
}: {
  status: DocumentStatus;
  /** Pulse the dot for in-flight statuses (Pipeline-fill cue). */
  animate?: boolean;
}) {
  const meta = STATUS_META[status];
  return (
    <span className={clsx("inline-flex items-center gap-1.5 type-caption", TEXT[meta.tone])}>
      <span
        aria-hidden
        className={clsx(
          "size-1.5 rounded-full",
          DOT[meta.tone],
          animate && "motion-safe:animate-pulse",
        )}
      />
      {meta.label}
    </span>
  );
}
