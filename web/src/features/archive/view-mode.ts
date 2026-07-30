"use client";

/**
 * The archive's view mode — Explorer's three ways to look at a folder:
 *
 *   details — the dense sortable table (thumbnail, folder, status, size, date)
 *   list    — name-only, packed into columns: scan a big folder at a glance
 *   icons   — the card grid, summaries and all
 *
 * Persisted per browser like the tree pane's collapse, because a view mode the
 * user picked and lost on the next visit is worse than not offering one. Read
 * through `useSyncExternalStore` so SSR renders the default without an effect.
 */

import { useCallback, useSyncExternalStore } from "react";

export type ViewMode = "details" | "list" | "icons";

const KEY = "filemindr.archiveView";
const EVENT = "filemindr:archive-view";
const DEFAULT: ViewMode = "details";

function isMode(value: string | null): value is ViewMode {
  return value === "details" || value === "list" || value === "icons";
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useViewMode(): [ViewMode, (next: ViewMode) => void] {
  const mode = useSyncExternalStore(
    subscribe,
    () => {
      const stored = window.localStorage.getItem(KEY);
      return isMode(stored) ? stored : DEFAULT;
    },
    () => DEFAULT,
  );
  const setMode = useCallback((next: ViewMode) => {
    window.localStorage.setItem(KEY, next);
    window.dispatchEvent(new Event(EVENT));
  }, []);
  return [mode, setMode];
}
