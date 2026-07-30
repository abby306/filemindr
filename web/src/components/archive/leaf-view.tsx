"use client";

/**
 * LeafView — a folder's documents (the directory's leaf). Explorer-style
 * selection: single-click a row to select it (highlight + a preview rail on
 * wide screens), double-click / title / the eye button to open, Space to Quick
 * Look the selection. The preview rail shows on xl so it doesn't crowd the tree
 * pane on narrower desktops. Gallery view stays click-to-open (no selection).
 */

import { useEffect, useState } from "react";

import { DocumentCard } from "@/components/archive/document-card";
import { DocumentPreview } from "@/components/archive/document-preview";
import { DocumentTable } from "@/components/archive/document-table";
import { QuickLook } from "@/components/archive/quick-look";
import type { DocumentSummary } from "@/lib/api/types";

export function LeafView({
  docs,
  view,
  onMoved,
  hasNextPage,
  fetchNextPage,
  isFetchingNextPage,
}: {
  docs: DocumentSummary[];
  view: "table" | "gallery";
  onMoved: (folderName: string) => void;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  isFetchingNextPage: boolean;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [quickLook, setQuickLook] = useState<DocumentSummary | null>(null);
  const selected = docs.find((d) => d.id === selectedId) ?? null;

  // Space peeks the selected document (unless typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== " " || !selected) return;
      const el = document.activeElement as HTMLElement | null;
      if (
        el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      setQuickLook(selected);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected]);

  return (
    <div className="flex flex-col gap-6">
      <div className={selected && view === "table" ? "xl:grid xl:grid-cols-[1fr_290px] xl:gap-6" : ""}>
        <div className="min-w-0">
          {view === "table" ? (
            <DocumentTable
              docs={docs}
              onMoved={onMoved}
              selectedId={selectedId}
              onSelect={(d) => setSelectedId(d.id)}
              onQuickLook={(d) => setQuickLook(d)}
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {docs.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} />
              ))}
            </div>
          )}
        </div>

        {selected && view === "table" ? (
          <aside className="hidden xl:block">
            <div className="sticky top-20 max-h-[calc(100dvh-6rem)] overflow-y-auto rounded-lg border border-border bg-surface p-4">
              <DocumentPreview doc={selected} size="pane" />
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
    </div>
  );
}
