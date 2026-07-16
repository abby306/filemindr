"use client";

/**
 * FolderTree — the Finder-style archive rail. Smart folders (mapped to real API
 * filters) pinned on top, then the class taxonomy as parent folders with
 * expandable subclass children. Active state comes from the selected filter;
 * parents auto-expand when they contain the active child.
 *
 * Class folders are drag-and-drop targets (drop a document to file it there) and
 * custom folders can be created/deleted inline; system folders show a lock.
 */

import { useState } from "react";
import Link from "next/link";
import { useDroppable } from "@dnd-kit/core";
import { Check, ChevronRight, Lock, Pencil, Plus, Trash2, X } from "lucide-react";
import clsx from "clsx";

import { Skeleton } from "@/components/ui/skeleton";
import {
  useClasses,
  useCreateFolder,
  useDeleteFolder,
  useRenameFolder,
} from "@/features/archive/queries";
import {
  CLASS_FOLDER_ICON,
  SMART_FOLDERS,
  filterKey,
  folderHref,
  tintForSlug,
  type FolderFilter,
  type FolderNode,
} from "@/features/archive/taxonomy";
import type { ClassInfo } from "@/lib/api/types";

interface FolderTreeProps {
  activeKey: string;
  onNavigate?: () => void;
}

export function FolderTree({ activeKey, onNavigate }: FolderTreeProps) {
  const { data, isPending, isError } = useClasses();
  const del = useDeleteFolder();

  const onDelete = (cls: ClassInfo) => {
    if (window.confirm(`Delete the "${cls.name}" folder? Documents keep their other labels.`)) {
      del.mutate(cls.id);
    }
  };

  return (
    <nav aria-label="Archive folders" className="flex flex-col gap-1 p-3">
      <div className="flex flex-col gap-0.5">
        {SMART_FOLDERS.map((f) => (
          <FolderLink
            key={f.segment ?? "all"}
            href={folderHref(f.filter)}
            label={f.label}
            active={activeKey === filterKey(f.filter)}
            onNavigate={onNavigate}
            icon={<f.icon aria-hidden className="size-[18px] shrink-0" strokeWidth={1.75} />}
          />
        ))}
      </div>

      <div className="flex items-center justify-between px-3 pb-1 pt-3">
        <p className="type-caption uppercase text-text-3">Folders</p>
        <NewFolder />
      </div>

      {isPending ? (
        <div className="flex flex-col gap-1.5 px-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : isError ? (
        <p className="px-3 type-callout text-text-3">Couldn&apos;t load folders.</p>
      ) : (
        <div className="flex flex-col gap-0.5">
          {data.tree.map((node) => (
            <ParentFolder
              key={node.cls.id}
              node={node}
              activeKey={activeKey}
              onNavigate={onNavigate}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </nav>
  );
}

function ParentFolder({
  node,
  activeKey,
  onNavigate,
  onDelete,
}: {
  node: FolderNode;
  activeKey: string;
  onNavigate?: () => void;
  onDelete: (cls: ClassInfo) => void;
}) {
  const containsActive = node.children.some((c) => activeKey === `class:${c.slug}`);
  const [override, setOverride] = useState<boolean | null>(null);
  const expanded = override ?? containsActive;
  const hasChildren = node.children.length > 0;
  const filter: FolderFilter = { kind: "class", slug: node.cls.slug };

  return (
    <div>
      <div className="flex items-center">
        {hasChildren ? (
          <button
            type="button"
            aria-label={expanded ? "Collapse" : "Expand"}
            aria-expanded={expanded}
            onClick={() => setOverride(!expanded)}
            className="flex size-6 shrink-0 items-center justify-center rounded-sm text-text-3 hover:text-text-1"
          >
            <ChevronRight
              aria-hidden
              className={clsx(
                "size-4 transition-transform duration-[var(--dur-micro)]",
                expanded && "rotate-90",
              )}
            />
          </button>
        ) : (
          <span className="size-6 shrink-0" />
        )}
        <DropFolder cls={node.cls} onDelete={onDelete}>
          <FolderLink
            href={folderHref(filter)}
            label={node.cls.name}
            count={node.totalCount}
            active={activeKey === filterKey(filter)}
            onNavigate={onNavigate}
            icon={<CLASS_FOLDER_ICON aria-hidden className="size-[18px] shrink-0" strokeWidth={1.75} />}
            tint={tintForSlug(node.cls.slug)}
            className="flex-1"
          />
        </DropFolder>
      </div>

      {hasChildren && expanded ? (
        <div className="ml-6 flex flex-col gap-0.5 border-l border-border pl-2">
          {node.children.map((child) => {
            const childFilter: FolderFilter = { kind: "class", slug: child.slug };
            return (
              <DropFolder key={child.id} cls={child} onDelete={onDelete}>
                <FolderLink
                  href={folderHref(childFilter)}
                  label={child.name}
                  count={child.document_count}
                  active={activeKey === filterKey(childFilter)}
                  onNavigate={onNavigate}
                  tint={tintForSlug(node.cls.slug)}
                  className="flex-1"
                />
              </DropFolder>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/** Droppable wrapper around a class folder + its hover rename/delete/lock. */
function DropFolder({
  cls,
  onDelete,
  children,
}: {
  cls: ClassInfo;
  onDelete: (cls: ClassInfo) => void;
  children: React.ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `class:${cls.id}`,
    data: { classId: cls.id, name: cls.name },
  });
  const rename = useRenameFolder();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(cls.name);

  const submit = () => {
    const value = name.trim();
    if (value && value !== cls.name) rename.mutate({ classId: cls.id, name: value });
    setEditing(false);
  };

  if (editing) {
    return (
      <span className="flex flex-1 items-center gap-1 px-2.5 py-1">
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") setEditing(false);
          }}
          onBlur={submit}
          aria-label={`Rename ${cls.name}`}
          className="w-full rounded border border-accent bg-surface px-1.5 py-0.5 type-subhead text-text-1 outline-none"
        />
      </span>
    );
  }

  return (
    <div
      ref={setNodeRef}
      className={clsx(
        "group/f relative flex flex-1 items-center rounded-md transition-colors",
        isOver && "bg-accent-100 ring-1 ring-accent-300",
      )}
    >
      {children}
      {cls.is_system ? (
        <Lock
          aria-hidden
          className="pointer-events-none absolute right-2 size-3 text-text-3 opacity-0 group-hover/f:opacity-50"
        />
      ) : (
        <span className="absolute right-1 flex items-center gap-0.5 opacity-0 transition group-hover/f:opacity-100">
          <button
            type="button"
            aria-label={`Rename ${cls.name} folder`}
            onClick={() => {
              setName(cls.name);
              setEditing(true);
            }}
            className="flex size-6 items-center justify-center rounded text-text-3 hover:text-accent"
          >
            <Pencil aria-hidden className="size-3.5" />
          </button>
          <button
            type="button"
            aria-label={`Delete ${cls.name} folder`}
            onClick={() => onDelete(cls)}
            className="flex size-6 items-center justify-center rounded text-text-3 hover:text-danger"
          >
            <Trash2 aria-hidden className="size-3.5" />
          </button>
        </span>
      )}
    </div>
  );
}

/** Inline "create custom folder" control. */
function NewFolder() {
  const create = useCreateFolder();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  const submit = () => {
    const value = name.trim();
    if (!value) return;
    create.mutate(value, { onSuccess: () => setName("") });
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        type="button"
        aria-label="New folder"
        onClick={() => setOpen(true)}
        className="flex size-5 items-center justify-center rounded text-text-3 hover:text-accent"
      >
        <Plus aria-hidden className="size-4" />
      </button>
    );
  }

  return (
    <span className="flex items-center gap-1">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Folder name"
        aria-label="New folder name"
        className="w-28 rounded border border-border bg-surface px-1.5 py-0.5 type-caption text-text-1 outline-none focus-visible:border-accent"
      />
      <button type="button" aria-label="Create" onClick={submit} className="text-accent hover:text-accent-hover">
        <Check aria-hidden className="size-3.5" />
      </button>
      <button type="button" aria-label="Cancel" onClick={() => setOpen(false)} className="text-text-3 hover:text-text-1">
        <X aria-hidden className="size-3.5" />
      </button>
    </span>
  );
}

function FolderLink({
  href,
  label,
  count,
  active,
  icon,
  tint,
  onNavigate,
  className,
}: {
  href: string;
  label: string;
  count?: number;
  active: boolean;
  icon?: React.ReactNode;
  tint?: string;
  onNavigate?: () => void;
  className?: string;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "flex min-h-9 items-center gap-2 rounded-md px-2.5 type-subhead transition-colors",
        active
          ? "bg-accent-50 text-accent shadow-[inset_2px_0_0_0_var(--accent)]"
          : "text-text-2 hover:bg-surface-2 hover:text-text-1",
        className,
      )}
    >
      {icon}
      {!icon && tint ? (
        <span
          aria-hidden
          className="size-2 shrink-0 rounded-[3px]"
          style={{ backgroundColor: tint }}
        />
      ) : null}
      <span className="truncate">{label}</span>
      {count != null && count > 0 ? (
        <span className="ml-auto type-caption text-text-3">{count}</span>
      ) : null}
    </Link>
  );
}
