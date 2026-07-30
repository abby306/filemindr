"use client";

/**
 * Drag-to-refile — the directory's other way to move a document: pick rows up
 * and drop them on a folder (a grid tile, a tree node, or a breadcrumb). Filing
 * uses `set_primary`, exactly like the "Move to folder" menu, so a drag and a
 * menu pick are the same operation with different ergonomics.
 *
 * The DndContext lives above both panes (ArchiveScreen) because a row in the
 * document table drops onto a tree node that is its sibling in the layout. Drag
 * data travels on the draggable (`{ ids, label }`) and the droppable
 * (`{ classId, name }`), so this module owns the whole contract:
 *
 *   <ArchiveDnd onToast={…}>…</ArchiveDnd>   // once, around the screen
 *   const drag = useDocumentDrag(id, ids, label);   // <tr {...drag.handleProps}>
 *   const drop = useFolderDrop(classId, name);      // <div ref={drop.setNodeRef}>
 *
 * A pointer must travel 6px before a drag starts, so a plain click still
 * selects and a double-click still opens.
 */

import { createContext, use, useState, type ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { FileText } from "lucide-react";

import { useBulkRefile } from "@/features/archive/queries";

interface DragPayload {
  ids: string[];
  label: string;
}

interface DropPayload {
  classId: string;
  name: string;
}

/** True while a document drag is in flight — folders light up as targets. */
const DraggingContext = createContext(false);

export function useIsDragging(): boolean {
  return use(DraggingContext);
}

export function ArchiveDnd({
  children,
  onToast,
}: {
  children: ReactNode;
  onToast: (message: string) => void;
}) {
  const refile = useBulkRefile();
  const [dragging, setDragging] = useState<DragPayload | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const onDragStart = (e: DragStartEvent) => {
    setDragging((e.active.data.current as DragPayload | undefined) ?? null);
  };

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setDragging(null);
    const from = active.data.current as DragPayload | undefined;
    const to = over?.data.current as DropPayload | undefined;
    // The "Archive" root crumb registers as a droppable with no class behind
    // it — nothing to file into, so a drop there is a no-op.
    if (!from || !to?.classId || from.ids.length === 0) return;
    refile.mutate(
      { documentIds: from.ids, classId: to.classId },
      {
        onSuccess: () =>
          onToast(
            from.ids.length === 1
              ? `Moved to ${to.name}`
              : `Moved ${from.ids.length} documents to ${to.name}`,
          ),
      },
    );
  };

  return (
    <DndContext
      sensors={sensors}
      // pointerWithin, not the default rect intersection: the ghost keeps the
      // grab offset, so a wide row's rect can overlap a folder the pointer
      // isn't near. What's under the pointer is what the user means.
      collisionDetection={pointerWithin}
      onDragStart={onDragStart}
      onDragCancel={() => setDragging(null)}
      onDragEnd={onDragEnd}
    >
      <DraggingContext value={dragging !== null}>{children}</DraggingContext>
      {/* fit-content: the overlay otherwise inherits the dragged row's full
          width, and a 900px-wide ghost hides the folder it's aimed at. */}
      <DragOverlay dropAnimation={null} style={{ width: "fit-content", height: "fit-content" }}>
        {dragging ? (
          <div className="flex w-fit items-center gap-2 rounded-md border border-accent-300 bg-surface px-2.5 py-1.5 shadow-e3">
            <FileText aria-hidden className="size-4 text-accent" strokeWidth={1.75} />
            <span className="max-w-56 truncate type-subhead text-text-1">
              {dragging.label}
            </span>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

/**
 * Make a document row draggable. `ids` is what actually moves — the whole
 * selection when this row is part of it, otherwise just this row.
 */
export function useDocumentDrag(rowId: string, ids: string[], label: string) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `doc:${rowId}`,
    data: { ids, label } satisfies DragPayload,
  });
  return {
    setNodeRef,
    isDragging,
    handleProps: { ...attributes, ...listeners },
  };
}

/** Make a folder a drop target for documents. */
export function useFolderDrop(classId: string, name: string) {
  const { setNodeRef, isOver } = useDroppable({
    id: `folder:${classId}`,
    data: { classId, name } satisfies DropPayload,
  });
  return { setNodeRef, isOver };
}
