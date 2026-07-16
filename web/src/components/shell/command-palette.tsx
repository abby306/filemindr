"use client";

/**
 * CommandPalette — ⌘K / Ctrl-K quick navigation + actions. A lightweight modal
 * (overlay + filterable list, arrow/enter keyboard) for jumping between screens,
 * starting a chat, or toggling the theme.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  CreditCard,
  FolderOpen,
  Inbox,
  MessageSquareText,
  Search,
  SunMoon,
  Upload,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";

import { getTheme, setTheme } from "@/lib/theme/theme";

interface Command {
  id: string;
  label: string;
  icon: LucideIcon;
  keywords?: string;
  run: (router: ReturnType<typeof useRouter>) => void;
}

const COMMANDS: Command[] = [
  { id: "upload", label: "Upload", icon: Upload, keywords: "intake add file", run: (r) => r.push("/") },
  { id: "archive", label: "Archive", icon: FolderOpen, keywords: "documents folders", run: (r) => r.push("/archive") },
  { id: "review", label: "Review", icon: Inbox, keywords: "needs review queue", run: (r) => r.push("/review") },
  { id: "ask", label: "Ask — new chat", icon: MessageSquareText, keywords: "chat question", run: (r) => r.push("/chat") },
  { id: "analytics", label: "Analytics", icon: BarChart3, keywords: "usage quality", run: (r) => r.push("/analytics") },
  // Billing is a hosted-product surface; hidden unless enabled (see lib/nav.ts).
  ...(process.env.NEXT_PUBLIC_ENABLE_BILLING === "1"
    ? [{ id: "billing", label: "Billing", icon: CreditCard, keywords: "plan invoices", run: (r) => r.push("/billing") } satisfies Command]
    : []),
  {
    id: "theme",
    label: "Toggle light / dark",
    icon: SunMoon,
    keywords: "theme dark mode appearance",
    run: () => setTheme(getTheme() === "dark" ? "light" : "dark"),
  },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
        setHighlight(0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return COMMANDS;
    return COMMANDS.filter(
      (c) => c.label.toLowerCase().includes(q) || c.keywords?.includes(q),
    );
  }, [query]);

  if (!open) return null;

  const run = (cmd: Command | undefined) => {
    if (!cmd) return;
    setOpen(false);
    cmd.run(router);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[15vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="absolute inset-0 bg-p-950/40 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />
      <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-e3">
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search aria-hidden className="size-4 shrink-0 text-text-3" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setHighlight(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setHighlight((h) => Math.min(h + 1, results.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setHighlight((h) => Math.max(h - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(results[highlight]);
              } else if (e.key === "Escape") {
                setOpen(false);
              }
            }}
            placeholder="Jump to…"
            aria-label="Command"
            className="min-h-12 w-full bg-transparent type-body text-text-1 outline-none placeholder:text-text-3"
          />
          <kbd className="hidden shrink-0 rounded border border-border bg-surface-2 px-1.5 py-0.5 type-caption text-text-3 sm:block">
            esc
          </kbd>
        </div>

        <ul className="max-h-80 overflow-y-auto p-1.5">
          {results.length === 0 ? (
            <li className="px-3 py-3 type-callout text-text-3">No matches.</li>
          ) : (
            results.map((cmd, i) => {
              const Icon = cmd.icon;
              return (
                <li key={cmd.id}>
                  <button
                    type="button"
                    onClick={() => run(cmd)}
                    onMouseEnter={() => setHighlight(i)}
                    className={clsx(
                      "flex min-h-10 w-full items-center gap-3 rounded-md px-2.5 text-left type-subhead transition-colors",
                      highlight === i ? "bg-accent-50 text-accent" : "text-text-1 hover:bg-surface-2",
                    )}
                  >
                    <Icon aria-hidden className="size-4 shrink-0 text-text-3" />
                    {cmd.label}
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}
