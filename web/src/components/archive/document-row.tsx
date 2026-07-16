/** DocumentRow — the List-view counterpart to DocumentCard (compact, scannable). */

import Link from "next/link";
import { FileText } from "lucide-react";

import { StatusBadge } from "@/components/ui/status-badge";
import { formatDate, pageLabel } from "@/lib/format";
import { isProcessing } from "@/features/archive/taxonomy";
import type { DocumentSummary } from "@/lib/api/types";

export function DocumentRow({
  doc,
  tint,
}: {
  doc: DocumentSummary;
  tint?: string;
}) {
  const title = doc.title?.trim() || doc.original_filename;
  const pages = pageLabel(doc.page_count);

  return (
    <Link
      href={`/documents/${doc.id}`}
      className="group flex items-center gap-3 border-b border-border px-3 py-3 transition-colors last:border-b-0 hover:bg-surface-2"
    >
      <span
        aria-hidden
        className="flex size-8 shrink-0 items-center justify-center rounded-md bg-surface-2"
        style={tint ? { backgroundColor: `${tint}22` } : undefined}
      >
        <FileText
          aria-hidden
          className="size-4 text-text-3"
          style={tint ? { color: tint } : undefined}
          strokeWidth={1.75}
        />
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate type-headline text-text-1 group-hover:text-accent">
          {title}
        </p>
        <p className="truncate type-caption text-text-3">{doc.original_filename}</p>
      </div>

      <div className="hidden shrink-0 items-center gap-4 sm:flex">
        {pages ? <span className="type-caption text-text-3">{pages}</span> : null}
        <span className="w-24 type-caption text-text-3">{formatDate(doc.created_at)}</span>
      </div>
      <div className="w-24 shrink-0 text-right">
        <StatusBadge status={doc.status} animate={isProcessing(doc.status)} />
      </div>
    </Link>
  );
}
