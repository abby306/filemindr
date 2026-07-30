"use client";

/**
 * BreadcrumbBar — the directory address bar: Back / Up controls then the
 * ancestor trail (Archive ▸ Financial ▸ Invoices). Every segment is a link; the
 * last is the current node. Slugs are unique per account, so each crumb is a
 * plain /archive/{slug} link and "up" is derived from the class tree.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ChevronRight, CornerLeftUp } from "lucide-react";
import clsx from "clsx";

import { useFolderDrop } from "@/features/archive/dnd";
import type { Crumb } from "@/features/archive/taxonomy";

export function BreadcrumbBar({
  crumbs,
  upHref,
  canGoUp,
}: {
  crumbs: Crumb[];
  upHref: string;
  canGoUp: boolean;
}) {
  const router = useRouter();

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          aria-label="Back"
          onClick={() => router.back()}
          className="pressable flex size-8 items-center justify-center rounded-md text-text-2 transition-colors hover:bg-surface-2 hover:text-text-1"
        >
          <ArrowLeft aria-hidden className="size-4" />
        </button>
        {canGoUp ? (
          <Link
            href={upHref}
            aria-label="Up one level"
            className="pressable flex size-8 items-center justify-center rounded-md text-text-2 transition-colors hover:bg-surface-2 hover:text-text-1"
          >
            <CornerLeftUp aria-hidden className="size-4" />
          </Link>
        ) : (
          <span
            aria-hidden
            className="flex size-8 items-center justify-center rounded-md text-text-3 opacity-40"
          >
            <CornerLeftUp className="size-4" />
          </span>
        )}
      </div>

      <nav
        aria-label="Breadcrumb"
        className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto rounded-md border border-border bg-surface-2 px-2 py-1"
      >
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <span key={c.href + i} className="flex shrink-0 items-center gap-0.5">
              {i > 0 ? (
                <ChevronRight aria-hidden className="size-3.5 shrink-0 text-text-3" />
              ) : null}
              {last ? (
                <span
                  aria-current="page"
                  className="rounded-sm px-1.5 py-0.5 type-subhead font-semibold text-text-1"
                >
                  {c.label}
                </span>
              ) : (
                <CrumbLink crumb={c} />
              )}
            </span>
          );
        })}
      </nav>
    </div>
  );
}

/** An ancestor crumb. Folder crumbs double as drop targets, so dragging a
 *  document onto "Financial" files it one level up — the address bar's version
 *  of Explorer's drag-to-parent. */
function CrumbLink({ crumb }: { crumb: Crumb }) {
  const { setNodeRef, isOver } = useFolderDrop(crumb.id ?? "", crumb.label);
  return (
    <Link
      ref={crumb.id ? setNodeRef : undefined}
      href={crumb.href}
      className={clsx(
        "rounded-sm px-1.5 py-0.5 type-subhead transition-colors",
        isOver && crumb.id
          ? "bg-accent-wash text-accent-text ring-1 ring-accent"
          : "text-text-2 hover:bg-surface hover:text-text-1",
      )}
    >
      {crumb.label}
    </Link>
  );
}
