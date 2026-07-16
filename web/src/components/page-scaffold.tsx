/**
 * PageScaffold — the shared frame every screen renders into: an accent-ink
 * eyebrow, a serif page title, optional lede, and a content slot. Milestone
 * screens pass an <EmptyState> placeholder; real content replaces it later.
 */

import type { LucideIcon } from "lucide-react";

export function PageScaffold({
  eyebrow,
  title,
  lede,
  children,
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-5xl flex-col px-4 py-8 sm:px-8 sm:py-10">
      <header className="mb-8">
        {eyebrow ? <p className="eyebrow mb-2">{eyebrow}</p> : null}
        <h1 className="type-display text-text-1">{title}</h1>
        {lede ? <p className="mt-2 max-w-2xl type-body text-text-2">{lede}</p> : null}
      </header>
      {children}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border-strong bg-card/60 px-6 py-16 text-center">
      <span className="flex size-12 items-center justify-center rounded-lg bg-surface-2 text-accent">
        <Icon aria-hidden className="size-6" strokeWidth={1.5} />
      </span>
      <h2 className="mt-4 type-title2 text-text-1">{title}</h2>
      <p className="mt-1 max-w-sm type-callout text-text-2">{description}</p>
      <span className="mt-5 rounded-full bg-hl-wash px-3 py-1 type-caption uppercase text-hl-strong">
        Coming in a later milestone
      </span>
    </div>
  );
}
