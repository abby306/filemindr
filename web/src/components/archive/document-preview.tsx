"use client";

/**
 * DocumentPreview — the card a document shows when selected (preview pane) or
 * peeked (Quick Look): first page + title + status + a few typed facts and
 * parties, pulled from the shared ["document"] cache. Read-only; "Open" lives
 * with the caller. `size="pane"` is the compact right-rail form; `size="look"`
 * is the roomier modal form.
 */

import { PageThumb } from "@/components/archive/page-thumb";
import { StatusBadge } from "@/components/ui/status-badge";
import { useDocument } from "@/features/documents/queries";
import { formatBytes, formatDate } from "@/lib/format";
import type { DocumentSummary } from "@/lib/api/types";

export function DocumentPreview({
  doc,
  size = "pane",
}: {
  doc: DocumentSummary;
  size?: "pane" | "look";
}) {
  const { data: card } = useDocument(doc.id);
  const title = doc.title?.trim() || doc.original_filename;
  const parties = card
    ? [...card.entities.organizations, ...card.entities.people].slice(0, 5)
    : [];
  const facts = card?.typed_facts.filter((f) => f.value).slice(0, 6) ?? [];

  return (
    <div className="flex flex-col gap-3">
      <PageThumb
        documentId={doc.id}
        mimeType={doc.mime_type}
        className={size === "look" ? "aspect-[3/4] w-full" : "aspect-[3/3.6] w-full"}
      />

      <div>
        <p className="type-record text-text-1">{title}</p>
        <p className="type-data text-text-3">{doc.original_filename}</p>
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusBadge status={doc.status} />
        <span className="type-data text-text-3">
          {[formatBytes(doc.byte_size), formatDate(doc.created_at), doc.primary_class?.name]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>

      {doc.summary ? (
        <p className={size === "look" ? "type-callout text-text-2" : "type-caption font-normal text-text-2"}>
          {doc.summary}
        </p>
      ) : null}

      {parties.length ? (
        <div>
          <p className="eyebrow mb-1.5">Parties</p>
          <div className="flex flex-wrap gap-1.5">
            {parties.map((p, i) => (
              <span
                key={i}
                className="rounded-full border border-border bg-surface-2 px-2 py-0.5 type-caption text-text-2"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {facts.length ? (
        <div>
          <p className="eyebrow mb-1.5">Key facts</p>
          <dl className="flex flex-col gap-1.5">
            {facts.map((f, i) => (
              <div key={i} className="flex items-baseline justify-between gap-3">
                <dt className="type-caption font-normal text-text-3">{f.label}</dt>
                <dd className="type-data text-right text-text-1">{f.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
