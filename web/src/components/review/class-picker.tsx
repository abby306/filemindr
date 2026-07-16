"use client";

/**
 * ClassPicker — type-ahead over the full class taxonomy with inline folder
 * creation. Filtering/keyboard is view concern; the actual assignment (pick an
 * existing class, or create one) is a server call the parent owns. Arrow keys
 * move the highlight, Enter selects, and a "Create" row appears when the query
 * doesn't match an existing class.
 */

import { useMemo, useState, type RefObject } from "react";
import { FolderPlus, Search } from "lucide-react";
import clsx from "clsx";

import { useClasses } from "@/features/archive/queries";
import { CLASS_FOLDER_ICON } from "@/features/archive/taxonomy";
import type { ClassInfo } from "@/lib/api/types";

const MAX_RESULTS = 7;

export function ClassPicker({
  onPick,
  onCreate,
  disabled,
  inputRef,
}: {
  onPick: (classId: string) => void;
  onCreate: (name: string) => void;
  disabled?: boolean;
  inputRef?: RefObject<HTMLInputElement | null>;
}) {
  const { data } = useClasses();
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);

  const results = useMemo<ClassInfo[]>(() => {
    const all = data?.classes ?? [];
    const q = query.trim().toLowerCase();
    if (!q) {
      // Default to leaf/subclasses first (more specific = better labels).
      return [...all]
        .sort((a, b) => Number(!!b.parent_id) - Number(!!a.parent_id))
        .slice(0, MAX_RESULTS);
    }
    return all
      .filter((c) => c.name.toLowerCase().includes(q) || c.slug.includes(q))
      .sort((a, b) => rank(a, q) - rank(b, q))
      .slice(0, MAX_RESULTS);
  }, [data, query]);

  const exactMatch = results.some(
    (c) => c.name.toLowerCase() === query.trim().toLowerCase(),
  );
  const canCreate = query.trim().length > 0 && !exactMatch;
  const rowCount = results.length + (canCreate ? 1 : 0);

  const commit = (index: number) => {
    if (index < results.length) onPick(results[index].id);
    else if (canCreate) onCreate(query.trim());
  };

  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search aria-hidden className="size-4 shrink-0 text-text-3" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          disabled={disabled}
          placeholder="Search folders, or type a new name…"
          aria-label="Search or create a folder"
          className="min-h-11 w-full bg-transparent type-body text-text-1 outline-none placeholder:text-text-3"
          onChange={(e) => {
            setQuery(e.target.value);
            setHighlight(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setHighlight((h) => Math.min(h + 1, rowCount - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setHighlight((h) => Math.max(h - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              commit(highlight);
            }
          }}
        />
      </div>

      <ul className="max-h-64 overflow-y-auto p-1.5">
        {results.map((c, i) => (
          <li key={c.id}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(c.id)}
              onMouseEnter={() => setHighlight(i)}
              className={clsx(
                "flex min-h-10 w-full items-center gap-2.5 rounded-md px-2.5 text-left transition-colors",
                highlight === i ? "bg-accent-50" : "hover:bg-surface-2",
              )}
            >
              <CLASS_FOLDER_ICON
                aria-hidden
                className="size-3.5 shrink-0 text-text-3"
                strokeWidth={1.75}
              />
              <span className="type-subhead text-text-1">{c.name}</span>
              {c.parent_slug ? (
                <span className="ml-auto type-data text-text-3">{c.parent_slug}</span>
              ) : null}
            </button>
          </li>
        ))}

        {canCreate ? (
          <li>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onCreate(query.trim())}
              onMouseEnter={() => setHighlight(results.length)}
              className={clsx(
                "flex min-h-10 w-full items-center gap-2.5 rounded-md px-2.5 text-left transition-colors",
                highlight === results.length ? "bg-accent-50" : "hover:bg-surface-2",
              )}
            >
              <FolderPlus aria-hidden className="size-4 shrink-0 text-accent" />
              <span className="type-subhead text-text-1">
                Create folder “{query.trim()}”
              </span>
            </button>
          </li>
        ) : null}

        {rowCount === 0 ? (
          <li className="px-2.5 py-3 type-callout text-text-3">No folders found.</li>
        ) : null}
      </ul>
    </div>
  );
}

function rank(c: ClassInfo, q: string): number {
  const name = c.name.toLowerCase();
  if (name === q) return 0;
  if (name.startsWith(q)) return 1;
  if (c.slug.startsWith(q)) return 2;
  return 3;
}
