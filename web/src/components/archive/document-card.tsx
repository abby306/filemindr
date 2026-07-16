/**
 * DocumentCard — a manila filing card: warm card surface, a bold category tab
 * along the top edge (color that means the folder), a serif "record" title, then
 * summary and a meta footer. Per-document class labels aren't in the list
 * payload, so the tab tints to the active folder when browsing one. Links to the
 * (future) document view; lifts gently on hover.
 */

import Link from "next/link";

import { StatusBadge } from "@/components/ui/status-badge";
import { PipelineFill } from "@/components/upload/pipeline-fill";
import { formatDate, pageLabel } from "@/lib/format";
import { isProcessing } from "@/features/archive/taxonomy";
import type { DocumentSummary } from "@/lib/api/types";

export function DocumentCard({
  doc,
  tint,
}: {
  doc: DocumentSummary;
  /** Folder category color for the card's tab; neutral when absent. */
  tint?: string;
}) {
  const title = doc.title?.trim() || doc.original_filename;
  const showsFilename = title !== doc.original_filename;
  const pages = pageLabel(doc.page_count);

  return (
    <Link
      href={`/documents/${doc.id}`}
      className="group flex flex-col overflow-hidden rounded-lg border border-border bg-card shadow-e1 transition-[box-shadow,transform] duration-[var(--dur-base)] ease-[var(--ease-quiet)] hover:shadow-e2 focus-visible:shadow-e2 motion-safe:hover:-translate-y-0.5"
    >
      {/* category tab */}
      <span
        aria-hidden
        className="h-1.5 w-full"
        style={{ backgroundColor: tint ?? "var(--border-strong)" }}
      />
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="type-record text-text-1 transition-colors group-hover:text-accent">
          {title}
        </h3>
        {doc.summary ? (
          <p className="line-clamp-2 type-callout text-text-2">{doc.summary}</p>
        ) : null}

        <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-1">
          {isProcessing(doc.status) ? (
            <PipelineFill status={doc.status} />
          ) : (
            <StatusBadge status={doc.status} />
          )}
          {pages ? <span className="type-caption text-text-3">{pages}</span> : null}
          <span className="type-caption text-text-3">{formatDate(doc.created_at)}</span>
        </div>

        {showsFilename ? (
          <p className="truncate type-data text-text-3" title={doc.original_filename}>
            {doc.original_filename}
          </p>
        ) : null}
      </div>
    </Link>
  );
}
