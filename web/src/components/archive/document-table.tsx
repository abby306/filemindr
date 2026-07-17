"use client";

/**
 * DocumentTable — the archive's primary view: a dense, sortable table. Columns:
 * document (first-page thumbnail + title), folder (primary class), status
 * (live pipeline while processing), size, date. Sorting is client-side over the
 * loaded pages (the server's keyset order is the date-desc default); rows rise
 * in with a 40ms stagger. Below `sm` the table collapses to a compact list.
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import clsx from "clsx";

import { PageThumb } from "@/components/archive/page-thumb";
import { MoveMenu } from "@/components/archive/move-menu";
import { RetryButton } from "@/components/documents/retry-button";
import { StatusBadge } from "@/components/ui/status-badge";
import { PipelineFill } from "@/components/upload/pipeline-fill";
import { isProcessing } from "@/features/archive/taxonomy";
import { formatBytes, formatDate } from "@/lib/format";
import type { DocumentSummary } from "@/lib/api/types";

type SortKey = "title" | "folder" | "size" | "date";
type SortDir = "asc" | "desc";

const displayTitle = (d: DocumentSummary) => d.title?.trim() || d.original_filename;

const COMPARE: Record<SortKey, (a: DocumentSummary, b: DocumentSummary) => number> = {
  title: (a, b) =>
    displayTitle(a).localeCompare(displayTitle(b), undefined, { sensitivity: "base" }),
  // Unfiled documents sort after every named folder.
  folder: (a, b) =>
    (a.primary_class?.name ?? "￿").localeCompare(
      b.primary_class?.name ?? "￿",
      undefined,
      { sensitivity: "base" },
    ),
  size: (a, b) => (a.byte_size ?? 0) - (b.byte_size ?? 0),
  date: (a, b) => a.created_at.localeCompare(b.created_at),
};

/** Rows past the first dozen skip the stagger so late rows don't lag. */
const riseDelay = (i: number) => ({ animationDelay: `${Math.min(i, 12) * 40}ms` });

export function DocumentTable({
  docs,
  onMoved,
}: {
  docs: DocumentSummary[];
  onMoved: (folderName: string) => void;
}) {
  const router = useRouter();
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({
    key: "date",
    dir: "desc",
  });

  const toggleSort = (key: SortKey) =>
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "title" || key === "folder" ? "asc" : "desc" },
    );

  const sorted = useMemo(() => {
    const rows = [...docs].sort(COMPARE[sort.key]);
    if (sort.dir === "desc") rows.reverse();
    return rows;
  }, [docs, sort]);

  return (
    <>
      {/* sm+: the dense table */}
      <div className="hidden overflow-x-auto rounded-lg border border-border bg-card sm:block">
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            <col />
            <col className="w-36" />
            <col className="w-40" />
            <col className="w-20" />
            <col className="w-32" />
            <col className="w-12" />
          </colgroup>
          <thead>
            <tr className="border-b border-border">
              <Th label="Document" sortKey="title" sort={sort} onSort={toggleSort} />
              <Th label="Folder" sortKey="folder" sort={sort} onSort={toggleSort} />
              <th className="px-3 py-2 text-left type-caption uppercase text-text-3">
                Status
              </th>
              <Th label="Size" sortKey="size" sort={sort} onSort={toggleSort} alignRight />
              <Th label="Date" sortKey="date" sort={sort} onSort={toggleSort} />
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((doc, i) => (
              <tr
                key={doc.id}
                onClick={() => router.push(`/documents/${doc.id}`)}
                style={riseDelay(i)}
                className="animate-rise-in group cursor-pointer border-b border-border transition-colors duration-[var(--dur-micro)] last:border-b-0 hover:bg-surface-2"
              >
                <td className="py-2 pl-3 pr-2">
                  <div className="flex items-center gap-3">
                    <PageThumb
                      documentId={doc.id}
                      mimeType={doc.mime_type}
                      className="h-10 w-8"
                    />
                    <div className="min-w-0">
                      <Link
                        href={`/documents/${doc.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="block truncate type-subhead text-text-1 transition-colors group-hover:text-accent-text"
                      >
                        {displayTitle(doc)}
                      </Link>
                      <p className="truncate type-caption font-normal text-text-3">
                        {doc.original_filename}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="truncate px-3 py-2">
                  {doc.primary_class ? (
                    <Link
                      href={`/archive/${doc.primary_class.slug}`}
                      onClick={(e) => e.stopPropagation()}
                      className="type-callout text-text-2 transition-colors hover:text-accent-text"
                    >
                      {doc.primary_class.name ?? doc.primary_class.slug}
                    </Link>
                  ) : (
                    <span className="type-callout text-text-3">—</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-2">
                    {isProcessing(doc.status) ? (
                      <PipelineFill status={doc.status} />
                    ) : (
                      <StatusBadge status={doc.status} />
                    )}
                    {doc.status === "failed" ? (
                      <RetryButton documentId={doc.id} />
                    ) : null}
                  </span>
                </td>
                <td className="px-3 py-2 text-right type-data text-text-2">
                  {formatBytes(doc.byte_size) ?? "—"}
                </td>
                <td className="whitespace-nowrap px-3 py-2 type-data text-text-2">
                  {formatDate(doc.created_at)}
                </td>
                <td className="py-2 pr-2">
                  <MoveMenu doc={doc} onMoved={onMoved} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* <sm: compact list */}
      <div className="overflow-hidden rounded-lg border border-border bg-card sm:hidden">
        {sorted.map((doc, i) => (
          <div
            key={doc.id}
            style={riseDelay(i)}
            className="animate-rise-in flex items-center gap-3 border-b border-border py-2.5 pl-3 pr-1 last:border-b-0"
          >
            <Link
              href={`/documents/${doc.id}`}
              className="flex min-w-0 flex-1 items-center gap-3"
            >
              <PageThumb documentId={doc.id} mimeType={doc.mime_type} className="h-12 w-9" />
              <div className="min-w-0 flex-1">
                <p className="truncate type-subhead text-text-1">{displayTitle(doc)}</p>
                <p className="truncate type-caption font-normal text-text-3">
                  {[doc.primary_class?.name, formatDate(doc.created_at)]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <div className="mt-0.5 flex items-center gap-2">
                  {isProcessing(doc.status) ? (
                    <PipelineFill status={doc.status} showTrack={false} />
                  ) : (
                    <StatusBadge status={doc.status} />
                  )}
                  {doc.status === "failed" ? (
                    <RetryButton documentId={doc.id} />
                  ) : null}
                </div>
              </div>
            </Link>
            <MoveMenu doc={doc} onMoved={onMoved} />
          </div>
        ))}
      </div>
    </>
  );
}

function Th({
  label,
  sortKey,
  sort,
  onSort,
  alignRight,
}: {
  label: string;
  sortKey: SortKey;
  sort: { key: SortKey; dir: SortDir };
  onSort: (key: SortKey) => void;
  alignRight?: boolean;
}) {
  const active = sort.key === sortKey;
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={clsx("px-3 py-2", alignRight ? "text-right" : "text-left")}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={clsx(
          "inline-flex items-center gap-1 rounded-sm type-caption uppercase transition-colors",
          active ? "text-text-1" : "text-text-3 hover:text-text-1",
        )}
      >
        {label}
        <Icon aria-hidden className={clsx("size-3", !active && "opacity-60")} />
      </button>
    </th>
  );
}
