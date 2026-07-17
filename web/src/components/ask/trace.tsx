"use client";

/**
 * Trace — the live activity feed while an answer is worked out (signature
 * motion #2). Every real backend step lands as it happens: the current one
 * spins, finished ones check off, and the elapsed clock ticks — so the
 * silent seconds of model work still show honest progress. When the answer
 * arrives it collapses to one quiet mono line ("✓ searched your archive ·
 * 3 sources · 1.8s") that re-opens to the steps. Data voice = mono.
 */

import { useEffect, useState } from "react";
import {
  BookOpen,
  Brain,
  Check,
  Compass,
  FileText,
  FolderSearch,
  Layers,
  Loader2,
  Search,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";

import type { TraceStep } from "@/features/ask/types";

const SHOWN = new Set([
  "intent",
  "retrieved",
  "thinking",
  "find_documents",
  "searching",
  "reading",
  "escalating",
]);

/** The intent router's verdict, in plain words. */
const INTENT_LABEL: Record<string, string> = {
  semantic: "looking for meaning",
  lexical: "matching exact words",
  aggregate: "adding up numbers",
  metadata: "checking dates and details",
};

interface StepSource {
  title: string;
  facts?: number;
}

interface StepView {
  icon: LucideIcon;
  label: string;
  detail?: string;
  /** The documents this step actually read (title + per-doc match count). */
  sources?: StepSource[];
  /** Documents beyond the listed ones ("+2 more"). */
  moreDocuments?: number;
  /** Trimmed matched-fact snippets — the key data the step surfaced. */
  highlights?: string[];
}

/** The server's transparency payload (sources/highlights), when present. */
function evidence(d: Record<string, unknown>): Pick<StepView, "sources" | "moreDocuments" | "highlights"> {
  const sources = Array.isArray(d.sources) ? (d.sources as StepSource[]) : undefined;
  const highlights = Array.isArray(d.highlights) ? (d.highlights as string[]) : undefined;
  return {
    sources: sources?.length ? sources : undefined,
    moreDocuments: typeof d.more_documents === "number" && d.more_documents > 0 ? d.more_documents : undefined,
    highlights: highlights?.length ? highlights : undefined,
  };
}

function describe(step: TraceStep): StepView {
  const d = step.data;
  const found = typeof d.found === "number" ? d.found : null;
  switch (step.type) {
    case "intent":
      return {
        icon: Compass,
        label: "Understanding the question",
        detail:
          typeof d.intent === "string"
            ? (INTENT_LABEL[d.intent] ?? d.intent)
            : undefined,
      };
    case "retrieved":
      return {
        icon: Layers,
        label: "Gathering facts from your documents",
        detail:
          found != null
            ? `${found} fact${found === 1 ? "" : "s"} · ${d.documents} document${d.documents === 1 ? "" : "s"}`
            : undefined,
        ...evidence(d),
      };
    case "thinking":
      return {
        icon: Brain,
        label:
          d.step === 1 ? "Reading the top matches" : "Putting the answer together",
      };
    case "find_documents":
      return {
        icon: FolderSearch,
        label: "Finding the right documents",
        detail: [d.query, found != null ? `${found} found` : null]
          .filter(Boolean)
          .join(" · "),
        ...evidence(d),
      };
    case "searching":
      return {
        icon: Search,
        label: "Searching deeper",
        detail: [
          typeof d.query === "string" ? `“${d.query}”` : null,
          found != null ? `${found} found` : null,
        ]
          .filter(Boolean)
          .join(" · "),
        ...evidence(d),
      };
    case "reading":
      return {
        icon: BookOpen,
        label: "Reading the source page",
        detail: [
          typeof d.document === "string" ? d.document : null,
          typeof d.page === "number" && d.page > 0 ? `p${d.page}` : null,
        ]
          .filter(Boolean)
          .join(" · "),
      };
    case "escalating":
      return { icon: Sparkles, label: "Double-checking with a stronger model" };
    default:
      return { icon: Search, label: step.type };
  }
}

/** Collapse runs of identical steps (repeated "putting it together" turns) —
 *  but two searches/reads with different details each keep their row. */
function toViews(steps: TraceStep[]): StepView[] {
  const views: StepView[] = [];
  for (const step of steps) {
    if (!SHOWN.has(step.type)) continue;
    const view = describe(step);
    const prev = views[views.length - 1];
    if (prev && prev.label === view.label && prev.detail === view.detail) {
      views[views.length - 1] = view;
    } else {
      views.push(view);
    }
  }
  return views;
}

/** The proof under a retrieval step: file chips + the matched key data. */
function Evidence({ view }: { view: StepView }) {
  if (!view.sources && !view.highlights) return null;
  return (
    <div className="ml-6 flex min-w-0 flex-col gap-1">
      {view.sources ? (
        <div className="flex flex-wrap items-center gap-1">
          {view.sources.map((s) => (
            <span
              key={s.title}
              className="inline-flex max-w-64 items-center gap-1 rounded bg-surface-2 px-1.5 py-0.5"
            >
              <FileText aria-hidden className="size-3 shrink-0 text-text-3" />
              <span className="truncate type-caption font-normal text-text-2">{s.title}</span>
              {s.facts != null && s.facts > 1 ? (
                <span className="shrink-0 type-data text-[11px] text-text-3">×{s.facts}</span>
              ) : null}
            </span>
          ))}
          {view.moreDocuments ? (
            <span className="type-caption text-text-3">+{view.moreDocuments} more</span>
          ) : null}
        </div>
      ) : null}
      {view.highlights?.map((h) => (
        <p key={h} className="truncate type-data text-text-3">
          “{h}”
        </p>
      ))}
    </div>
  );
}

function useElapsedSeconds(startedAt: number | undefined, running: boolean): number | null {
  // The clock first appears at "1s" — no synchronous set, no render-time Date.
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);
  if (!startedAt || !running || now == null) return null;
  return Math.max(0, Math.floor((now - startedAt) / 1000));
}

