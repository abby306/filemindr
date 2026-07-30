"use client";

/**
 * FolderGrid — the directory's folder view: a grid of folder tiles a user steps
 * into (root shows document categories; a category shows its subfolders). Each
 * tile links to /archive/{slug}; the count is the aggregate for that node. Folder
 * glyphs stay neutral — amber is reserved for provenance, never folders.
 *
 * Right-clicking a tile opens the folder menu (Open / Rename / Delete); rename
 * turns the tile's label into an inline input, Explorer-style.
 */

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Folder, FolderTree, Inbox } from "lucide-react";
import clsx from "clsx";

import { folderMenuItems } from "@/components/archive/folder-menu";
import { ContextMenu, type MenuAnchor } from "@/components/ui/context-menu";
import { useFolderDrop, useIsDragging } from "@/features/archive/dnd";
import { useFolderCommands, type FolderRef } from "@/features/archive/use-folder-commands";
import type { FolderTile } from "@/features/archive/taxonomy";

const riseDelay = (i: number) => ({ animationDelay: `${Math.min(i, 12) * 40}ms` });

const asFolderRef = (t: FolderTile): FolderRef => ({
  id: t.id,
  slug: t.slug,
  name: t.name,
  isSystem: t.isSystem,
});

export function FolderGrid({
  tiles,
  showNeedsReview,
  onToast,
}: {
  tiles: FolderTile[];
  showNeedsReview?: boolean;
  onToast?: (message: string) => void;
}) {
  const router = useRouter();
  const { submitRename, confirmDelete } = useFolderCommands(onToast);
  const [menu, setMenu] = useState<{ anchor: MenuAnchor; tile: FolderTile } | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {showNeedsReview ? (
        <SmartTile
          href="/archive/needs-review"
          icon={Inbox}
          name="Needs review"
          hint="Waiting on you"
        />
      ) : null}
      {tiles.map((t, i) => (
        <FolderTileLink
          key={t.slug}
          tile={t}
          index={i + (showNeedsReview ? 1 : 0)}
          renaming={renamingId === t.id}
          onRenameSubmit={(name) => {
            setRenamingId(null);
            submitRename(asFolderRef(t), name);
          }}
          onRenameCancel={() => setRenamingId(null)}
          onContextMenu={(anchor) => setMenu({ anchor, tile: t })}
        />
      ))}

      <ContextMenu
        anchor={menu?.anchor ?? null}
        onClose={() => setMenu(null)}
        label={menu ? `${menu.tile.name} folder menu` : "Folder menu"}
        items={
          menu
            ? folderMenuItems({
                folder: asFolderRef(menu.tile),
                onOpen: () => router.push(`/archive/${menu.tile.slug}`),
                onRename: () => setRenamingId(menu.tile.id),
                onDelete: () => confirmDelete(asFolderRef(menu.tile)),
              })
            : []
        }
      />
    </div>
  );
}

function FolderTileLink({
  tile,
  index,
  renaming,
  onRenameSubmit,
  onRenameCancel,
  onContextMenu,
}: {
  tile: FolderTile;
  index: number;
  renaming: boolean;
  onRenameSubmit: (name: string) => void;
  onRenameCancel: () => void;
  onContextMenu: (anchor: MenuAnchor) => void;
}) {
  const body = (
    <>
      <Folder
        aria-hidden
        className="size-7 text-text-2 transition-colors group-hover:text-accent"
        strokeWidth={1.5}
      />
      {renaming ? (
        <RenameField name={tile.name} onSubmit={onRenameSubmit} onCancel={onRenameCancel} />
      ) : (
        <span className="mt-3 truncate type-title3 text-text-1">{tile.name}</span>
      )}
      <span className="mt-0.5 flex items-center gap-1.5 type-data text-text-3">
        {tile.count} {tile.count === 1 ? "item" : "items"}
        {tile.hasChildren ? (
          <>
            <span aria-hidden>·</span>
            <FolderTree aria-hidden className="size-3" />
            subfolders
          </>
        ) : null}
      </span>
    </>
  );

  const { setNodeRef, isOver } = useFolderDrop(tile.id, tile.name);
  const dragging = useIsDragging();

  const className = clsx(
    "pressable animate-rise-in group relative flex flex-col rounded-lg border bg-surface p-4 transition-[transform,box-shadow,border-color] duration-[var(--dur-base)] hover:-translate-y-0.5 hover:border-border-strong hover:shadow-e2",
    // A live drag makes every folder a visible target; the one under the
    // pointer commits to the accent.
    isOver
      ? "border-accent bg-accent-wash shadow-e2"
      : dragging
        ? "border-dashed border-accent-300"
        : "border-border",
  );

  // While renaming the tile stops being a link, so typing (and Space) reaches
  // the input instead of navigating.
  if (renaming) {
    return (
      <div data-folder-slug={tile.slug} style={riseDelay(index)} className={className}>
        {body}
      </div>
    );
  }

  return (
    <Link
      ref={setNodeRef}
      href={`/archive/${tile.slug}`}
      data-folder-slug={tile.slug}
      style={riseDelay(index)}
      onContextMenu={(e) => {
        e.preventDefault();
        onContextMenu({ x: e.clientX, y: e.clientY });
      }}
      className={className}
    >
      {body}
    </Link>
  );
}

function RenameField({
  name,
  onSubmit,
  onCancel,
}: {
  name: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(name);
  return (
    <input
      autoFocus
      value={value}
      aria-label={`Rename ${name}`}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === "Enter") onSubmit(value);
        if (e.key === "Escape") onCancel();
      }}
      onBlur={() => onSubmit(value)}
      className="mt-3 w-full rounded-sm border border-accent-300 bg-accent-50 px-1 type-title3 text-text-1 outline-none"
    />
  );
}

function SmartTile({
  href,
  icon: Icon,
  name,
  hint,
}: {
  href: string;
  icon: typeof Inbox;
  name: string;
  hint: string;
}) {
  return (
    <Link
      href={href}
      style={riseDelay(0)}
      className="pressable animate-rise-in group relative flex flex-col rounded-lg border border-accent-300/60 bg-gradient-to-b from-accent-wash to-transparent p-4 transition-[transform,box-shadow] duration-[var(--dur-base)] hover:-translate-y-0.5 hover:shadow-e2"
    >
      <Icon aria-hidden className="size-7 text-accent" strokeWidth={1.5} />
      <span className="mt-3 truncate type-title3 text-text-1">{name}</span>
      <span className="mt-0.5 type-data text-text-3">{hint}</span>
    </Link>
  );
}
