"use client";

/**
 * AppShell — the responsive chrome: top bar + main content, with primary
 * navigation as a persistent left rail on desktop (≥lg) and a bottom tab bar
 * below that (TabBar owns the More sheet). Content is a scroll container so
 * the shell stays fixed; mobile content keeps clearance for the tab bar.
 */

import { CommandPalette } from "@/components/shell/command-palette";
import { ProcessingDock } from "@/components/shell/processing-dock";
import { Sidebar } from "@/components/shell/sidebar";
import { TabBar } from "@/components/shell/tab-bar";
import { TopBar } from "@/components/shell/top-bar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-canvas text-text-1">
      <TopBar />

      <div className="flex min-h-0 flex-1">
        {/* Desktop rail */}
        <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:block">
          <Sidebar />
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
