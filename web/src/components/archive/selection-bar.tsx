"use client";

/**
 * SelectionBar — the floating bulk-action bar for a multi-selection (Explorer's
 * command bar, docked). Appears once two or more documents are selected so a
 * single selection stays quiet (the preview rail is its feedback); "Move to
 * folder" reuses the document menu's folder list, anchored to the button.
 */

import { useState } from "react";
import { FolderInput, Trash2, X } from "lucide-react";

import { ContextMenu, type MenuAnchor, type MenuItem } from "@/components/ui/context-menu";

export function SelectionBar({
  count,
  moveOptions,
  onDelete,
  onClear,
  busy,
}: {
  count: number;
  /** Folder targets, already wired to the bulk move (see documentMenuItems). */
  moveOptions: MenuItem[];
  onDelete: () => void;
  onClear: () => void;
  busy?: boolean;
}) {
  const [anchor, setAnchor] = useState<MenuAnchor | null>(null);

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-40 flex justify-center px-4 lg:bottom-8">
      {/* rise-in, not toast-in: the toast keyframes bake in translateX(-50%)
          for a `left-1/2` toast, which would shove a flex-centered bar left. */}
      <div className="animate-rise-in pointer-events-auto flex items-center gap-1.5 rounded-full border border-border bg-surface py-1.5 pl-4 pr-1.5 shadow-e3">
        <span className="type-subhead text-text-1">
          {count} selected
        </span>
        <span aria-hidden className="mx-1 h-4 w-px bg-border" />
        <button
          type="button"
          disabled={busy}
          onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            setAnchor({ x: r.left, y: r.top - 4 });
          }}
          className="pressable flex min-h-9 items-center gap-2 rounded-full px-3 type-subhead text-text-1 transition-colors hover:bg-surface-2 disabled:opacity-60"
        >
          <FolderInput aria-hidden className="size-4" strokeWidth={1.75} />
          Move to folder
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onDelete}
          className="pressable flex min-h-9 items-center gap-2 rounded-full px-3 type-subhead text-danger transition-colors hover:bg-danger/10 disabled:opacity-60"
        >
          <Trash2 aria-hidden className="size-4" strokeWidth={1.75} />
          Delete
        </button>
        <button
          type="button"
          aria-label="Clear selection"
          onClick={onClear}
          className="pressable flex size-9 items-center justify-center rounded-full text-text-3 transition-colors hover:bg-surface-2 hover:text-text-1"
        >
          <X aria-hidden className="size-4" strokeWidth={1.75} />
        </button>
      </div>

      <ContextMenu
        anchor={anchor}
        items={moveOptions}
        onClose={() => setAnchor(null)}
        label="Move selection to folder"
      />
    </div>
  );
}
