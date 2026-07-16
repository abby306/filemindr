/**
 * BarList — horizontal magnitude bars for nominal categories (top folders,
 * most-asked docs). Dataviz rules applied: nominal categories take ONE hue
 * (the accent) — never a color per bar (the folder tint appears only as the
 * identity dot beside the name, always next to its label, mirroring the
 * archive's wayfinding); bars are thin with a 4px rounded data-end and a
 * square baseline; the value sits at the bar tip in text ink, never on the
 * mark's color. Rendered as a real list, so it is its own table twin.
 */

export interface BarListItem {
  key: string;
  label: string;
  value: number;
  /** Optional identity tint (folder color) shown as a dot beside the label. */
  tint?: string;
}

export function BarList({
  items,
  ariaLabel,
}: {
  items: BarListItem[];
  ariaLabel: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ol aria-label={ariaLabel} className="flex flex-col gap-2.5">
      {items.map((item) => (
        <li key={item.key} className="grid grid-cols-[minmax(7rem,30%)_1fr_auto] items-center gap-3">
          <span className="flex min-w-0 items-center gap-2">
            {item.tint ? (
              <span
                aria-hidden
                className="size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: item.tint }}
              />
            ) : null}
            <span className="truncate type-callout text-text-1" title={item.label}>
              {item.label}
            </span>
          </span>
          <span aria-hidden className="h-2.5">
            <span
              className="block h-full rounded-r-[4px] bg-accent"
              style={{ width: `${Math.max((item.value / max) * 100, 1.5)}%` }}
            />
          </span>
          <span className="type-data tabular-nums text-text-2">{item.value}</span>
        </li>
      ))}
    </ol>
  );
}
