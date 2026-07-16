/** Small presentational formatters for the data voice (dates, sizes, counts). */

const DATE_FMT = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

/** Short absolute date, e.g. "Apr 1, 2025". */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : DATE_FMT.format(d);
}

/** Human file size from bytes. */
export function formatBytes(bytes: number | null): string | null {
  if (bytes == null) return null;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

/** "1 page" / "4 pages" / null. */
export function pageLabel(pageCount: number | null): string | null {
  if (pageCount == null || pageCount <= 0) return null;
  return `${pageCount} ${pageCount === 1 ? "page" : "pages"}`;
}

/** Compact count for stat tiles: 964 / 12.9K / 4.2M. */
export function formatCompact(n: number): string {
  if (Math.abs(n) < 1000) return String(n);
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

/** Money from integer cents, e.g. 1500 → "$15". */
export function formatMoney(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    minimumFractionDigits: cents % 100 === 0 ? 0 : 2,
  }).format(cents / 100);
}

/** Short day label for chart axes, e.g. "Jul 2". */
export function formatDayShort(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(d);
}
