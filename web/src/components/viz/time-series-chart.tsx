"use client";

/**
 * TimeSeriesChart — the single-accent line/area chart (dataviz mark specs:
 * 2px round-joined line, ~10% area wash, ≥8px end marker with a 2px surface
 * ring, hairline solid gridlines, selective endpoint label only).
 *
 * Interaction is part of the deliverable: a crosshair snaps to the nearest day
 * on pointer move, arrow keys walk the days on keyboard focus, and the tooltip
 * (value first, date second) never gates — an sr-only table twin carries every
 * value for screen readers. One series per chart, so no legend box: the title
 * above names it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { formatDayShort } from "@/lib/format";

export interface ChartPoint {
  date: string;
  value: number;
}

const HEIGHT = 200;
const M = { top: 10, right: 14, bottom: 24, left: 40 };

/** Round up to a clean axis maximum (1/2/5 × 10^k), minimum 4 for tiny counts. */
function niceMax(max: number): number {
  if (max <= 4) return 4;
  const pow = 10 ** Math.floor(Math.log10(max));
  for (const m of [1, 2, 5, 10]) {
    if (max <= m * pow) return m * pow;
  }
  return 10 * pow;
}

export function TimeSeriesChart({
  points,
  area = false,
  valueName,
  ariaLabel,
}: {
  points: ChartPoint[];
  /** Fill under the line (single-series area, e.g. archive growth). */
  area?: boolean;
  /** What one value is, for the tooltip/table (e.g. "documents", "queries"). */
  valueName: string;
  ariaLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(entry.contentRect.width),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const plotW = Math.max(width - M.left - M.right, 0);
  const plotH = HEIGHT - M.top - M.bottom;
  const yMax = niceMax(Math.max(...points.map((p) => p.value), 0));

  const x = useCallback(
    (i: number) =>
      M.left + (points.length <= 1 ? plotW / 2 : (i / (points.length - 1)) * plotW),
    [points.length, plotW],
  );
  const y = useCallback(
    (v: number) => M.top + plotH - (v / yMax) * plotH,
    [plotH, yMax],
  );

  const linePath = useMemo(
    () => points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.value)}`).join(""),
    [points, x, y],
  );
  const areaPath = useMemo(
    () =>
      `${linePath}L${x(points.length - 1)},${M.top + plotH}L${x(0)},${M.top + plotH}Z`,
    [linePath, points.length, plotH, x],
  );

  const yTicks = [0, yMax / 2, yMax];
  const xTickIdx = points.length <= 1 ? [0] : [0, Math.floor((points.length - 1) / 2), points.length - 1];

  const moveTo = (clientX: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || points.length === 0) return;
    const rel = (clientX - rect.left - M.left) / Math.max(plotW, 1);
    setActive(Math.min(points.length - 1, Math.max(0, Math.round(rel * (points.length - 1)))));
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const delta = e.key === "ArrowRight" ? 1 : -1;
      setActive((i) =>
        Math.min(points.length - 1, Math.max(0, (i ?? points.length - 1) + delta)),
      );
    }
    if (e.key === "Escape") setActive(null);
  };

  const last = points.length - 1;
  const activePoint = active != null ? points[active] : null;

  return (
    <div ref={containerRef} className="relative w-full">
      {width > 0 && points.length > 0 ? (
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={ariaLabel}
          tabIndex={0}
          className="block focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          onPointerMove={(e) => moveTo(e.clientX)}
          onPointerLeave={() => setActive(null)}
          onFocus={() => setActive((i) => i ?? last)}
          onBlur={() => setActive(null)}
          onKeyDown={onKeyDown}
        >
          {/* recessive hairline grid + y ticks (clean numbers) */}
          {yTicks.map((t) => (
            <g key={t}>
              <line
                x1={M.left}
                x2={width - M.right}
                y1={y(t)}
                y2={y(t)}
                className="stroke-border"
                strokeWidth={1}
              />
              <text
                x={M.left - 8}
                y={y(t) + 3}
                textAnchor="end"
                className="fill-text-3 type-caption tabular-nums"
              >
                {t}
              </text>
            </g>
          ))}
          {/* x tick labels: first / middle / last day */}
          {xTickIdx.map((i) => (
            <text
              key={i}
              x={x(i)}
              y={HEIGHT - 6}
              textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"}
              className="fill-text-3 type-caption"
            >
              {formatDayShort(points[i].date)}
            </text>
          ))}

          {area ? <path d={areaPath} className="fill-accent opacity-10" /> : null}
          <path
            d={linePath}
            fill="none"
            className="stroke-accent"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* crosshair + active marker (2px surface ring) */}
          {activePoint ? (
            <g>
              <line
                x1={x(active!)}
                x2={x(active!)}
                y1={M.top}
                y2={M.top + plotH}
                className="stroke-border-strong"
                strokeWidth={1}
              />
              <circle
                cx={x(active!)}
                cy={y(activePoint.value)}
                r={5}
                className="fill-accent stroke-card"
                strokeWidth={2}
              />
            </g>
          ) : (
            /* resting endpoint marker + selective direct label (the endpoint only) */
            <g>
              <circle
                cx={x(last)}
                cy={y(points[last].value)}
                r={4}
                className="fill-accent stroke-card"
                strokeWidth={2}
              />
              <text
                x={x(last) - 8}
                y={y(points[last].value) - 8}
                textAnchor="end"
                className="fill-text-1 type-caption font-semibold tabular-nums"
              >
                {points[last].value}
              </text>
            </g>
          )}
        </svg>
      ) : (
        <div style={{ height: HEIGHT }} />
      )}

      {/* tooltip — value leads, date follows; mirrors keyboard focus */}
      {activePoint && width > 0 ? (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-md border border-border bg-surface px-2.5 py-1.5 shadow-e2"
          style={{
            left: Math.min(Math.max(x(active!), 56), width - 56),
            top: Math.max(y(activePoint.value) - 54, 0),
          }}
        >
          <p className="type-subhead tabular-nums text-text-1">
            {activePoint.value} {valueName}
          </p>
          <p className="type-caption text-text-3">{formatDayShort(activePoint.date)}</p>
        </div>
      ) : null}

      {/* table twin — every value reachable without hover (WCAG) */}
      <table className="sr-only">
        <caption>{ariaLabel}</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">{valueName}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date}>
              <td>{p.date}</td>
              <td>{p.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
