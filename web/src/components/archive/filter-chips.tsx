"use client";

/**
 * FilterChips — folders demoted from a rail to one quiet chip row: smart
 * filters (All / Needs review) then the parent folders that hold documents.
 * Selecting a parent with subclasses reveals a second row of child chips.
 * Folder CRUD stays here: a "+" chip creates a custom folder inline, and the
 * active custom folder's chip carries a rename/delete menu.
 */

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CornerDownRight, MoreHorizontal, Plus } from "lucide-react";
import clsx from "clsx";

import {
  useClasses,
  useCreateFolder,
  useDeleteFolder,
  useRenameFolder,
} from "@/features/archive/queries";
import {
  SMART_FOLDERS,
  filterKey,
  folderHref,
  type FolderNode,
} from "@/features/archive/taxonomy";
import type { ClassInfo } from "@/lib/api/types";
import { useDismiss } from "@/lib/use-dismiss";

export function FilterChips({ activeKey }: { activeKey: string }) {
  const { data, isPending } = useClasses();

  if (isPending) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <span key={i} className="animate-skeleton h-8 w-24 rounded-full" />
        ))}
      </div>
    );
  }
  if (!data) return null;

  // The active parent row: selected parent, or the parent of a selected child.
  const activeParent = data.tree.find(
    (node) =>
      activeKey === `class:${node.cls.slug}` ||
      node.children.some((c) => activeKey === `class:${c.slug}`),
  );

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {SMART_FOLDERS.map((f) => (
          <Chip
            key={f.segment ?? "all"}
            href={folderHref(f.filter)}
            label={f.label}
            active={activeKey === filterKey(f.filter)}
          />
        ))}
        <span aria-hidden className="mx-1 h-4 w-px bg-border" />
        {data.tree.map((node) => (
          <FolderChip
            key={node.cls.id}
            cls={node.cls}
            count={node.totalCount}
            active={activeKey === `class:${node.cls.slug}`}
            containsActive={node.children.some(
              (c) => activeKey === `class:${c.slug}`,
            )}
          />
        ))}
        <NewFolderChip />
      </div>

      {activeParent && activeParent.children.length > 0 ? (
        <SubfolderRow node={activeParent} activeKey={activeKey} />
      ) : null}
    </div>
  );
}

function SubfolderRow({ node, activeKey }: { node: FolderNode; activeKey: string }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 pl-2">
      <CornerDownRight aria-hidden className="size-3.5 text-text-3" />
      {node.children.map((child) => (
        <FolderChip
          key={child.id}
          cls={child}
          count={child.document_count}
          active={activeKey === `class:${child.slug}`}
        />
      ))}
    </div>
  );
}

const CHIP_BASE =
  "inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 type-subhead transition-colors";
const CHIP_ACTIVE = "border-accent-300 bg-accent-50 text-accent-text";
const CHIP_IDLE =
  "border-border bg-surface text-text-2 hover:bg-surface-2 hover:text-text-1";

function Chip({
  href,
  label,
  count,
  active,
}: {
  href: string;
  label: string;
  count?: number;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={clsx(CHIP_BASE, active ? CHIP_ACTIVE : CHIP_IDLE)}
    >
      {label}
      {count != null && count > 0 ? (
        <span className={clsx("type-caption", active ? "opacity-70" : "text-text-3")}>
          {count}
        </span>
      ) : null}
    </Link>
  );
}

/** A folder chip; when it's the active custom folder it grows a ⋯ menu
 *  (rename / delete) so folder management survives the rail's removal. */
function FolderChip({
  cls,
  count,
  active,
  containsActive,
}: {
  cls: ClassInfo;
  count: number;
  active: boolean;
  containsActive?: boolean;
}) {
  const router = useRouter();
  const rename = useRenameFolder();
  const del = useDeleteFolder();
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(cls.name);
  const menuRef = useRef<HTMLDivElement>(null);
  useDismiss(menuRef, () => setMenuOpen(false), menuOpen);

  const submitRename = () => {
    const value = name.trim();
    if (value && value !== cls.name) {
      rename.mutate({ classId: cls.id, name: value });
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <span className={clsx(CHIP_BASE, CHIP_ACTIVE)}>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitRename();
            if (e.key === "Escape") setEditing(false);
          }}
          onBlur={submitRename}
          aria-label={`Rename ${cls.name}`}
          size={Math.max(name.length, 4)}
          className="bg-transparent outline-none"
        />
      </span>
    );
  }

  const editable = active && !cls.is_system;

  return (
    <div ref={menuRef} className="relative">
      <span
        className={clsx(
          CHIP_BASE,
          active || containsActive ? CHIP_ACTIVE : CHIP_IDLE,
          editable && "pr-1.5",
        )}
      >
        <Link href={folderHref({ kind: "class", slug: cls.slug })} aria-current={active ? "page" : undefined} className="inline-flex items-center gap-1.5">
          {cls.name}
          {count > 0 ? (
            <span
              className={clsx(
                "type-caption",
                active || containsActive ? "opacity-70" : "text-text-3",
              )}
            >
              {count}
            </span>
          ) : null}
        </Link>
        {editable ? (
          <button
            type="button"
            aria-label={`${cls.name} folder options`}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
            className="flex size-5 items-center justify-center rounded-full hover:bg-accent-100"
          >
            <MoreHorizontal aria-hidden className="size-3.5" />
          </button>
        ) : null}
      </span>

      {menuOpen ? (
        <div className="absolute left-0 top-full z-20 mt-1 min-w-36 rounded-lg border border-border bg-surface p-1 shadow-e2">
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              setName(cls.name);
              setEditing(true);
            }}
            className="flex w-full items-center rounded-md px-2.5 py-1.5 type-subhead text-text-1 hover:bg-surface-2"
          >
            Rename
          </button>
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              if (
                window.confirm(
                  `Delete the "${cls.name}" folder? Documents keep their other labels.`,
                )
              ) {
                del.mutate(cls.id, { onSuccess: () => router.push("/archive") });
              }
            }}
            className="flex w-full items-center rounded-md px-2.5 py-1.5 type-subhead text-danger hover:bg-surface-2"
          >
            Delete
          </button>
        </div>
      ) : null}
    </div>
  );
}

function NewFolderChip() {
  const create = useCreateFolder();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  const submit = () => {
    const value = name.trim();
    if (value) create.mutate(value);
    setName("");
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        type="button"
        aria-label="New folder"
        onClick={() => setOpen(true)}
        className={clsx(CHIP_BASE, CHIP_IDLE, "border-dashed")}
      >
        <Plus aria-hidden className="size-3.5" />
        New folder
      </button>
    );
  }

  return (
    <span className={clsx(CHIP_BASE, CHIP_ACTIVE)}>
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setOpen(false);
        }}
        onBlur={submit}
        placeholder="Folder name"
        aria-label="New folder name"
        size={12}
        className="bg-transparent outline-none placeholder:text-text-3"
      />
    </span>
  );
}
