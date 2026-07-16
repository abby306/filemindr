"use client";

/**
 * DocumentScreen — the split document view: rendered source (left) ⇄ extracted
 * card (right). Typed facts carry a provenance jump (↩) that flips the source
 * pane to the fact's page and flashes it. Read/verify surface for this milestone;
 * class editing lives in the Review deck (and the add/replace archive pass).
 */

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CornerDownLeft, FileText, MessageSquareText } from "lucide-react";

import { PipelineFill } from "@/components/upload/pipeline-fill";
import { SourcePane } from "@/components/documents/source-pane";
import { ClassChip } from "@/components/ui/class-chip";
import { Sheet } from "@/components/ui/sheet";
import { StatusBadge } from "@/components/ui/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocument, useDocumentFacts } from "@/features/documents/queries";
import { isProcessing } from "@/features/archive/taxonomy";
import { useMedia } from "@/lib/use-media";
import type { DocumentCard } from "@/lib/api/types";

export function DocumentScreen({
  documentId,
  initialPage,
  initialFact,
}: {
  documentId: string;
  /** Land on this page — e.g. arriving from a citation. */
  initialPage?: number;
  /** Cited fact id → sweep a highlighter over its exact region (SourceGlow). */
  initialFact?: string;
}) {
  const { data: doc, isPending, isError, error } = useDocument(documentId);
  const { data: facts } = useDocumentFacts(documentId, !!initialFact);
  const targetFact = initialFact ? facts?.find((f) => f.id === initialFact) : undefined;

  const [manualPage, setManualPage] = useState<number | null>(null);
  const [flashKey, setFlashKey] = useState(initialPage && !initialFact ? 1 : 0);
  const sourceRef = useRef<HTMLElement>(null);

  // Below lg the source pane lives in a bottom sheet (opened by the "View
  // source" button or any provenance jump); a citation arrival opens it too.
  const isDesktop = useMedia("(min-width: 1024px)", true);
  const [sourceOpen, setSourceOpen] = useState(!!initialPage || !!initialFact);

  // Page follows the user's navigation, else the cited fact's page, else ?p.
  const page =
    manualPage ?? targetFact?.page ?? (initialPage && initialPage > 0 ? initialPage : 1);
  const highlightBbox =
    targetFact && targetFact.page === page ? targetFact.bbox : null;

  const jumpTo = useCallback(
    (target: number | null) => {
      if (!target || target < 1) return;
      setManualPage(target);
      setFlashKey((k) => k + 1);
      if (isDesktop) {
        sourceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        setSourceOpen(true);
      }
    },
    [isDesktop],
  );

  const sourcePane = doc ? (
    <SourcePane
      documentId={doc.id}
      filename={doc.original_filename}
      mimeType={doc.mime_type}
      pageCount={doc.page_count}
      page={page}
      onPageChange={setManualPage}
      flashKey={flashKey}
      highlightBbox={highlightBbox}
    />
  ) : null;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <Link
        href="/archive"
        className="mb-5 inline-flex items-center gap-1.5 type-subhead text-text-2 transition-colors hover:text-text-1"
      >
        <ArrowLeft aria-hidden className="size-4" />
        Archive
      </Link>

      {isPending ? (
        <Skeleton className="h-[60vh] w-full" />
      ) : isError ? (
        <NotFound message={error instanceof Error ? error.message : undefined} />
      ) : isDesktop ? (
        <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,1fr)_26rem] lg:items-start">
          <section
            ref={sourceRef}
            className="lg:sticky lg:top-6 lg:h-[calc(100dvh-9rem)]"
          >
            {sourcePane}
          </section>

          <section className="flex flex-col gap-7">
            <Card doc={doc} onJump={jumpTo} />
          </section>
        </div>
      ) : (
        <div className="flex flex-col gap-7">
          <button
            type="button"
            onClick={() => setSourceOpen(true)}
            className="flex min-h-11 w-fit items-center gap-2 rounded-lg border border-border bg-surface px-3.5 type-subhead text-text-1 transition-colors hover:bg-surface-2"
          >
            <FileText aria-hidden className="size-4 text-text-3" />
            View source
            {doc.page_count ? (
              <span className="type-data text-text-3">
                {doc.page_count} {doc.page_count === 1 ? "page" : "pages"}
              </span>
            ) : null}
          </button>
          <Card doc={doc} onJump={jumpTo} />
          <Sheet
            open={sourceOpen}
            onClose={() => setSourceOpen(false)}
            title={doc.title?.trim() || doc.original_filename}
            tall
          >
            <div className="h-full">{sourcePane}</div>
          </Sheet>
        </div>
      )}
    </div>
  );
}