export function Trace({
  steps,
  streaming,
  elapsedMs,
  sourceCount,
  scopeLabel,
  startedAt,
}: {
  steps: TraceStep[];
  streaming: boolean;
  elapsedMs?: number;
  /** Cited sources on the finished answer (for the collapsed summary line). */
  sourceCount?: number;
  /** What was searched, when scoped (e.g. a document title); default archive. */
  scopeLabel?: string;
  /** When this turn started — drives the live elapsed clock while streaming. */
  startedAt?: number;
}) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const elapsed = useElapsedSeconds(startedAt, streaming);
  const views = toViews(steps);

  if (!streaming && views.length === 0) return null;

  // --- live activity card (while the answer is being worked out) -----------
  if (streaming) {
    // Until the first backend event lands (initial retrieval), show the one
    // thing that is honestly happening rather than an empty card.
    const liveViews: StepView[] =
      views.length > 0
        ? views
        : [{ icon: Search, label: "Searching your archive" }];
    return (
      <div className="mb-3 rounded-lg border border-border bg-surface px-3.5 py-3">
        <div className="flex items-center gap-2">
          <Loader2 aria-hidden className="size-3.5 text-accent motion-safe:animate-spin" />
          <span className="type-subhead text-text-1">Working on it</span>
          {elapsed != null ? (
            <span className="ml-auto type-data text-text-3">{elapsed}s</span>
          ) : null}
        </div>
        <ol className="mt-2.5 flex flex-col gap-2">
          {liveViews.map((view, i) => {
            const active = i === liveViews.length - 1;
            const Icon = active ? view.icon : Check;
            return (
              <li key={`${view.label}-${i}`} className="animate-trace-in flex min-w-0 flex-col gap-1">
                <span className="flex items-center gap-2.5">
                  <Icon
                    aria-hidden
                    className={clsx(
                      "size-3.5 shrink-0",
                      active ? "text-accent" : "text-ok",
                    )}
                    strokeWidth={active ? 1.75 : 2.5}
                  />
                  <span
                    className={clsx(
                      "shrink-0 type-caption",
                      active ? "text-text-1" : "text-text-2",
                    )}
                  >
                    {view.label}
                  </span>
                  {view.detail ? (
                    <span className="truncate type-data text-text-3">{view.detail}</span>
                  ) : null}
                </span>
                <Evidence view={view} />
              </li>
            );
          })}
        </ol>
      </div>
    );
  }

  // --- finished: the quiet mono line, expandable back to the steps ---------
  const open = manualOpen ?? false;
  const summary = [
    `searched ${scopeLabel ?? "your archive"}`,
    sourceCount ? `${sourceCount} source${sourceCount === 1 ? "" : "s"}` : null,
    elapsedMs ? `${(elapsedMs / 1000).toFixed(1)}s` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="mb-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setManualOpen(!open)}
        className="flex min-h-11 items-center gap-1.5 text-left type-data text-text-3 transition-colors hover:text-text-2 sm:min-h-0"
      >
        <Check aria-hidden className="size-3 text-ok" strokeWidth={2.5} />
        {summary}
      </button>

      {open ? (
        <ol className="mt-2 flex flex-col gap-2 border-l border-border pl-3">
          {views.map((view, i) => (
            <li key={`${view.label}-${i}`} className="animate-trace-in flex min-w-0 flex-col gap-1">
              <span className="flex items-center gap-2">
                <view.icon aria-hidden className="size-3.5 shrink-0 text-accent" />
                <span className="shrink-0 type-caption text-text-2">{view.label}</span>
                {view.detail ? (
                  <span className="truncate type-data text-text-3">{view.detail}</span>
                ) : null}
              </span>
              <Evidence view={view} />
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
