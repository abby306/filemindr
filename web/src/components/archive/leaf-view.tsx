"use client";

/**
 * LeafView — a folder's documents (the directory's leaf) and the owner of
 * Explorer's selection model. Single-click selects (highlight + a preview rail
 * on wide screens), ⌘/Ctrl-click toggles, Shift-click extends a range in the
 * table's visual order, ⌘A selects all, Escape clears; double-click / title /
 * the eye button open, Space Quick Looks a single selection. Right-clicking a
 * row opens the document menu — acting on the whole selection when the row is
 * part of it — and two or more selected raises the bulk SelectionBar.
 * Gallery view stays click-to-open (no selection).
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { DocumentCard } from "@/components/archive/document-card";
import { documentMenuItems, folderMoveOptions } from "@/components/archive/document-menu";
import { DocumentPreview } from "@/components/archive/document-preview";
import { DocumentTable, type RowClick } from "@/components/archive/document-table";
import { QuickLook } from "@/components/archive/quick-look";
import { SelectionBar } from "@/components/archive/selection-bar";
import { ContextMenu, type MenuAnchor } from "@/components/ui/context-menu";
import {
  useBulkDeleteDocuments,
  useBulkRefile,
  useClasses,
} from "@/features/archive/queries";
import type { DocumentSummary } from "@/lib/api/types";

const titleOf = (d: DocumentSummary) => d.title?.trim() || d.original_filename;

/** Does the whole selection sit in one folder? (Ticks it in the move list.) */
function sharedFolderSlug(docs: DocumentSummary[]): string | null {
  const first = docs[0]?.primary_class?.slug ?? null;
  return docs.every((d) => (d.primary_class?.slug ?? null) === first) ? first : null;
}

