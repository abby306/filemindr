/**
 * PipelineFill — the processing choreography. Four segments fill as the
 * backend reports each real stage (received → ocr_done → extracted → indexed):
 * completed segments fill solid (with a one-shot thickness pop), the active
 * segment shimmers until its stage resolves, and reaching "Filed" earns a
 * drawn checkmark. Terminal problem states (needs review / failed) keep the
 * track and switch the label tone. Every animation fires once, on a real
 * state change; reduced-motion collapses to opacity.
 */

import clsx from "clsx";

import { STATUS_META } from "@/features/archive/taxonomy";
import type { DocumentStatus } from "@/lib/api/types";

const STAGES: DocumentStatus[] = ["received", "ocr_done", "extracted", "indexed"];

function Segment({ state }: { state: "done" | "active" | "todo" }) {
  return (
    <span className="relative h-1 flex-1 overflow-hidden rounded-full bg-surface-2">
      {state === "done" ? (
        <span className="animate-seg-pop absolute inset-0 rounded-full bg-accent" />
      ) : null}
      {state === "active" ? (
        <>
          <span className="absolute inset-0 rounded-full bg-accent opacity-30" />
          <span className="animate-seg-shimmer absolute inset-0 rounded-full" />
        </>
      ) : null}
    </span>
  );
}

export function FiledCheck({ label = "Filed" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 type-caption font-medium text-ok">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden className="size-3.5">
        <path
          d="M4 12.5l5 5L20 6.5"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="animate-draw-check"
        />
      </svg>
      {label}
    </span>
  );
}

export function PipelineFill({
  status,
  showTrack = true,
}: {
  status: DocumentStatus;
  /** Hide the segment track for ultra-compact rows (label only). */
  showTrack?: boolean;
}) {
  const idx = STAGES.indexOf(status);
  const meta = STATUS_META[status];
  const filed = status === "indexed";
  const trouble = status === "failed" || status === "needs_review";

  return (
    <span
      className={clsx("flex min-w-0 items-center gap-2.5", showTrack && "w-full")}
      title={filed || trouble ? meta.label : `${meta.label}…`}
    >
      {showTrack ? (
        <span aria-hidden className="flex min-w-16 max-w-40 flex-1 items-center gap-1">
          {STAGES.map((stage, i) => (
            <Segment
              key={stage}
              state={
                filed || i < idx ? "done" : i === idx && !trouble ? "active" : "todo"
              }
            />
          ))}
        </span>
      ) : null}
      {filed ? (
        <FiledCheck />
      ) : (
        <span
          className={clsx(
            "shrink-0 type-caption font-medium",
            status === "failed"
              ? "text-danger"
              : status === "needs_review"
                ? "text-warn"
                : "text-accent-text",
          )}
        >
          {meta.label}
          {trouble ? "" : "…"}
        </span>
      )}
    </span>
  );
}
