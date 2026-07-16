/**
 * DocumentCard — a clean surface card: title, summary, then a meta footer with
 * the live pipeline state. Color no longer encodes folders (v2); the card lifts
 * gently on hover and materializes with a soft spring when it first appears.
 */

import Link from "next/link";

import { StatusBadge } from "@/components/ui/status-badge";
import { PipelineFill } from "@/components/upload/pipeline-fill";
import { formatDate, pageLabel } from "@/lib/format";
import { isProcessing } from "@/features/archive/taxonomy";
import type { DocumentSummary } from "@/lib/api/types";

export function DocumentCard({ doc }: { doc: DocumentSummary }) {
  const title = doc.title?.trim() || doc.original_filename;
  const showsFilename = title !== doc.original_filename;
  const pages = pageLabel(doc.page_count);

  return (
    <Link
      href={`/documents/${doc.id}`}
      className="group animate-materialize flex flex-col overflow-hidden rounded-lg border border-border bg-card shadow-e1 transition-[box-shadow,transform,border-color] duration-[var(--dur-base)] ease-[var(--ease-quiet)] hover:border-border-strong hover:shadow-e2 focus-visible:shadow-e2"
    >
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