export function LeafView({
  docs,
  view,
  onToast,
  hasNextPage,
  fetchNextPage,
  isFetchingNextPage,
}: {
  docs: DocumentSummary[];
  view: "table" | "gallery";
  onToast: (message: string) => void;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  isFetchingNextPage: boolean;
}) {
  const router = useRouter();
  const { data: classData } = useClasses();
  const bulkRefile = useBulkRefile();
  const bulkDelete = useBulkDeleteDocuments();

  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());
  const [anchorId, setAnchorId] = useState<string | null>(null);
  const [quickLook, setQuickLook] = useState<DocumentSummary | null>(null);
  const [menu, setMenu] = useState<{ anchor: MenuAnchor; ids: string[] } | null>(null);

  // A document can vanish under the selection (deleted, refiled elsewhere, a
  // page reload) — derive from the live list rather than trusting stale ids.
  const selected = useMemo(
    () => docs.filter((d) => selectedIds.has(d.id)),
    [docs, selectedIds],
  );
  const single = selected.length === 1 ? selected[0] : null;

  const clear = () => {
    setSelectedIds(new Set());
    setAnchorId(null);
  };

  /** Resolve a click against the current selection (plain / ⌘ / shift). */
  const select = ({ doc, ordered, additive, range }: RowClick) => {
    if (range && anchorId) {
      const from = ordered.findIndex((d) => d.id === anchorId);
      const to = ordered.findIndex((d) => d.id === doc.id);
      if (from !== -1 && to !== -1) {
        const [lo, hi] = from < to ? [from, to] : [to, from];
        setSelectedIds(new Set(ordered.slice(lo, hi + 1).map((d) => d.id)));
        return;
      }
    }
    if (additive) {
      const next = new Set(selectedIds);
      if (next.has(doc.id)) next.delete(doc.id);
      else next.add(doc.id);
      setSelectedIds(next);
      setAnchorId(doc.id);
      return;
    }
    setSelectedIds(new Set([doc.id]));
    setAnchorId(doc.id);
  };

  const openMenu = (click: RowClick, anchor: MenuAnchor) => {
    // Right-clicking outside the selection reselects that one row first, so the
    // menu never acts on documents the user can't see highlighted.
    const inSelection = selectedIds.has(click.doc.id);
    if (!inSelection) {
      setSelectedIds(new Set([click.doc.id]));
      setAnchorId(click.doc.id);
    }
    const ids = inSelection ? [...selectedIds] : [click.doc.id];
    setMenu({ anchor, ids });
  };

  const moveMany = (ids: string[], classId: string, folderName: string) => {
    bulkRefile.mutate(
      { documentIds: ids, classId },
      {
        onSuccess: () => {
          onToast(
            ids.length === 1
              ? `Moved to ${folderName}`
              : `Moved ${ids.length} documents to ${folderName}`,
          );
          clear();
        },
      },
    );
  };

  const deleteMany = (ids: string[]) => {
    const what =
      ids.length === 1
        ? `“${titleOf(docs.find((d) => d.id === ids[0]) ?? docs[0])}”`
        : `${ids.length} documents`;
    const ok = window.confirm(
      `Delete ${what}? This removes the ${ids.length === 1 ? "file" : "files"}, their facts, and it can't be undone.`,
    );
    if (!ok) return;
    bulkDelete.mutate(ids, {
      onSuccess: () => {
        onToast(ids.length === 1 ? "Document deleted" : `${ids.length} documents deleted`);
        clear();
      },
    });
  };

  // Keyboard: Space peeks a single selection, Escape clears, ⌘A selects all.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      const typing =
        el &&
        (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (typing) return;

      if (e.key === "Escape") {
        clear();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a" && view === "table") {
        e.preventDefault();
        setSelectedIds(new Set(docs.map((d) => d.id)));
        return;
      }
      if (e.key === " " && single) {
        e.preventDefault();
        setQuickLook(single);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [docs, single, view]);

  const menuItems = menu
    ? documentMenuItems({
        count: menu.ids.length,
        folders: classData?.fullTree ?? [],
        currentSlug: sharedFolderSlug(docs.filter((d) => menu.ids.includes(d.id))),
        onOpen: () => router.push(`/documents/${menu.ids[0]}`),
        onQuickLook: () => {
          const doc = docs.find((d) => d.id === menu.ids[0]);
          if (doc) setQuickLook(doc);
        },
        onMove: (classId, name) => moveMany(menu.ids, classId, name),
        onDelete: () => deleteMany(menu.ids),
      })
    : [];

  const busy = bulkRefile.isPending || bulkDelete.isPending;

  return (
    <div className="flex flex-col gap-6">
      <div className={single && view === "table" ? "xl:grid xl:grid-cols-[1fr_290px] xl:gap-6" : ""}>
        <div className="min-w-0">
          {view === "table" ? (
            <DocumentTable
              docs={docs}
              onMoved={(name) => onToast(`Moved to ${name}`)}
              selectedIds={selectedIds}
              onSelect={select}
              onQuickLook={(d) => setQuickLook(d)}
              onRowContextMenu={openMenu}
              dragIdsFor={(doc) =>
                selectedIds.has(doc.id) && selectedIds.size > 1
                  ? [...selectedIds]
                  : [doc.id]
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {docs.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} />
              ))}
            </div>
          )}
        </div>

        {single && view === "table" ? (
          <aside className="hidden xl:block">
            <div className="sticky top-20 max-h-[calc(100dvh-6rem)] overflow-y-auto rounded-lg border border-border bg-surface p-4">
              <DocumentPreview doc={single} size="pane" />
            </div>
          </aside>
        ) : null}
      </div>

      {hasNextPage ? (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
            className="pressable min-h-11 rounded-md border border-border bg-surface px-5 type-subhead text-text-1 transition-colors hover:bg-surface-2 disabled:opacity-60"
          >
            {isFetchingNextPage ? "Loading…" : "Load more"}
          </button>
        </div>
      ) : null}

      <QuickLook doc={quickLook} onClose={() => setQuickLook(null)} />

      <ContextMenu
        anchor={menu?.anchor ?? null}
        items={menuItems}
        onClose={() => setMenu(null)}
        label="Document menu"
      />

      {selected.length > 1 ? (
        <SelectionBar
          count={selected.length}
          busy={busy}
          moveOptions={folderMoveOptions({
            folders: classData?.fullTree ?? [],
            currentSlug: sharedFolderSlug(selected),
            onMove: (classId, name) =>
              moveMany(
                selected.map((d) => d.id),
                classId,
                name,
              ),
          })}
          onDelete={() => deleteMany(selected.map((d) => d.id))}
          onClear={clear}
        />
      ) : null}
    </div>
  );
}
