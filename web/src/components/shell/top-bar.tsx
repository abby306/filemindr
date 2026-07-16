"use client";

/** Top bar — quiet surface with a hairline rule. The wordmark carries the
 *  brand's one idea: an amber wash over "mind", a highlighted word. */

import { AccountSwitcher } from "@/components/shell/account-switcher";
import { BackendStatus } from "@/components/shell/backend-status";
import { ThemeToggle } from "@/components/shell/theme-toggle";

/** Navigation lives in the sidebar (≥lg) / bottom tab bar (below) — the top
 *  bar carries only the brand and session controls. */
export function TopBar() {
  return (
    <header className="flex h-13 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
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
