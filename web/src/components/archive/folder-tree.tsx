"use client";

/**
 * FolderTree — the desktop navigation pane (Explorer's nav rail). Shows the full
 * taxonomy: a Quick-access group (All / Needs review) and the parent folders,
 * each expandable to its subfolders. The active node is highlighted and its
 * parent auto-expands. Collapses to a slim rail (persisted per browser); hidden
 * below lg where the breadcrumb + folder grid carry navigation. Every folder
 * node carries the same right-click menu as a folder tile (Open / Rename /
 * Delete), with rename editing the label in place.
 */

import { useCallback, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ChevronRight,
  Folder,
  Inbox,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import clsx from "clsx";

import { folderMenuItems } from "@/components/archive/folder-menu";
import { ContextMenu, type MenuAnchor } from "@/components/ui/context-menu";
import { useClasses } from "@/features/archive/queries";
import { useFolderCommands, type FolderRef } from "@/features/archive/use-folder-commands";
import type { FolderFilter } from "@/features/archive/taxonomy";
import type { ClassInfo } from "@/lib/api/types";

const COLLAPSE_KEY = "filemindr.archiveTree";
const COLLAPSE_EVENT = "filemindr:archive-tree";

const asFolderRef = (cls: ClassInfo): FolderRef => ({
  id: cls.id,
  slug: cls.slug,
  name: cls.name,
  isSystem: cls.is_system,
});

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

export function FolderTree({
  filter,
  onToast,
}: {
  filter: FolderFilter;
  onToast?: (message: string) => void;
}) {
  const { data } = useClasses();
  const router = useRouter();
  const [collapsed, toggle] = useTreeCollapsed();
  const { submitRename, confirmDelete } = useFolderCommands(onToast);
  const [menu, setMenu] = useState<{ anchor: MenuAnchor; cls: ClassInfo } | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);

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

  const nodeProps = {
    activeSlug,
    renamingId,
    onRenameSubmit: (cls: ClassInfo, name: string) => {
      setRenamingId(null);
      submitRename(asFolderRef(cls), name);
    },
    onRenameCancel: () => setRenamingId(null),
    onContextMenu: (anchor: MenuAnchor, cls: ClassInfo) => setMenu({ anchor, cls }),
  };

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
                cls={node.cls}
                count={node.totalCount}
                childClasses={node.children}
                startOpen={activeParentSlug === node.cls.slug}
                {...nodeProps}
              />
            ))
          : Array.from({ length: 5 }).map((_, i) => (
              <span key={i} className="animate-skeleton mx-1 my-0.5 h-8 rounded-md" />
            ))}
      </div>

      <ContextMenu
        anchor={menu?.anchor ?? null}
        onClose={() => setMenu(null)}
        label={menu ? `${menu.cls.name} folder menu` : "Folder menu"}
        items={
          menu
            ? folderMenuItems({
                folder: asFolderRef(menu.cls),
                onOpen: () => router.push(`/archive/${menu.cls.slug}`),
                onRename: () => setRenamingId(menu.cls.id),
                onDelete: () =>
                  confirmDelete(
                    asFolderRef(menu.cls),
                    activeSlug === menu.cls.slug ? "/archive" : undefined,
                  ),
              })
            : []
        }
      />
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

interface NodeHandlers {
  activeSlug: string | null;
  renamingId: string | null;
  onRenameSubmit: (cls: ClassInfo, name: string) => void;
  onRenameCancel: () => void;
  onContextMenu: (anchor: MenuAnchor, cls: ClassInfo) => void;
}

function TreeParent({
  cls,
  count,
  childClasses,
  startOpen,
  ...handlers
}: {
  cls: ClassInfo;
  count: number;
  childClasses: ClassInfo[];
  startOpen: boolean;
} & NodeHandlers) {
  const { activeSlug, renamingId, onRenameSubmit, onRenameCancel, onContextMenu } = handlers;
  const [open, setOpen] = useState(startOpen);
  // Adjust during render (not in an effect): when navigation makes this the
  // active parent, expand it — without clobbering a manual collapse otherwise.
  const [prevStartOpen, setPrevStartOpen] = useState(startOpen);
  if (startOpen !== prevStartOpen) {
    setPrevStartOpen(startOpen);
    if (startOpen) setOpen(true);
  }

  const hasChildren = childClasses.length > 0;
  const active = activeSlug === cls.slug;
  const renaming = renamingId === cls.id;

  return (
    <div>
      <div
        onContextMenu={(e) => {
          e.preventDefault();
          onContextMenu({ x: e.clientX, y: e.clientY }, cls);
        }}
        className={clsx(
          "group flex items-center rounded-md pr-1 transition-colors",
          active ? "bg-accent-wash" : "hover:bg-surface-2",
        )}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? `Collapse ${cls.name}` : `Expand ${cls.name}`}
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
        {renaming ? (
          <span className="flex min-w-0 flex-1 items-center gap-2 py-1 pr-1">
            <Folder aria-hidden className="size-4 shrink-0 text-text-3" strokeWidth={1.75} />
            <RenameField
              name={cls.name}
              onSubmit={(value) => onRenameSubmit(cls, value)}
              onCancel={onRenameCancel}
            />
          </span>
        ) : (
          <Link
            href={`/archive/${cls.slug}`}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-1 type-subhead transition-colors",
              active ? "text-accent-text" : "text-text-1",
            )}
          >
            <Folder aria-hidden className="size-4 shrink-0 text-text-3" strokeWidth={1.75} />
            <span className="truncate">{cls.name}</span>
            {count > 0 ? (
              <span className="ml-auto type-data text-text-3">{count}</span>
            ) : null}
          </Link>
        )}
      </div>

      {open && hasChildren ? (
        <div className="ml-3 border-l border-border pl-1.5">
          {childClasses.map((c) => (
            <div
              key={c.id}
              onContextMenu={(e) => {
                e.preventDefault();
                onContextMenu({ x: e.clientX, y: e.clientY }, c);
              }}
            >
              {renamingId === c.id ? (
                <span className="flex items-center py-1 pl-2 pr-1">
                  <RenameField
                    name={c.name}
                    onSubmit={(value) => onRenameSubmit(c, value)}
                    onCancel={onRenameCancel}
                  />
                </span>
              ) : (
                <Link
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
              )}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** In-place folder label editing — Enter commits, Escape and blur-with-no-change
 *  are no-ops (the command hook ignores an unchanged name). */
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
      className="min-w-0 flex-1 rounded-sm border border-accent-300 bg-accent-50 px-1 type-subhead text-text-1 outline-none"
    />
  );
}
