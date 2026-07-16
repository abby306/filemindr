"use client";

/** AccountSwitcher — personal ⇄ company. Styled for the ink masthead (cream on
 *  translucent). Native <select> for a11y + zero deps. */

import { ChevronsUpDown } from "lucide-react";

import { useAccount } from "@/lib/account/account-context";

export function AccountSwitcher() {
  const { account, accounts, setAccount } = useAccount();

  return (
    <label className="group relative flex items-center">
      <span className="sr-only">Active account</span>
      <span
        aria-hidden
        className="pointer-events-none absolute left-2 flex size-5 items-center justify-center rounded-sm bg-hl text-p-950 type-caption"
      >
        {account.label.charAt(0)}
      </span>
      <select
        value={account.id}
        onChange={(e) => setAccount(e.target.value)}
        className="type-subhead cursor-pointer appearance-none rounded-md border border-[color:var(--on-ink-border)] bg-white/10 py-1.5 pl-9 pr-8 text-on-ink transition-colors hover:bg-white/15 focus-visible:border-on-ink"
      >
        {accounts.map((a) => (
          <option key={a.id} value={a.id} className="bg-surface text-text-1">
            {a.label}
          </option>
        ))}
      </select>
      <ChevronsUpDown
        aria-hidden
        className="pointer-events-none absolute right-2.5 size-3.5 text-on-ink-muted"
      />
    </label>
  );
}
