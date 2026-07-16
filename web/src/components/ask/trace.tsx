"use client";

/**
 * Trace — the retrieval steps in plain language (signature motion #2: each step
 * fades + rises in as it streams). Expanded while working; collapses to
 * "Worked for Ns" when done (the user can re-open). Data voice = mono.
 */

import { useState } from "react";
import {
  ChevronRight,
  Compass,
  FolderSearch,
  Loader2,
  Search,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";

import type { TraceStep } from "@/features/ask/types";

const SHOWN = new Set(["intent", "find_documents", "searching", "escalating"]);

const META: Record<string, { icon: LucideIcon; label: string }> = {
  intent: { icon: Compass, label: "Understanding the question" },
  find_documents: { icon: FolderSearch, label: "Finding relevant documents" },
  searching: { icon: Search, label: "Searching your archive" },
  escalating: { icon: Sparkles, label: "Thinking harder" },
};

function detailOf(data: Record<string, unknown>): string | null {
  for (const key of ["query", "intent", "class", "document_ref", "name", "about", "detail"]) {
    const v = data[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  return null;
}

export function Trace({
  steps,
  streaming,
  elapsedMs,
}: {
  steps: TraceStep[];
  streaming: boolean;
  elapsedMs?: number;
}) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const shown = steps.filter((s) => SHOWN.has(s.type));

  if (!streaming && shown.length === 0) return null;

  const open = manualOpen ?? streaming;
  const seconds = elapsedMs ? (elapsedMs / 1000).toFixed(1) : null;

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setManualOpen(!open)}
        className="flex items-center gap-1.5 type-caption text-text-3 transition-colors hover:text-text-2"
      >
        {streaming ? (
          <Loader2 aria-hidden className="size-3 text-accent motion-safe:animate-spin" />
        ) : (
          <ChevronRight
            aria-hidden
            className={clsx("size-3.5 transition-transform", open && "rotate-90")}
          />
        )}
        {streaming
          ? "Working…"
          : seconds
            ? `Worked for ${seconds}s`
            : `${shown.length} step${shown.length === 1 ? "" : "s"}`}
      </button>

      {open ? (
        <ol className="mt-2 flex flex-col gap-1.5 border-l border-border pl-3">
          {shown.map((step, i) => {
            const meta = META[step.type] ?? { icon: Search, label: step.type };
            const Icon = meta.icon;
            const detail = detailOf(step.data);
            return (
              <li
                key={i}
                className="flex items-center gap-2 animate-trace-in"
              >
                <Icon aria-hidden className="size-3.5 shrink-0 text-accent" />
                <span className="type-caption text-text-2">{meta.label}</span>
                {detail ? (
                  <span className="truncate type-data text-text-3">{detail}</span>
                ) : null}
              </li>
            );
          })}
          {streaming ? (
            <li className="flex items-center gap-2 type-caption text-text-3">
              <Loader2 aria-hidden className="size-3 motion-safe:animate-spin" />
              …
            </li>
          ) : null}
        </ol>
      ) : null}
    </div>
  );
}
