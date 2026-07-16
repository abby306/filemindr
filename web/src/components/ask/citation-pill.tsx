"use client";

/** CitationPill — one grounded source (grouped by document). Click opens the
 *  document view at the cited page, where the source pane flashes it (SourceGlow). */

import Link from "next/link";
import { MapPin } from "lucide-react";

import type { CitationGroup } from "@/lib/api/types";

export function CitationPill({ group }: { group: CitationGroup }) {
  const firstPage = group.pages[0];
  const factId = group.fact_ids[0];
  const params = new URLSearchParams();
  if (firstPage) params.set("p", String(firstPage));
  if (factId) params.set("fact", factId);
  const qs = params.toString();
  const href = qs
    ? `/documents/${group.document_id}?${qs}`
    : `/documents/${group.document_id}`;
  const pages =
    group.pages.length > 0
      ? `p${group.pages.length > 1 ? group.pages.join(", ") : group.pages[0]}`
      : null;

  return (
    <Link
      href={href}
      className="animate-materialize inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 transition-colors hover:border-hl hover:bg-hl-wash"
    >
      <MapPin aria-hidden className="size-3 shrink-0 text-hl-strong" />
      <span className="truncate type-data text-text-1">
        {group.title || "Document"}
      </span>
      {pages ? <span className="shrink-0 type-data text-text-3">{pages}</span> : null}
    </Link>
  );
}
