"use client";

/**
 * FolderTree — the desktop navigation pane (Explorer's nav rail). Shows the full
 * taxonomy: a Quick-access group (All / Needs review) and the parent folders,
 * each expandable to its subfolders. The active node is highlighted and its
 * parent auto-expands. Collapses to a slim rail (persisted per browser); hidden
 * below lg where the breadcrumb + folder grid carry navigation.
 */

import { useCallback, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  ChevronRight,
  Folder,
  Inbox,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import clsx from "clsx";

import { useClasses } from "@/features/archive/queries";
import type { FolderFilter } from "@/features/archive/taxonomy";

const COLLAPSE_KEY = "filemindr.archiveTree";
const COLLAPSE_EVENT = "filemindr:archive-tree";

function subscribeCollapse(onChange: () => void) {
  window.addEventListener(COLLAPSE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(COLLAPSE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Tree-pane collapse, persisted per browser (multi-tab safe) — mirrors the
 *  shell's rail hook, which keeps it SSR-safe without a mount effect. */
function useTreeCollapsed(): [boolean, () => void] {
  const collapsed = useSyncExternalStore(
    subscribeCollapse,
    () => window.localStorage.getItem(COLLAPSE_KEY) === "1",
    () => false,
  );
  const toggle = useCallback(() => {
    window.localStorage.setItem(
      COLLAPSE_KEY,
      window.localStorage.getItem(COLLAPSE_KEY) === "1" ? "0" : "1",
    );
    window.dispatchEvent(new Event(COLLAPSE_EVENT));
  }, []);
  return [collapsed, toggle];
}

export function FolderTree({ filter }: { filter: FolderFilter }) {
  const { data } = useClasses();
  const [collapsed, toggle] = useTreeCollapsed();

  const activeSlug = filter.kind === "class" ? filter.slug : null;

  // Which parent (if any) contains the active node, so it starts expanded.
  const activeParentSlug = useMemo(() => {
    if (!data || !activeSlug) return null;
    const cls = data.classes.find((c) => c.slug === activeSlug);
    if (!cls) return null;
    return cls.parent_slug ?? cls.slug;
  }, [data, activeSlug]);

  if (collapsed) {
    return (
      <aside className="hidden shrink-0 lg:block">
        <button
          type="button"
          onClick={toggle}
          aria-label="Show folder tree"
          className="pressable sticky top-20 flex size-9 items-center justify-center rounded-md border border-border bg-surface text-text-2 transition-colors hover:bg-surface-2 hover:text-text-1"
        >
          <PanelLeftOpen aria-hidden className="size-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="hidden w-56 shrink-0 lg:block">
      <div className="sticky top-20 flex max-h-[calc(100dvh-6rem)] flex-col overflow-y-auto rounded-lg border border-border bg-surface p-2">
        <div className="flex items-center justify-between px-1.5 pb-1">
          <span className="eyebrow">Folders</span>
          <button
            type="button"
            onClick={toggle}
            aria-label="Collapse folder tree"
            className="pressable flex size-7 items-center justify-center rounded-md text-text-3 transition-colors hover:bg-surface-2 hover:text-text-1"
          >
            <PanelLeftClose aria-hidden className="size-4" />
          </button>
        </div>

        <TreeLeaf
          href="/archive"
          icon={Layers}
          label="All documents"
          active={filter.kind === "all"}
        />
        <TreeLeaf
          href="/archive/needs-review"
          icon={Inbox}
          label="Needs review"
          active={filter.kind === "needs_review"}
        />

        <div aria-hidden className="my-1.5 h-px bg-border" />

        {data
          ? data.tree.map((node) => (
              <TreeParent
                key={node.cls.id}
                slug={node.cls.slug}
                name={node.cls.name}
                count={node.totalCount}
                childClasses={node.children}
                activeSlug={activeSlug}
                startOpen={activeParentSlug === node.cls.slug}
              />
            ))
          : Array.from({ length: 5 }).map((_, i) => (
              <span key={i} className="animate-skeleton mx-1 my-0.5 h-8 rounded-md" />
            ))}
      </div>
    </aside>
  );
}

function TreeLeaf({
  href,
  icon: Icon,
  label,
  active,
}: {
  href: string;
  icon: typeof Inbox;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "flex items-center gap-2.5 rounded-md px-2 py-1.5 type-subhead transition-colors",
        active
          ? "bg-accent-wash text-accent-text"
          : "text-text-2 hover:bg-surface-2 hover:text-text-1",
      )}
    >
      <Icon aria-hidden className="size-4 shrink-0" strokeWidth={1.75} />
      <span className="truncate">{label}</span>
    </Link>
  );
}

function TreeParent({
  slug,
  name,
  count,
  childClasses,
  activeSlug,
  startOpen,
}: {
  slug: string;
  name: string;
  count: number;
  childClasses: { id: string; slug: string; name: string; document_count: number }[];
  activeSlug: string | null;
  startOpen: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  // Adjust during render (not in an effect): when navigation makes this the
  // active parent, expand it — without clobbering a manual collapse otherwise.
  const [prevStartOpen, setPrevStartOpen] = useState(startOpen);
  if (startOpen !== prevStartOpen) {
    setPrevStartOpen(startOpen);
    if (startOpen) setOpen(true);
  }

  const hasChildren = childClasses.length > 0;
  const active = activeSlug === slug;

  return (
    <div>
      <div
        className={clsx(
          "group flex items-center rounded-md pr-1 transition-colors",
          active ? "bg-accent-wash" : "hover:bg-surface-2",
        )}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? `Collapse ${name}` : `Expand ${name}`}
            aria-expanded={open}
            className="flex size-6 shrink-0 items-center justify-center rounded text-text-3 hover:text-text-1"
          >
            <ChevronRight
              aria-hidden
              className={clsx("size-3.5 transition-transform", open && "rotate-90")}
            />
          </button>
        ) : (
          <span aria-hidden className="w-6 shrink-0" />
        )}
        <Link
          href={`/archive/${slug}`}
          aria-current={active ? "page" : undefined}
          className={clsx(
            "flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-1 type-subhead transition-colors",
            active ? "text-accent-text" : "text-text-1",
          )}
        >
          <Folder aria-hidden className="size-4 shrink-0 text-text-3" strokeWidth={1.75} />
          <span className="truncate">{name}</span>
          {count > 0 ? (
            <span className="ml-auto type-data text-text-3">{count}</span>
          ) : null}
        </Link>
      </div>

      {open && hasChildren ? (
        <div className="ml-3 border-l border-border pl-1.5">
          {childClasses.map((c) => (
            <Link
              key={c.id}
              href={`/archive/${c.slug}`}
              aria-current={activeSlug === c.slug ? "page" : undefined}
              className={clsx(
                "flex items-center gap-2 rounded-md py-1.5 pl-2 pr-1 type-subhead transition-colors",
                activeSlug === c.slug
                  ? "bg-accent-wash text-accent-text"
                  : "text-text-2 hover:bg-surface-2 hover:text-text-1",
              )}
            >
              <span className="truncate">{c.name}</span>
              {c.document_count > 0 ? (
                <span className="ml-auto type-data text-text-3">{c.document_count}</span>
              ) : null}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
