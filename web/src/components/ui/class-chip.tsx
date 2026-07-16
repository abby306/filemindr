/** ClassChip — a document's class label: category tint, name, optional parent
 *  context and confidence. `primary` styles the folder-owning class prominently;
 *  secondary labels read quieter. */

import clsx from "clsx";

import { tintForSlug } from "@/features/archive/taxonomy";

export function ClassChip({
  name,
  slug,
  parentSlug,
  confidence,
  primary,
}: {
  name: string;
  slug: string;
  parentSlug: string | null;
  confidence?: number | null;
  primary?: boolean;
}) {
  const pct = confidence == null ? null : Math.round(Math.max(0, Math.min(1, confidence)) * 100);
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1",
        primary
          ? "border-accent-300 bg-accent-50"
          : "border-border bg-surface-2",
      )}
    >
      <span
        aria-hidden
        className="size-2.5 shrink-0 rounded-[3px]"
        style={{ backgroundColor: tintForSlug(parentSlug ?? slug) }}
      />
      <span className={clsx("type-subhead", primary ? "text-text-1" : "text-text-2")}>
        {name}
      </span>
      {pct != null ? (
        <span className="type-data text-text-3">{pct}%</span>
      ) : null}
      {primary ? (
        <span className="type-caption uppercase text-accent">primary</span>
      ) : null}
    </span>
  );
}
