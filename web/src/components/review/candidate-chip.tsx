"use client";

/**
 * CandidateChip — a class the model proposed for an ambiguous document, shown
 * with its confidence and a keyboard-shortcut hint. Confirm by click or the
 * matching number key. Carries its own category tint for continuity with the
 * archive.
 */

import clsx from "clsx";

import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { tintForSlug } from "@/features/archive/taxonomy";

export function CandidateChip({
  name,
  parentSlug,
  slug,
  confidence,
  shortcut,
  onConfirm,
  disabled,
}: {
  name: string;
  parentSlug: string | null;
  slug: string;
  confidence: number | null;
  shortcut?: number;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const tint = tintForSlug(parentSlug ?? slug);
  return (
    <button
      type="button"
      onClick={onConfirm}
      disabled={disabled}
      className={clsx(
        "group flex w-full items-center gap-3 rounded-lg border border-border bg-surface p-3 text-left transition-colors",
        "hover:border-accent-300 hover:bg-accent-50 focus-visible:border-accent disabled:opacity-60",
      )}
    >
      <span
        aria-hidden
        className="size-3 shrink-0 rounded-[3px]"
        style={{ backgroundColor: tint }}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate type-headline text-text-1">{name}</span>
          {parentSlug ? (
            <span className="shrink-0 type-caption text-text-3">{parentSlug}</span>
          ) : null}
        </span>
        <ConfidenceBar value={confidence} className="mt-1.5" />
      </span>
      {shortcut ? (
        <kbd className="flex size-6 shrink-0 items-center justify-center rounded-md border border-border bg-surface-2 type-caption text-text-2 group-hover:border-accent-300">
          {shortcut}
        </kbd>
      ) : null}
    </button>
  );
}
