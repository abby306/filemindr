/**
 * The document right-click menu, shared by a single row and a multi-selection
 * (the selection bar reuses the same verbs). With more than one document
 * selected the per-document verbs — Open, Quick Look — drop out and the rest
 * speak in counts, so the menu always states exactly what it will act on.
 *
 * "Move to folder" lists the full taxonomy (parents ▸ children, empty folders
 * included) and files with `set_primary`, keeping the documents' other labels.
 */

import { Eye, FolderInput, SquareArrowOutUpRight, Trash2 } from "lucide-react";

import type { MenuItem } from "@/components/ui/context-menu";
import type { FolderNode } from "@/features/archive/taxonomy";

/** The folder targets, flat with subfolders indented — also used on their own
 *  by the selection bar's "Move to folder" button. */
export function folderMoveOptions({
  folders,
  currentSlug,
  onMove,
}: {
  folders: FolderNode[];
  currentSlug?: string | null;
  onMove: (classId: string, folderName: string) => void;
}): MenuItem[] {
  return folders.flatMap((node) => [
    {
      key: node.cls.id,
      label: node.cls.name,
      checked: currentSlug === node.cls.slug,
      disabled: currentSlug === node.cls.slug,
      onSelect: () => onMove(node.cls.id, node.cls.name),
    },
    ...node.children.map((child) => ({
      key: child.id,
      label: child.name,
      indent: true,
      checked: currentSlug === child.slug,
      disabled: currentSlug === child.slug,
      onSelect: () => onMove(child.id, child.name),
    })),
  ]);
}

export function documentMenuItems({
  count,
  folders,
  currentSlug,
  onOpen,
  onQuickLook,
  onMove,
  onDelete,
}: {
  /** How many documents the menu acts on (1 for a plain row). */
  count: number;
  folders: FolderNode[];
  /** The selection's folder, ticked in the move list when they all share one. */
  currentSlug?: string | null;
  onOpen: () => void;
  onQuickLook: () => void;
  onMove: (classId: string, folderName: string) => void;
  onDelete: () => void;
}): MenuItem[] {
  const single = count === 1;
  const noun = single ? "document" : `${count} documents`;

  const items: MenuItem[] = [];
  if (single) {
    items.push(
      { key: "open", label: "Open", icon: SquareArrowOutUpRight, onSelect: onOpen },
      { key: "peek", label: "Quick Look", icon: Eye, hint: "Space", onSelect: onQuickLook },
    );
  }
  items.push({
    key: "move",
    label: single ? "Move to folder" : `Move ${count} to folder`,
    icon: FolderInput,
    separatorBefore: single,
    submenu: folderMoveOptions({ folders, currentSlug, onMove }),
  });
  items.push({
    key: "delete",
    label: single ? "Delete document" : `Delete ${noun}`,
    icon: Trash2,
    danger: true,
    separatorBefore: true,
    onSelect: onDelete,
  });
  return items;
}
