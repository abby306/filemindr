"use client";

/**
 * ArchiveScreen — a navigable directory over the taxonomy. Root and category
 * folders show a grid of subfolder tiles you step into (BreadcrumbBar drives
 * Back/Up); a leaf (a subclass, a childless category, or "Needs review") shows
 * its documents in the table/gallery. Slugs are unique per account, so each
 * node is a plain /archive/{slug} URL and the hierarchy is derived from the tree.
 */

import { useState } from "react";
import {
  FolderOpen,
  FolderPlus,
  LayoutGrid,
  List,
  Search,
  Sparkles,
  TableProperties,
} from "lucide-react";

import { EmptyState } from "@/components/page-scaffold";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { Toast } from "@/components/ui/toast";
import { BreadcrumbBar } from "@/components/archive/breadcrumb-bar";
import { FolderGrid } from "@/components/archive/folder-grid";
import { FolderTree } from "@/components/archive/folder-tree";
import { FolderChat } from "@/components/archive/folder-chat";
import { LeafView } from "@/components/archive/leaf-view";
import { ArchiveDnd } from "@/features/archive/dnd";
import {
  useArchiveDocuments,
  useClasses,
  useCreateFolder,
} from "@/features/archive/queries";
import { useViewMode, type ViewMode } from "@/features/archive/view-mode";
import {
  breadcrumbFor,
  folderTilesFor,
  parentHref,
  resolveFolder,
} from "@/features/archive/taxonomy";
import type { DocumentSummary } from "@/lib/api/types";

export function ArchiveScreen({ folderSegment }: { folderSegment?: string }) {
  const { filter } = resolveFolder(folderSegment);
  const [view, setView] = useViewMode();
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  const { data: classData, isPending: classesPending } = useClasses();

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

  const crumbs = classData ? breadcrumbFor(filter, classData.classes) : [];
  const upHref = classData ? parentHref(filter, classData.classes) : "/archive";
  const tiles = classData ? folderTilesFor(filter, classData.tree) : null;
  const isFolderView = tiles !== null;

  return (
    <ArchiveDnd onToast={setToast}>
    <div className="mx-auto flex w-full max-w-7xl gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <FolderTree filter={filter} onToast={setToast} />
      <div className="flex min-w-0 flex-1 flex-col">
      <header className="mb-4">
        <p className="eyebrow mb-1">Archive</p>
        {classesPending ? (
          <Skeleton className="h-9 w-64" />
        ) : (
          <BreadcrumbBar
            crumbs={crumbs}
            upHref={upHref}
            canGoUp={filter.kind !== "all"}
          />
        )}
      </header>

      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate type-title1 text-text-1">{title}</h1>
        </div>
        {isFolderView ? (
          <div className="flex items-center gap-3">
            {filter.kind === "class" ? (
              <AskFolderButton onOpen={() => setChatOpen(true)} />
            ) : null}
            <NewFolderButton onCreated={(name) => setToast(`Created “${name}”`)} />
          </div>
        ) : (
          <div className="flex items-center gap-3">
            {filter.kind === "class" ? (
              <AskFolderButton onOpen={() => setChatOpen(true)} />
            ) : null}
            <label className="relative hidden sm:block sm:w-64">
              <Search
                aria-hidden
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-text-3"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter in this folder…"
                aria-label="Filter documents by title, filename, or folder"
                className="min-h-9 w-full rounded-md border border-border bg-surface pl-8 pr-3 type-subhead text-text-1 outline-none transition-colors placeholder:text-text-3 focus-visible:border-accent"
              />
            </label>
            <SegmentedControl<ViewMode>
              ariaLabel="View mode"
              value={view}
              onChange={setView}
              segments={[
                { value: "details", label: "Details", icon: <TableProperties className="size-4" /> },
                { value: "list", label: "List", icon: <List className="size-4" /> },
                { value: "icons", label: "Icons", icon: <LayoutGrid className="size-4" /> },
              ]}
            />
          </div>
        )}
      </div>

      {isFolderView ? (
        <FolderGrid
          tiles={tiles}
          showNeedsReview={filter.kind === "all"}
          onToast={setToast}
        />
      ) : (
        <DocumentResults filter={filter} view={view} query={query} onToast={setToast} />
      )}
      </div>

      {filter.kind === "class" ? (
        <FolderChat
          classSlug={filter.slug}
          folderName={title}
          open={chatOpen}
          onClose={() => setChatOpen(false)}
        />
      ) : null}

      <Toast open={!!toast} message={toast ?? ""} onDismiss={() => setToast(null)} />
    </div>
    </ArchiveDnd>
  );
}

/** Opens the docked, folder-scoped chat. Only shown inside a real folder —
 *  "All documents" is what the full Ask screen already answers. */
function AskFolderButton({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="pressable flex min-h-9 items-center gap-2 rounded-md border border-accent-300 bg-accent-50 px-3 type-subhead text-accent-text transition-colors hover:bg-accent-100"
    >
      <Sparkles aria-hidden className="size-4" strokeWidth={1.75} />
      Ask this folder
    </button>
  );
}

/** Inline folder creation — replaces the retired filter-chip "+" control. */
function NewFolderButton({ onCreated }: { onCreated: (name: string) => void }) {
  const create = useCreateFolder();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  const submit = () => {
    const value = name.trim();
    if (value) create.mutate(value, { onSuccess: () => onCreated(value) });
    setName("");
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="pressable flex min-h-9 items-center gap-2 rounded-md border border-border-strong bg-surface px-3 type-subhead text-text-1 transition-colors hover:bg-surface-2"
      >
        <FolderPlus aria-hidden className="size-4" strokeWidth={1.75} />
        New folder
      </button>
    );
  }

  return (
    <span className="flex min-h-9 items-center rounded-md border border-accent-300 bg-accent-50 px-3 type-subhead text-accent-text">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setOpen(false);
        }}
        onBlur={submit}
        placeholder="Folder name"
        aria-label="New folder name"
        size={14}
        className="bg-transparent outline-none placeholder:text-accent-text/50"
      />
    </span>
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
  onToast,
}: {
  filter: ReturnType<typeof resolveFolder>["filter"];
  view: ViewMode;
  query: string;
  onToast: (message: string) => void;
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
    return view !== "icons" ? (
      <div className="flex flex-col gap-px overflow-hidden rounded-lg border border-border">
        {Array.from({ length: view === "list" ? 12 : 8 }).map((_, i) => (
          <Skeleton
            key={i}
            className={view === "list" ? "h-9 w-full rounded-none" : "h-14 w-full rounded-none"}
          />
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
          className="pressable min-h-11 rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover"
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
        <p className="type-body text-text-2">No loaded documents match “{q}”.</p>
        {hasNextPage ? (
          <p className="mt-1 type-callout text-text-3">
            More documents exist — load more below to widen the search.
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <LeafView
      docs={docs}
      view={view}
      onToast={onToast}
      hasNextPage={!!hasNextPage}
      fetchNextPage={fetchNextPage}
      isFetchingNextPage={isFetchingNextPage}
    />
  );
}
