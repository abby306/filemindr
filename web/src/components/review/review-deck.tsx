"use client";

/**
 * ReviewDeck — the human-in-the-loop labelling queue: one `needs_review`
 * document at a time, keyboard-first (Superhuman-speed × Apple-calm). Candidate
 * classes (when the model was torn) confirm with 1/2/3; otherwise pick or create
 * a folder. Confirming assigns server-side, clears the flag, and advances.
 *
 * The queue is held stable while reviewing; confirmations optimistically advance
 * and reconcile via the mutation. "Undo" reopens the last document to relabel it
 * (there's no server un-assign; relabelling is the correction path).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import Link from "next/link";

import { CandidateChip } from "@/components/review/candidate-chip";
import { ClassPicker } from "@/components/review/class-picker";
import { Skeleton } from "@/components/ui/skeleton";
import { Toast } from "@/components/ui/toast";
import { useClasses } from "@/features/archive/queries";
import {
  useAssignClasses,
  useDocumentCard,
  useReviewQueue,
} from "@/features/review/queries";
import type { ReviewReason } from "@/lib/api/types";

const REASON_LABEL: Record<NonNullable<ReviewReason>, string> = {
  ambiguous: "Torn between a few folders",
  low_confidence: "Not fully sure where this goes",
  no_class: "Couldn’t pick a folder",
};

export function ReviewDeck() {
  const { data: queue, isPending, isError } = useReviewQueue();
  const { data: classData } = useClasses();
  const assign = useAssignClasses();

  const [doneIds, setDoneIds] = useState<Set<string>>(new Set());
  const [skipOffset, setSkipOffset] = useState(0);
  const [toast, setToast] = useState<{ id: string; label: string } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const slugToId = useMemo(
    () => new Map((classData?.classes ?? []).map((c) => [c.slug, c.id])),
    [classData],
  );

  const remaining = useMemo(
    () => (queue ?? []).filter((d) => !doneIds.has(d.id)),
    [queue, doneIds],
  );
  const total = queue?.length ?? 0;
  const current =
    remaining.length > 0 ? remaining[skipOffset % remaining.length] : undefined;

  const { data: card, isPending: cardPending } = useDocumentCard(current?.id);
  const candidates = (card?.classes ?? []).slice(0, 3);

  const advance = useCallback(() => setSkipOffset(0), []);

  const confirm = useCallback(
    (label: string, vars: Parameters<typeof assign.mutate>[0]) => {
      const id = vars.documentId;
      setDoneIds((prev) => new Set(prev).add(id)); // optimistic advance
      advance();
      assign.mutate(vars, {
        onSuccess: () => setToast({ id, label }),
        onError: () =>
          setDoneIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          }),
      });
    },
    [assign, advance],
  );

  const confirmClass = useCallback(
    (classId: string, label: string) => {
      if (!current) return;
      confirm(label, { documentId: current.id, classIds: [classId] });
    },
    [current, confirm],
  );

  const createFolder = useCallback(
    (name: string) => {
      if (!current) return;
      confirm(name, { documentId: current.id, newClass: { name } });
    },
    [current, confirm],
  );

  const skip = useCallback(() => {
    if (remaining.length > 1) setSkipOffset((o) => o + 1);
  }, [remaining.length]);

  const undo = useCallback(() => {
    if (!toast) return;
    setDoneIds((prev) => {
      const next = new Set(prev);
      next.delete(toast.id);
      return next;
    });
    setToast(null);
  }, [toast]);

  // Keyboard: 1/2/3 confirm a candidate, → skip, / focus search (unless typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement;
      const typing =
        el instanceof HTMLElement &&
        (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (e.key === "Escape" && typing) {
        (el as HTMLElement).blur();
        return;
      }
      if (typing || !current) return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        skip();
      } else if (["1", "2", "3"].includes(e.key)) {
        const cand = candidates[Number(e.key) - 1];
        const classId = cand ? slugToId.get(cand.slug) : undefined;
        if (cand && classId) {
          e.preventDefault();
          confirmClass(classId, cand.name ?? cand.slug);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, candidates, slugToId, skip, confirmClass]);

  if (isPending) {
    return (
      <Wrapper>
        <Skeleton className="h-64 w-full" />
      </Wrapper>
    );
  }
  if (isError) {
    return (
      <Wrapper>
        <p className="type-body text-text-2">Couldn’t load the review queue.</p>
      </Wrapper>
    );
  }

  if (!current) {
    return (
      <Wrapper>
        <div className="flex flex-1 flex-col items-center justify-center py-20 text-center">
          <span className="flex size-14 items-center justify-center rounded-full bg-ok/12 text-ok">
            <Check aria-hidden className="size-7" strokeWidth={2} />
          </span>
          <h2 className="mt-5 type-title1 text-text-1">All filed. Inbox zero.</h2>
          <p className="mt-1 type-body text-text-2">
            Nothing is waiting on your review.
          </p>
          <Link
            href="/archive"
            className="mt-6 flex min-h-11 items-center rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
          >
            Open the archive
          </Link>
        </div>
        <Toast
          open={!!toast}
          message={toast ? `Filed as ${toast.label}` : ""}
          actionLabel="Undo"
          onAction={undo}
          onDismiss={() => setToast(null)}
        />
      </Wrapper>
    );
  }

  const title = current.title?.trim() || current.original_filename;
  const reason = current.review_reason
    ? REASON_LABEL[current.review_reason]
    : "Needs a folder";

  return (
    <Wrapper progress={{ done: doneIds.size, total }}>
      <div key={current.id} className="animate-review-in flex flex-col gap-6">
        <div>
          <p className="eyebrow mb-1.5">{reason}</p>
          <h2 className="type-record text-text-1">{title}</h2>
          {cardPending ? (
            <Skeleton className="mt-3 h-12 w-full" />
          ) : card?.summary ? (
            <p className="mt-2 line-clamp-3 type-body text-text-2">{card.summary}</p>
          ) : null}
          <p className="mt-2 type-data text-text-3">{current.original_filename}</p>
        </div>

        {candidates.length > 0 ? (
          <div className="flex flex-col gap-2">
            <p className="type-subhead text-text-2">Best guesses</p>
            {candidates.map((c, i) => {
              const classId = slugToId.get(c.slug);
              return (
                <CandidateChip
                  key={c.slug}
                  name={c.name ?? c.slug}
                  slug={c.slug}
                  parentSlug={c.parent_slug}
                  confidence={c.confidence}
                  shortcut={i + 1}
                  disabled={!classId}
                  onConfirm={() => classId && confirmClass(classId, c.name ?? c.slug)}
                />
              );
            })}
          </div>
        ) : null}

        <div className="flex flex-col gap-2">
          <p className="type-subhead text-text-2">
            {candidates.length > 0 ? "Or choose a folder" : "Choose a folder"}
          </p>
          <ClassPicker
            inputRef={searchRef}
            onPick={(classId) => {
              const name =
                classData?.classes.find((c) => c.id === classId)?.name ?? "folder";
              confirmClass(classId, name);
            }}
            onCreate={createFolder}
          />
        </div>

        <div className="flex items-center justify-between border-t border-border pt-4">
          <span className="type-caption text-text-3">
            <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5">1</kbd>{" "}
            confirm ·{" "}
            <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5">/</kbd>{" "}
            search ·{" "}
            <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5">→</kbd>{" "}
            skip
          </span>
          <button
            type="button"
            onClick={skip}
            disabled={remaining.length <= 1}
            className="flex min-h-9 items-center gap-1.5 rounded-md px-3 type-subhead text-text-2 transition-colors hover:bg-surface-2 hover:text-text-1 disabled:opacity-40"
          >
            Skip
            <ArrowRight aria-hidden className="size-4" />
          </button>
        </div>
      </div>

      <Toast
        open={!!toast}
        message={toast ? `Filed as ${toast.label}` : ""}
        actionLabel="Undo"
        onAction={undo}
        onDismiss={() => setToast(null)}
      />
    </Wrapper>
  );
}

function Wrapper({
  children,
  progress,
}: {
  children: React.ReactNode;
  progress?: { done: number; total: number };
}) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col px-4 py-8 sm:px-8 sm:py-10">
      <header className="mb-8 flex items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-1">Human in the loop</p>
          <h1 className="type-display text-text-1">Review</h1>
        </div>
        {progress && progress.total > 0 ? (
          <span className="rounded-full border border-border bg-surface px-3 py-1 type-caption text-text-2">
            {Math.min(progress.done + 1, progress.total)} of {progress.total}
          </span>
        ) : null}
      </header>

      <div className="flex flex-1 flex-col rounded-xl border border-border bg-card p-6 shadow-e1">
        {children}
      </div>
    </div>
  );
}
