"use client";

/** DraggableDoc — pointer-drag wrapper around a document card/row so it can be
 *  dropped onto a folder to refile it. Click-to-open still works (drag activates
 *  only after an 8px move); the original dims while dragging. */

import { useDraggable } from "@dnd-kit/core";
import clsx from "clsx";

export function DraggableDoc({
  id,
  data,
  children,
}: {
  id: string;
  data: Record<string, unknown>;
  children: React.ReactNode;
}) {
  const { setNodeRef, listeners, isDragging } = useDraggable({ id, data });
  return (
    <div
      ref={setNodeRef}
      {...listeners}
      className={clsx("touch-none", isDragging && "opacity-40")}
    >
      {children}
    </div>
  );
}
