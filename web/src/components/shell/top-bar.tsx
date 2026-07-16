"use client";

/** Ink masthead — the app's identity band: deep fountain-pen ink with a cream
 *  serif wordmark, the account switcher, and the live backend status. */

import { Menu } from "lucide-react";

import { AccountSwitcher } from "@/components/shell/account-switcher";
import { BackendStatus } from "@/components/shell/backend-status";
import { ThemeToggle } from "@/components/shell/theme-toggle";

export function TopBar({ onMenu }: { onMenu: () => void }) {
  return (
    <header className="masthead flex h-14 shrink-0 items-center gap-3 px-3 text-on-ink sm:px-4">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open navigation"
        className="flex size-11 items-center justify-center rounded-md text-on-ink-muted transition-colors hover:bg-white/10 hover:text-on-ink lg:hidden"
      >
        <Menu aria-hidden className="size-5" />
      </button>

      <div className="flex items-baseline gap-2.5">
        <span className="type-title2 text-on-ink">filemindr</span>
        <span className="hidden type-caption italic text-on-ink-muted sm:inline">
          intelligent archivist
        </span>
      </div>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <span className="hidden sm:flex">
          <BackendStatus />
        </span>
        <ThemeToggle />
        <AccountSwitcher />
      </div>
    </header>
  );
}
