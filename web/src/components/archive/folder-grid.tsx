"use client";

/**
 * FolderGrid — the directory's folder view: a grid of folder tiles a user steps
 * into (root shows document categories; a category shows its subfolders). Each
 * tile links to /archive/{slug}; the count is the aggregate for that node. Folder
 * glyphs stay neutral — amber is reserved for provenance, never folders.
 */

import Link from "next/link";
import { Folder, FolderTree, Inbox } from "lucide-react";

import type { FolderTile } from "@/features/archive/taxonomy";

const riseDelay = (i: number) => ({ animationDelay: `${Math.min(i, 12) * 40}ms` });

export function FolderGrid({
  tiles,
  showNeedsReview,
}: {
  tiles: FolderTile[];
  showNeedsReview?: boolean;
}) {
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
        <FolderTileLink key={t.slug} tile={t} index={i + (showNeedsReview ? 1 : 0)} />
      ))}
    </div>
  );
}

function FolderTileLink({ tile, index }: { tile: FolderTile; index: number }) {
  return (
    <Link
      href={`/archive/${tile.slug}`}
      data-folder-slug={tile.slug}
      style={riseDelay(index)}
      className="pressable animate-rise-in group relative flex flex-col rounded-lg border border-border bg-surface p-4 transition-[transform,box-shadow,border-color] duration-[var(--dur-base)] hover:-translate-y-0.5 hover:border-border-strong hover:shadow-e2"
    >
      <Folder
        aria-hidden
        className="size-7 text-text-2 transition-colors group-hover:text-accent"
        strokeWidth={1.5}
      />
      <span className="mt-3 truncate type-title3 text-text-1">{tile.name}</span>
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
    </Link>
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
