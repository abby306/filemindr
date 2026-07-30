/**
 * The folder right-click menu, built once so the grid tiles and the tree pane
 * offer the same verbs in the same order. System folders ship with the taxonomy
 * and are immutable server-side (409), so rename/delete render disabled with a
 * hint rather than failing on click.
 */

import { FolderOpen, PencilLine, SquareArrowOutUpRight, Trash2 } from "lucide-react";

import type { MenuItem } from "@/components/ui/context-menu";
import type { FolderRef } from "@/features/archive/use-folder-commands";

export function folderMenuItems({
  folder,
  onOpen,
  onRename,
  onDelete,
}: {
  folder: FolderRef;
  onOpen: () => void;
  onRename: () => void;
  onDelete: () => void;
}): MenuItem[] {
  const locked = folder.isSystem;
  return [
    { key: "open", label: "Open", icon: FolderOpen, onSelect: onOpen },
    {
      key: "new-tab",
      label: "Open in new tab",
      icon: SquareArrowOutUpRight,
      onSelect: () => window.open(`/archive/${folder.slug}`, "_blank", "noopener"),
    },
    {
      key: "rename",
      label: "Rename",
      icon: PencilLine,
      separatorBefore: true,
      disabled: locked,
      hint: locked ? "System" : undefined,
      onSelect: onRename,
    },
    {
      key: "delete",
      label: "Delete",
      icon: Trash2,
      danger: !locked,
      disabled: locked,
      onSelect: onDelete,
    },
  ];
}
