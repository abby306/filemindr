/**
 * PipelineFill — signature motion #1. Four stage pips advance
 * received → ocr_done → extracted → indexed, bound to the real backend status.
 * Completed stages fill solid, the active stage pulses, future stages stay
 * hollow. Shown while a document is processing; terminal states use StatusBadge.
 */

import clsx from "clsx";

import { STATUS_META } from "@/features/archive/taxonomy";
import type { DocumentStatus } from "@/lib/api/types";

const STAGES: DocumentStatus[] = ["received", "ocr_done", "extracted", "indexed"];

export function PipelineFill({ status }: { status: DocumentStatus }) {
  const idx = STAGES.indexOf(status);
  const meta = STATUS_META[status];

  return (
    <span className="inline-flex items-center gap-2" title={`${meta.label}…`}>
      <span aria-hidden className="flex items-center gap-1">
        {STAGES.map((stage, i) => {
          const done = i < idx;
          const active = i === idx;
          return (
            <span
              key={stage}
              className={clsx(
                "h-1.5 rounded-full transition-all duration-[var(--dur-base)] ease-[var(--ease-quiet)]",
                done && "w-4 bg-accent",
                active && "w-4 bg-accent motion-safe:animate-pulse",
                !done && !active && "w-2 bg-border-strong",
              )}
            />
          );
        })}
      </span>
      <span className="type-caption text-accent">{meta.label}…</span>
    </span>
  );
}
