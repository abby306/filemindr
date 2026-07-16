/** ConfidenceBar — a small track filled to a [0,1] confidence, with a % label. */

import clsx from "clsx";

export function ConfidenceBar({
  value,
  className,
}: {
  value: number | null;
  className?: string;
}) {
  const pct = value == null ? null : Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span className={clsx("flex items-center gap-2", className)}>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <span
          className="block h-full rounded-full bg-accent transition-[width] duration-[var(--dur-base)]"
          style={{ width: `${pct ?? 0}%` }}
        />
      </span>
      <span className="w-9 shrink-0 text-right type-caption text-text-3">
        {pct == null ? "—" : `${pct}%`}
      </span>
    </span>
  );
}
