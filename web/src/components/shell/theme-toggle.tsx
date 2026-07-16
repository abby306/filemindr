"use client";

/** ThemeToggle — flips light ⇄ dark (persisted). SSR-safe via useSyncExternalStore. */

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";

import { getTheme, setTheme, subscribeTheme } from "@/lib/theme/theme";

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => "light");
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} mode`}
      className="flex size-9 items-center justify-center rounded-md text-on-ink-muted transition-colors hover:bg-white/10 hover:text-on-ink"
    >
      {theme === "dark" ? (
        <Sun aria-hidden className="size-4" />
      ) : (
        <Moon aria-hidden className="size-4" />
      )}
    </button>
  );
}
