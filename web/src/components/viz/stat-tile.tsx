/**
 * StatTile — a single headline number (dataviz: "the number is the chart").
 * Label in sentence case, sans-semibold proportional-figure value (never the
 * serif — display faces read as decoration on data), and an optional muted
 * hint line ("last 30 days", "2 ratings"). `value=null` renders the honest
 * em-dash empty state instead of a fake zero.
 */

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | null;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3.5 shadow-e1">
      <p className="type-subhead text-text-2">{label}</p>
      <p className="mt-1 text-[26px] font-semibold leading-8 text-text-1">
        {value ?? "—"}
      </p>
      {hint ? <p className="mt-0.5 type-caption text-text-3">{hint}</p> : null}
    </div>
  );
}
