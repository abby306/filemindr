"use client";

/**
 * UsageMeter — one plan limit as a meter. The fill carries severity along the
 * status ramp (accent → amber past 75% → red past 90%) and the unfilled track
 * is a lighter step of the same ramp so state reads across the whole bar
 * (dataviz meter spec). Color is never the sole signal: the exact numbers ride
 * beside the label in the data voice, and near-limit adds a warning icon +
 * text. A null limit renders as "Unlimited" with a quiet full-track meter.
 */

import { TriangleAlert } from "lucide-react";
import clsx from "clsx";

export function UsageMeter({
  label,
  used,
  limit,
  formatValue,
}: {
  label: string;
  used: number;
  limit: number | null;
  /** Render a raw number for display (counts, bytes…). */
  formatValue: (n: number) => string;
}) {
  const pct = limit == null || limit === 0 ? null : Math.min((used / limit) * 100, 100);
  const severity = pct == null ? "none" : pct >= 90 ? "danger" : pct >= 75 ? "warn" : "ok";

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-1.5 type-subhead text-text-2">
          {label}
          {severity === "warn" || severity === "danger" ? (
            <TriangleAlert
              aria-hidden
              className={clsx(
                "size-3.5",
                severity === "danger" ? "text-danger" : "text-hl-strong",
              )}
              strokeWidth={2}
            />
          ) : null}
        </span>
        <span className="type-data tabular-nums text-text-2">
          {formatValue(used)}
          <span className="text-text-3">
            {" "}
            / {limit == null ? "Unlimited" : formatValue(limit)}
          </span>
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuenow={used}
        aria-valuemin={0}
        aria-valuemax={limit ?? undefined}
        aria-valuetext={`${formatValue(used)} of ${limit == null ? "unlimited" : formatValue(limit)}`}
        className={clsx(
          "h-2 overflow-hidden rounded-full",
          severity === "none" && "bg-surface-2",
          severity === "ok" && "bg-accent/20",
          severity === "warn" && "bg-hl-wash",
          severity === "danger" && "bg-danger/15",
        )}
      >
        {pct != null ? (
          <div
            className={clsx(
              "h-full rounded-full",
              severity === "ok" && "bg-accent",
              severity === "warn" && "bg-hl",
              severity === "danger" && "bg-danger",
            )}
            style={{ width: `${pct}%` }}
          />
        ) : null}
      </div>
      {severity === "danger" && pct != null && pct >= 100 ? (
        <p className="mt-1 type-caption text-danger">Limit reached — upgrade to continue.</p>
      ) : null}
    </div>
  );
}
