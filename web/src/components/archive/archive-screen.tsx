"use client";

/**
 * ArchiveScreen — the Finder-style archive: a folder rail (persistent on wide
 * screens, a disclosure on narrow ones) beside the document grid/list for the
 * selected folder. Documents drag onto folders to refile them (add a label;
 * the server owns add-vs-replace).
 */

import { useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { FolderOpen, LayoutGrid, List } from "lucide-react";

import { EmptyState } from "@/components/page-scaffold";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { Toast } from "@/components/ui/toast";
import { DocumentCard } from "@/components/archive/document-card";
import { DocumentRow } from "@/components/archive/document-row";
import { DraggableDoc } from "@/components/archive/draggable-doc";
import { FolderTree } from "@/components/archive/folder-tree";
import {
  useArchiveDocuments,
  useClasses,
  useRefile,
} from "@/features/archive/queries";
import {
  filterKey,
  resolveFolder,
  tintForSlug,
} from "@/features/archive/taxonomy";
import type { DocumentSummary } from "@/lib/api/types";

type ViewMode = "gallery" | "list";

export function ArchiveScreen({ folderSegment }: { folderSegment?: string }) {
  const { filter } = resolveFolder(folderSegment);
  const activeKey = filterKey(filter);
  const [view, setView] = useState<ViewMode>("gallery");

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

  const tint =
    filter.kind === "class"
      ? tintForSlug(activeClass?.parent_slug ?? filter.slug)
      : undefined;

  const refile = useRefile();
  const [dragging, setDragging] = useState<DocumentSummary | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  // Drag starts only after an 8px move, so a click still opens the document.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const onDragStart = (e: DragStartEvent) =>
    setDragging((e.active.data.current?.doc as DocumentSummary) ?? null);

  const onDragEnd = (e: DragEndEvent) => {
    setDragging(null);
    const doc = e.active.data.current?.doc as DocumentSummary | undefined;
    const over = e.over?.data.current as { classId?: string; name?: string } | undefined;
    if (!doc || !over?.classId) return;
    // Move: the dropped folder becomes the document's primary (so it shows there —
    // the archive browses by primary) while keeping any other labels (set_primary).
    refile.mutate(
      { documentId: doc.id, classId: over.classId, mode: "set_primary" },
      { onSuccess: () => setToast(`Moved to ${over.name}`) },
    );
  };

  return (
    <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
    <div className="flex min-h-full">
      {/* Persistent folder rail */}
      <aside className="hidden w-64 shrink-0 overflow-y-auto border-r border-border bg-surface xl:block">
        <FolderTree activeKey={activeKey} />
      </aside>

      <section className="min-w-0 flex-1">
        <div className="mx-auto flex w-full max-w-5xl flex-col px-4 py-6 sm:px-8 sm:py-8">
          {/* Narrow-screen folder disclosure */}
          <details className="mb-4 rounded-lg border border-border bg-surface xl:hidden">
            <summary className="flex min-h-11 cursor-pointer items-center px-4 type-subhead text-text-2">
              Folders
            </summary>
            <div className="border-t border-border">
              <FolderTree activeKey={activeKey} />
            </div>
          </details>

          <header className="mb-6 flex items-end justify-between gap-4">
            <div className="flex items-center gap-3">
              {tint ? (
                <span
                  aria-hidden
                  className="mt-1 h-8 w-1.5 shrink-0 rounded-full"
                  style={{ backgroundColor: tint }}
                />
              ) : null}
              <div>
                <p className="eyebrow mb-0.5">Archive</p>
                <h1 className="type-title1 text-text-1">{title}</h1>
              </div>
            </div>
            <SegmentedControl<ViewMode>
              ariaLabel="View mode"
              value={view}
              onChange={setView}
              segments={[
                { value: "gallery", label: "Gallery", icon: <LayoutGrid className="size-4" /> },
                { value: "list", label: "List", icon: <List className="size-4" /> },
              ]}
            />
          </header>

          <DocumentResults filter={filter} view={view} tint={tint} />
        </div>
      </section>

      <DragOverlay dropAnimation={null}>
        {dragging ? (
          <div className="flex items-center gap-2 rounded-lg border border-accent-300 bg-card px-3 py-2 shadow-e3">
            <span aria-hidden className="size-2 rounded-[3px] bg-accent" />
            <span className="truncate type-subhead text-text-1">
              {dragging.title?.trim() || dragging.original_filename}
            </span>
          </div>
        ) : null}
      </DragOverlay>

      <Toast open={!!toast} message={toast ?? ""} onDismiss={() => setToast(null)} />
    </div>
    </DndContext>
  );
}

function DocumentResults({
  filter,
  view,
  tint,
}: {
  filter: ReturnType<typeof resolveFolder>["filter"];
  view: ViewMode;
  tint?: string;
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
    return view === "gallery" ? (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full" />
        ))}
      </div>
    ) : (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
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

  const docs = data.pages.flatMap((p) => p.items);

  if (docs.length === 0) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="Nothing filed here yet"
        description="Upload documents and they'll appear in the folder that fits."
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {view === "gallery" ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {docs.map((doc) => (
            <DraggableDoc key={doc.id} id={doc.id} data={{ doc }}>
              <DocumentCard doc={doc} tint={tint} />
            </DraggableDoc>
          ))}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          {docs.map((doc) => (
            <DraggableDoc key={doc.id} id={doc.id} data={{ doc }}>
              <DocumentRow doc={doc} tint={tint} />
            </DraggableDoc>
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
