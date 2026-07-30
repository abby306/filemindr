"use client";

/**
 * DocumentList — Explorer's "List" view: names only, packed into columns so a
 * big folder fits on one screen. Same interaction contract as the table (click
 * selects, double-click opens, right-click menus, drag refiles) minus the
 * columns; the preview rail carries the detail for whatever is selected.
 *
 * Rows flow down each column before wrapping (CSS multi-column), matching
 * Explorer — reading order stays vertical, which is how a name list is scanned.
 */

import { FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import clsx from "clsx";

import { PipelineFill } from "@/components/upload/pipeline-fill";
import type { MenuAnchor } from "@/components/ui/context-menu";
import type { RowClick } from "@/components/archive/document-table";
import { useDocumentDrag } from "@/features/archive/dnd";
import { isProcessing } from "@/features/archive/taxonomy";
import type { DocumentSummary } from "@/lib/api/types";

const displayTitle = (d: DocumentSummary) => d.title?.trim() || d.original_filename;

export function DocumentList({
  docs,
  selectedIds,
  onSelect,
  onRowContextMenu,
  dragIdsFor,
}: {
  docs: DocumentSummary[];
  selectedIds: ReadonlySet<string>;
  onSelect: (click: RowClick) => void;
  onRowContextMenu: (click: RowClick, anchor: MenuAnchor) => void;
  dragIdsFor: (doc: DocumentSummary) => string[];
}) {
  const rowClick = (
    doc: DocumentSummary,
    index: number,
    e: { shiftKey: boolean; metaKey: boolean; ctrlKey: boolean },
  ): RowClick => ({
    doc,
    index,
    ordered: docs,
    additive: e.metaKey || e.ctrlKey,
    range: e.shiftKey,
  });

  return (
    <div
      role="listbox"
      aria-multiselectable
      aria-label="Documents"
      className="rounded-lg border border-border bg-card p-2 [column-gap:0.5rem] sm:columns-2 lg:columns-3"
    >
      {docs.map((doc, i) => (
        <ListRow
          key={doc.id}
          doc={doc}
          selected={selectedIds.has(doc.id)}
          dragIds={dragIdsFor(doc)}
          onClick={(e) => onSelect(rowClick(doc, i, e))}
          onContextMenu={(e) => {
            e.preventDefault();
            onRowContextMenu(rowClick(doc, i, e), { x: e.clientX, y: e.clientY });
          }}
        />
      ))}
    </div>
  );
}

function ListRow({
  doc,
  selected,
  dragIds,
  onClick,
  onContextMenu,
}: {
  doc: DocumentSummary;
  selected: boolean;
  dragIds: string[];
  onClick: (e: React.MouseEvent<HTMLDivElement>) => void;
  onContextMenu: (e: React.MouseEvent<HTMLDivElement>) => void;
}) {
  const router = useRouter();
  const label = displayTitle(doc);
  const { setNodeRef, handleProps, isDragging } = useDocumentDrag(
    doc.id,
    dragIds,
    dragIds.length > 1 ? `${dragIds.length} documents` : label,
  );

  return (
    <div
      ref={setNodeRef}
      {...handleProps}
      role="option"
      tabIndex={0}
      aria-selected={selected}
      title={label}
      onClick={onClick}
      onDoubleClick={() => router.push(`/documents/${doc.id}`)}
      onContextMenu={onContextMenu}
      onKeyDown={(e) => {
        if (e.key === "Enter") router.push(`/documents/${doc.id}`);
      }}
      className={clsx(
        // break-inside: a row must never be split across two columns.
        "flex min-h-9 break-inside-avoid cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 transition-colors duration-[var(--dur-micro)]",
        selected ? "bg-accent-wash text-accent-text" : "text-text-1 hover:bg-surface-2",
        isDragging && "opacity-40",
      )}
    >
      <FileText
        aria-hidden
        className={clsx("size-4 shrink-0", selected ? "text-accent" : "text-text-3")}
        strokeWidth={1.75}
      />
      <span className="truncate type-subhead">{label}</span>
      {isProcessing(doc.status) ? (
        <span className="ml-auto shrink-0">
          <PipelineFill status={doc.status} showTrack={false} />
        </span>
      ) : null}
    </div>
  );
}
