"use client";

/** SegmentedControl — small accessible radio group (e.g. Gallery / List view). */

import clsx from "clsx";

export interface Segment<T extends string> {
  value: T;
  label: string;
  icon?: React.ReactNode;
}

export function SegmentedControl<T extends string>({
  value,
  onChange,
  segments,
  ariaLabel,
}: {
  value: T;
  onChange: (value: T) => void;
  segments: Segment<T>[];
  ariaLabel: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex items-center gap-0.5 rounded-md border border-border bg-surface-2 p-0.5"
    >
      {segments.map((seg) => {
        const active = seg.value === value;
        return (
          <button
            key={seg.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={seg.label}
            onClick={() => onChange(seg.value)}
            className={clsx(
              "flex min-h-8 items-center gap-1.5 rounded-[6px] px-2.5 type-subhead transition-colors",
              active
                ? "bg-surface text-text-1 shadow-e1"
                : "text-text-3 hover:text-text-1",
            )}
          >
            {seg.icon}
            <span className="hidden sm:inline">{seg.label}</span>
          </button>
        );
      })}
    </div>
  );
}
