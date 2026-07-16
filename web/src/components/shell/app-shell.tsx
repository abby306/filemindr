"use client";

/**
 * AppShell — the responsive chrome: top bar + Finder-style rail + main content.
 * Desktop (≥lg): persistent left column. Mobile: the rail becomes a slide-in
 * drawer over a scrim, closing on navigation or Escape. Content is a scroll
 * container so the shell stays fixed.
 */

import { useEffect, useState } from "react";
import clsx from "clsx";

import { CommandPalette } from "@/components/shell/command-palette";
import { ProcessingDock } from "@/components/shell/processing-dock";
import { Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/top-bar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Close the mobile drawer on Escape.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="paper-grain flex h-dvh flex-col overflow-hidden bg-canvas text-text-1">
      <TopBar onMenu={() => setDrawerOpen(true)} />

      <div className="flex min-h-0 flex-1">
        {/* Desktop rail */}
        <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:block">
          <Sidebar />
        </aside>

        {/* Mobile drawer */}
        <div
          className={clsx(
            "fixed inset-0 z-40 lg:hidden",
            drawerOpen ? "pointer-events-auto" : "pointer-events-none",
          )}
          aria-hidden={!drawerOpen}
        >
          <div
            onClick={() => setDrawerOpen(false)}
            className={clsx(
              "absolute inset-0 bg-p-950/40 transition-opacity duration-[var(--dur-base)]",
              drawerOpen ? "opacity-100" : "opacity-0",
            )}
          />
          <aside
            className={clsx(
              "absolute left-0 top-0 h-full w-64 border-r border-border bg-surface shadow-e3 transition-transform duration-[var(--dur-base)] ease-[var(--ease-quiet)]",
              drawerOpen ? "translate-x-0" : "-translate-x-full",
            )}
          >
            <Sidebar onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>

        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>

      <ProcessingDock />
      <CommandPalette />
    </div>
  );
}