function Card({
  doc,
  onJump,
}: {
  doc: DocumentCard;
  onJump: (page: number | null) => void;
}) {
  const title = doc.title?.trim() || doc.original_filename;
  const primary = doc.classes.find((c) => c.is_primary) ?? doc.classes[0];
  const meta = [
    doc.page_count ? `${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"}` : null,
    doc.language?.toUpperCase() ?? null,
    doc.fact_count > 0 ? `${doc.fact_count} facts indexed` : null,
  ].filter(Boolean);

  return (
    <>
      <header>
        {primary ? (
          <p className="eyebrow mb-1.5">{primary.parent_slug ?? primary.slug}</p>
        ) : null}
        <h1 className="type-title1 text-text-1">{title}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
          {isProcessing(doc.status) ? (
            <PipelineFill status={doc.status} />
          ) : (
            <StatusBadge status={doc.status} />
          )}
          {meta.map((m) => (
            <span key={m} className="type-caption text-text-3">
              {m}
            </span>
          ))}
        </div>
        <p className="mt-2 type-data text-text-3">{doc.original_filename}</p>
        <Link
          href={`/chat?doc=${doc.id}`}
          className="mt-4 inline-flex min-h-9 items-center gap-2 rounded-md border border-border bg-surface px-3 type-subhead text-text-1 transition-colors hover:border-accent-300 hover:bg-accent-50"
        >
          <MessageSquareText aria-hidden className="size-4 text-accent" />
          Ask about this document
        </Link>
      </header>

      {doc.status === "needs_review" ? (
        <Link
          href="/review"
          className="flex items-center justify-between rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 type-subhead text-warn-text transition-colors hover:bg-warn/15"
        >
          This document is awaiting review
          <span aria-hidden>→</span>
        </Link>
      ) : null}

      <Section title="Classes">
        {doc.classes.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {doc.classes.map((c) => (
              <ClassChip
                key={c.slug}
                name={c.name ?? c.slug}
                confidence={c.confidence}
                primary={c.is_primary}
              />
            ))}
          </div>
        ) : (
          <Empty>No class yet.</Empty>
        )}
      </Section>

      {doc.summary ? (
        <Section title="Summary">
          <p className="type-body text-text-2">{doc.summary}</p>
        </Section>
      ) : null}

      {doc.typed_facts.length > 0 ? (
        <Section title="Facts">
          <dl className="flex flex-col divide-y divide-border overflow-hidden rounded-lg border border-border">
            {doc.typed_facts.map((f, i) => (
              <div key={`${f.label}-${i}`} className="flex items-center gap-3 px-3 py-2.5">
                <dt className="type-subhead text-text-2">{humanize(f.label)}</dt>
                <dd className="ml-auto flex items-center gap-2 text-right">
                  <span className="type-data text-text-1">
                    {f.value ?? f.value_numeric ?? "—"}
                    {f.unit ? ` ${f.unit}` : ""}
                  </span>
                  {f.page ? (
                    <button
                      type="button"
                      aria-label={`Show source on page ${f.page}`}
                      onClick={() => onJump(f.page)}
                      className="flex size-6 items-center justify-center rounded-md text-text-3 transition-colors hover:bg-accent-50 hover:text-accent"
                    >
                      <CornerDownLeft aria-hidden className="size-3.5" />
                    </button>
                  ) : null}
                </dd>
              </div>
            ))}
          </dl>
        </Section>
      ) : null}

      {hasEntities(doc) ? (
        <Section title="People & places">
          <div className="flex flex-col gap-3">
            <EntityGroup label="People" names={doc.entities.people} />
            <EntityGroup label="Organizations" names={doc.entities.organizations} />
            <EntityGroup label="Places" names={doc.entities.places} />
          </div>
        </Section>
      ) : null}

      {doc.dates.length > 0 ? (
        <Section title="Dates">
          <ul className="flex flex-col gap-1.5">
            {doc.dates.map((d, i) => (
              <li key={i} className="flex items-center gap-3">
                <span className="type-data text-text-1">{d.value ?? d.raw_text}</span>
                <span className="type-caption text-text-3">{d.role}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2.5 type-caption uppercase text-text-3">{title}</h2>
      {children}
    </section>
  );
}

function EntityGroup({ label, names }: { label: string; names: string[] }) {
  if (names.length === 0) return null;
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span className="type-caption text-text-3">{label}</span>
      {names.map((n) => (
        <span
          key={n}
          className="rounded-full bg-surface-2 px-2 py-0.5 type-subhead text-text-2"
        >
          {n}
        </span>
      ))}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="type-callout text-text-3">{children}</p>;
}

function NotFound({ message }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/60 py-20 text-center">
      <h1 className="type-title2 text-text-1">Document not found</h1>
      <p className="mt-1 type-callout text-text-2">
        {message || "It may have been removed, or belongs to another account."}
      </p>
      <Link
        href="/archive"
        className="mt-5 flex min-h-11 items-center rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
      >
        Back to archive
      </Link>
    </div>
  );
}

function hasEntities(doc: DocumentCard): boolean {
  const e = doc.entities;
  return e.people.length + e.organizations.length + e.places.length > 0;
}

function humanize(label: string): string {
  return label.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
