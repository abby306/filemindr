/** Skeleton — a quiet loading placeholder (pulses only when motion is allowed). */

import clsx from "clsx";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={clsx(
        "rounded-md bg-surface-2 motion-safe:animate-pulse",
        className,
      )}
    />
  );
}
