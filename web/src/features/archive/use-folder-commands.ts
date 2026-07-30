"use client";

/**
 * Folder commands shared by every surface that can act on a folder (the folder
 * grid's tiles, the tree pane's nodes, the breadcrumb). Rename and delete were
 * lost when the filter-chip row was retired; this is their one home, so the
 * confirm copy and the post-delete navigation stay identical everywhere.
 */

import { useRouter } from "next/navigation";

import { useDeleteFolder, useRenameFolder } from "@/features/archive/queries";

/** The bit of a class any folder surface has on hand. */
export interface FolderRef {
  id: string;
  slug: string;
  name: string;
  isSystem: boolean;
}

export function useFolderCommands(onToast?: (message: string) => void) {
  const router = useRouter();
  const rename = useRenameFolder();
  const del = useDeleteFolder();

  /** No-ops on an unchanged or empty name, so a blurred input is harmless. */
  const submitRename = (folder: FolderRef, next: string) => {
    const value = next.trim();
    if (!value || value === folder.name) return;
    rename.mutate(
      { classId: folder.id, name: value },
      { onSuccess: () => onToast?.(`Renamed to “${value}”`) },
    );
  };

  /** Deleting a folder only drops the label — the documents stay in the archive. */
  const confirmDelete = (folder: FolderRef, navigateTo?: string) => {
    const ok = window.confirm(
      `Delete the “${folder.name}” folder? The documents inside stay in your archive — they just lose this label.`,
    );
    if (!ok) return;
    del.mutate(folder.id, {
      onSuccess: () => {
        onToast?.(`Deleted “${folder.name}”`);
        if (navigateTo) router.push(navigateTo);
      },
    });
  };

  return { submitRename, confirmDelete };
}
