"use client";

/**
 * MoveMenu — the row's document menu: "Move to folder…" (replacing v1's
 * drag-to-folder — a deliberate trade: dnd fights a sortable table and chips
 * make poor drop targets once the list scrolls; a menu also works on touch)
 * plus "Delete document". Folders come from the full taxonomy (parents +
 * children, empty folders included); moving files with `set_primary`, keeping
 * the document's other labels.
 */

import { useRef, useState } from "react";
import { Check, FolderInput, Trash2 } from "lucide-react";
import clsx from "clsx";

import { useClasses, useRefile } from "@/features/archive/queries";
import { useDeleteDocument } from "@/features/documents/queries";
import type { DocumentSummary } from "@/lib/api/types";
import { useDismiss } from "@/lib/use-dismiss";

export function MoveMenu({
  doc,
  onMoved,
}: {
  doc: DocumentSummary;
  onMoved: (folderName: string) => void;
}) {
  const { data } = useClasses();
  const refile = useRefile();
  const deleteDoc = useDeleteDocument();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(ref, () => setOpen(false), open);

  if (!data) return null;

  const move = (classId: string, name: string) => {
    setOpen(false);
    refile.mutate(
      { documentId: doc.id, classId, mode: "set_primary" },
      { onSuccess: () => onMoved(name) },
    );
  };

  const remove = () => {
    setOpen(false);
    const title = doc.title?.trim() || doc.original_filename;
    if (window.confirm(`Delete “${title}”? This removes the file, its facts, and it can't be undone.`)) {
      deleteDoc.mutate(doc.id);
    }
  };

  return (
    <div ref={ref} className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        aria-label={`Move ${doc.title?.trim() || doc.original_filename} to folder`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "flex size-11 items-center justify-center rounded-md text-text-3 transition-colors hover:bg-surface-2 hover:text-accent-text sm:size-8",
          open && "bg-surface-2 text-accent-text",
        )}
      >
        <FolderInput aria-hidden className="size-4" strokeWidth={1.75} />
      </button>

      {open ? (
        <div className="absolute right-0 top-full z-30 mt-1 max-h-72 w-56 overflow-y-auto rounded-lg border border-border bg-surface p-1 shadow-e2">
          <p className="px-2.5 pb-1 pt-1.5 type-caption uppercase text-text-3">
            Move to folder
          </p>
          {data.fullTree.map((node) => (
            <div key={node.cls.id}>
              <FolderOption
                name={node.cls.name}
                current={doc.primary_class?.slug === node.cls.slug}
                onPick={() => move(node.cls.id, node.cls.name)}
              />
              {node.children.map((child) => (
                <FolderOption
                  key={child.id}
                  name={child.name}
                  nested
                  current={doc.primary_class?.slug === child.slug}
                  onPick={() => move(child.id, child.name)}
                />
              ))}
            </div>
          ))}
          <div className="mt-1 border-t border-border pt-1">
            <button
              type="button"
              onClick={remove}
              className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 type-subhead text-danger transition-colors hover:bg-danger/10"
            >
              <Trash2 aria-hidden className="size-3.5" />
              Delete document
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function FolderOption({
  name,
  nested,
  current,
  onPick,
}: {
  name: string;
  nested?: boolean;
  current: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={current}
      onClick={onPick}
      className={clsx(
        "flex w-full items-center justify-between gap-2 rounded-md py-1.5 pr-2.5 type-subhead transition-colors",
        nested ? "pl-6" : "pl-2.5",
        current ? "text-text-3" : "text-text-1 hover:bg-surface-2",
      )}
    >
      <span className="truncate">{name}</span>
      {current ? <Check aria-hidden className="size-3.5 shrink-0" /> : null}
    </button>
  );
}
