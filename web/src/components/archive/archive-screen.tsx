"use client";

/**
 * ArchiveScreen — a dense, sortable document table as the primary view (the
 * gallery of cards stays one toggle away). Folders are demoted to a filter-chip
 * row; the search box filters the loaded pages instantly (title/filename/
 * folder), on top of the server-side folder/status filters. Refiling moved from
 * drag-and-drop to each row's "Move to folder…" menu (see MoveMenu).
 */

import { useState } from "react";
import { FolderOpen, LayoutGrid, Search, TableProperties } from "lucide-react";

import { EmptyState } from "@/components/page-scaffold";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { Toast } from "@/components/ui/toast";
import { DocumentCard } from "@/components/archive/document-card";
import { DocumentTable } from "@/components/archive/document-table";
import { FilterChips } from "@/components/archive/filter-chips";
import { useArchiveDocuments, useClasses } from "@/features/archive/queries";
import { filterKey, resolveFolder } from "@/features/archive/taxonomy";
import type { DocumentSummary } from "@/lib/api/types";

type ViewMode = "table" | "gallery";

export function ArchiveScreen({ folderSegment }: { folderSegment?: string }) {
  const { filter } = resolveFolder(folderSegment);
  const activeKey = filterKey(filter);
  const [view, setView] = useState<ViewMode>("table");
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  const { data: classData } = useClasses();
  const activeClass =
    filter.kind === "class"
      ? classData?.classes.find((c) => c.slug === filter.slug)
      : undefined;

  const title =
    filter.kind === "all"
      ? "All documents"
      : filter.kind === "needs_review"
        ? "Needs review"
        : (activeClass?.name ?? filter.slug);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col px-4 py-6 sm:px-8 sm:py-8">
      <header className="mb-4">
        <p className="eyebrow mb-0.5">Archive</p>
        <h1 className="type-title1 text-text-1">{title}</h1>
      </header>

      <div className="mb-4">
        <FilterChips activeKey={activeKey} />
      </div>

      <div className="mb-4 flex items-center justify-between gap-3">
        <label className="relative flex-1 sm:max-w-72">
          <Search
            aria-hidden
            className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-text-3"
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter documents…"
            aria-label="Filter documents by title, filename, or folder"
            className="min-h-9 w-full rounded-md border border-border bg-surface pl-8 pr-3 type-subhead text-text-1 outline-none transition-colors placeholder:text-text-3 focus-visible:border-accent"
          />
        </label>
        <SegmentedControl<ViewMode>
          ariaLabel="View mode"
          value={view}
          onChange={setView}
          segments={[
            { value: "table", label: "Table", icon: <TableProperties className="size-4" /> },
            { value: "gallery", label: "Gallery", icon: <LayoutGrid className="size-4" /> },
          ]}
        />
      </div>

      <DocumentResults
        filter={filter}
        view={view}
        query={query}
        onMoved={(name) => setToast(`Moved to ${name}`)}
      />

      <Toast open={!!toast} message={toast ?? ""} onDismiss={() => setToast(null)} />
    </div>
  );
}

/** Instant client-side narrowing of the loaded pages (view concern only —
 *  the server filters stay authoritative for what gets loaded). */
function matches(doc: DocumentSummary, q: string): boolean {
  const hay =
    `${doc.title ?? ""} ${doc.original_filename} ${doc.primary_class?.name ?? ""}`.toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => hay.includes(term));
}

function DocumentResults({
  filter,
  view,
  query,
  onMoved,
}: {
  filter: ReturnType<typeof resolveFolder>["filter"];
  view: ViewMode;
  query: string;
  onMoved: (folderName: string) => void;
}) {
  const {
    data,
    isPending,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useArchiveDocuments(filter);

  if (isPending) {
    return view === "table" ? (
      <div className="flex flex-col gap-px overflow-hidden rounded-lg border border-border">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full rounded-none" />
        ))}
      </div>
    ) : (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-surface/50 px-6 py-16 text-center">
        <p className="type-body text-text-2">Couldn&apos;t load documents.</p>
        <button
          type="button"
          onClick={() => refetch()}
          className="min-h-11 rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
        >
          Try again
        </button>
      </div>
    );
  }

  const loaded = data.pages.flatMap((p) => p.items);
  const q = query.trim();
  const docs = q ? loaded.filter((d) => matches(d, q)) : loaded;

  if (loaded.length === 0) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="Nothing filed here yet"
        description="Upload documents and they'll appear in the folder that fits."
      />
    );
  }

  if (docs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-surface/50 px-6 py-12 text-center">
        <p className="type-body text-text-2">
          No loaded documents match “{q}”.
        </p>
        {hasNextPage ? (
          <p className="mt-1 type-callout text-text-3">
            More documents exist — load more below to widen the search.
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {view === "table" ? (
        <DocumentTable docs={docs} onMoved={onMoved} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {docs.map((doc) => (
            <DocumentCard key={doc.id} doc={doc} />
          ))}
        </div>
      )}

      {hasNextPage ? (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="min-h-11 rounded-md border border-border bg-surface px-5 type-subhead text-text-1 transition-colors hover:bg-surface-2 disabled:opacity-60"
          >
            {isFetchingNextPage ? "Loading…" : "Load more"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
