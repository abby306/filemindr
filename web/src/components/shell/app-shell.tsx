"use client";

/**
 * AppShell — the responsive chrome: top bar + main content, with primary
 * navigation as a persistent left rail on desktop (≥lg) and a bottom tab bar
 * below that (TabBar owns the More sheet). The rail collapses to an icon strip
 * (persisted per browser) so any screen can run full width. Content is a
 * scroll container so the shell stays fixed; mobile content keeps clearance
 * for the tab bar.
 */

import { useCallback, useSyncExternalStore } from "react";
import clsx from "clsx";

import { CommandPalette } from "@/components/shell/command-palette";
import { ProcessingDock } from "@/components/shell/processing-dock";
import { Sidebar } from "@/components/shell/sidebar";
import { TabBar } from "@/components/shell/tab-bar";
import { TopBar } from "@/components/shell/top-bar";

const RAIL_KEY = "filemindr.railCollapsed";
const RAIL_EVENT = "filemindr:rail-change";

function subscribeRail(onChange: () => void): () => void {
  window.addEventListener(RAIL_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(RAIL_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Desktop-rail collapse, persisted per browser (multi-tab safe). */
function useCollapsedRail(): [boolean, () => void] {
  const collapsed = useSyncExternalStore(
    subscribeRail,
    () => window.localStorage.getItem(RAIL_KEY) === "1",
    () => false,
  );
  const toggle = useCallback(() => {
    window.localStorage.setItem(
      RAIL_KEY,
      window.localStorage.getItem(RAIL_KEY) === "1" ? "0" : "1",
    );
    window.dispatchEvent(new Event(RAIL_EVENT));
  }, []);
  return [collapsed, toggle];
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [railCollapsed, toggleRail] = useCollapsedRail();

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-canvas text-text-1">
      <TopBar />

      <div className="flex min-h-0 flex-1">
        {/* Desktop rail — collapsible to an icon strip for full-width content */}
        <aside
          className={clsx(
            "hidden shrink-0 border-r border-border bg-surface transition-[width] duration-[var(--dur-base)] ease-[var(--ease-quiet)] lg:block",
            railCollapsed ? "w-14" : "w-60",
          )}
        >
          <Sidebar collapsed={railCollapsed} onToggleCollapse={toggleRail} />
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto pb-20 lg:pb-0">
          {children}
        </main>
      </div>

      <TabBar />
      <ProcessingDock />
      <CommandPalette />
    </div>
  );
}
