"use client";

/** Top bar — quiet surface with a hairline rule. The wordmark carries the
 *  brand's one idea: an amber wash over "mind", a highlighted word. */

import { Menu } from "lucide-react";

import { AccountSwitcher } from "@/components/shell/account-switcher";
import { BackendStatus } from "@/components/shell/backend-status";
import { ThemeToggle } from "@/components/shell/theme-toggle";

export function TopBar({ onMenu }: { onMenu: () => void }) {
  return (
    <header className="flex h-13 shrink-0 items-center gap-3 border-b border-border bg-surface px-3 sm:px-4">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open navigation"
        className="flex size-11 items-center justify-center rounded-md text-text-2 transition-colors hover:bg-surface-2 hover:text-text-1 lg:hidden"
      >
        <Menu aria-hidden className="size-5" />
      </button>

      <span className="wordmark text-[19px] text-text-1">
        file<span className="wordmark-mark">mind</span>r
      </span>

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
