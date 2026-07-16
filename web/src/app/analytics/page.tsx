"use client";

/**
 * Analytics — two lenses over the archive (FRONTEND.md): Usage (growth,
 * activity, folders, most-asked) scoped by one range filter row, and Quality
 * (rating %, grounded %, latency, extraction success) over all time. Every
 * number arrives computed from the server; this screen only renders. Sparse
 * charts, neutral ink, a single accent series (dataviz-validated).
 */

import { useState } from "react";
import Link from "next/link";
import { BarChart3, RefreshCw } from "lucide-react";
import clsx from "clsx";

import { PageScaffold } from "@/components/page-scaffold";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { BarList } from "@/components/viz/bar-list";
import { StatTile } from "@/components/viz/stat-tile";
import { TimeSeriesChart } from "@/components/viz/time-series-chart";
import {
  useAnalyticsQuality,
  useAnalyticsUsage,
  type UsageRange,
} from "@/features/analytics/queries";
import { formatBytes, formatCompact } from "@/lib/format";

/* SegmentedControl hides `label` below sm; the `icon` slot (visible at every
   width) carries the compact form so mobile still shows 7d/30d/90d. */
const RANGES: { value: UsageRange; label: string; icon?: React.ReactNode }[] = [
  { value: "7d", label: "7 days", icon: <span className="sm:hidden">7d</span> },
  { value: "30d", label: "30 days", icon: <span className="sm:hidden">30d</span> },
  { value: "90d", label: "90 days", icon: <span className="sm:hidden">90d</span> },
];

function Panel({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("rounded-lg border border-border bg-card p-4 shadow-e1", className)}>
      <h2 className="mb-3 type-title3 text-text-1">{title}</h2>
      {children}
    </section>
  );
}

function pctLabel(value: number | null): string | null {
  return value == null ? null : `${value}%`;
}

function latencyLabel(ms: number | null): string | null {
  if (ms == null) return null;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function LoadingGrid() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}

function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border-strong bg-card/60 px-6 py-14 text-center">
      <BarChart3 aria-hidden className="size-8 text-text-3" strokeWidth={1.5} />
      <h2 className="mt-3 type-title3 text-text-1">Couldn’t load analytics</h2>
      <p className="mt-1 type-callout text-text-2">The archive is fine — this lens just didn’t load.</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-md bg-accent px-4 type-subhead text-on-accent hover:bg-accent-hover"
      >
        <RefreshCw aria-hidden className="size-4" /> Try again
      </button>
    </div>
  );
}

export default function AnalyticsPage() {
  const [range, setRange] = useState<UsageRange>("30d");
  const usage = useAnalyticsUsage(range);
  const quality = useAnalyticsQuality();

  const rangeLabel = `last ${usage.data?.range_days ?? 30} days`;

  return (
    <PageScaffold
      eyebrow="Insight"
      title="Analytics"
      lede="How your archive is growing and how well answers are grounded."
    >
      {usage.isError ? (
        <ErrorPanel onRetry={() => usage.refetch()} />
      ) : usage.isPending ? (
        <LoadingGrid />
      ) : (
        <div className="flex flex-col gap-8">
          {/* ---- Usage lens ------------------------------------------------ */}
          <section aria-label="Usage">
            {/* one filter row, above everything it scopes */}
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="type-title2 text-text-1">Usage</h2>
              <SegmentedControl
                value={range}
                onChange={setRange}
                segments={RANGES}
                ariaLabel="Analytics range"
              />
            </div>

            {/* refetch keeps the frame: previous render dims, no skeleton flash */}
            <div
              className={clsx(
                "flex flex-col gap-4 transition-opacity",
                usage.isPlaceholderData && "opacity-60",
              )}
            >
              {usage.data.documents === 0 ? (
                <p className="rounded-md border border-border bg-surface-2 px-3 py-2 type-callout text-text-2">
                  No documents yet — upload a few and this page starts filling in.
                </p>
              ) : null}

              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatTile
                  label="Documents"
                  value={formatCompact(usage.data.documents)}
                  hint="in your archive"
                />
                <StatTile
                  label="Queries"
                  value={formatCompact(usage.data.queries)}
                  hint={rangeLabel}
                />
                <StatTile
                  label="Storage"
                  value={formatBytes(usage.data.storage_bytes) ?? "0 B"}
                  hint="of originals stored"
                />
                <StatTile
                  label="Token spend"
                  value={formatCompact(usage.data.token_spend)}
                  hint={`tokens · ${rangeLabel}`}
                />
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Panel title="Archive growth">
                  <TimeSeriesChart
                    points={usage.data.series.documents_over_time.map((p) => ({
                      date: p.date,
                      value: p.cumulative ?? p.count,
                    }))}
                    area
                    valueName="documents"
                    ariaLabel={`Documents in the archive per day, ${rangeLabel}`}
                  />
                </Panel>
                <Panel title="Queries per day">
                  <TimeSeriesChart
                    points={usage.data.series.queries_per_day.map((p) => ({
                      date: p.date,
                      value: p.count,
                    }))}
                    valueName="queries"
                    ariaLabel={`Questions asked per day, ${rangeLabel}`}
                  />
                </Panel>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <Panel title="Top folders">
                  {usage.data.top_classes.length === 0 ? (
                    <p className="type-callout text-text-3">
                      No filed documents yet — folders appear as documents are classified.
                    </p>
                  ) : (
                    <BarList
                      ariaLabel="Documents per folder"
                      items={usage.data.top_classes.map((c) => ({
                        key: c.slug,
                        label: c.name,
                        value: c.count,
                      }))}
                    />
                  )}
                </Panel>
                <Panel title="Most asked documents">
                  {usage.data.most_asked_documents.length === 0 ? (
                    <p className="type-callout text-text-3">
                      Nothing cited yet — ask a question and the sources land here.
                    </p>
                  ) : (
                    <table className="w-full">
                      <thead className="sr-only">
                        <tr>
                          <th scope="col">Document</th>
                          <th scope="col">Times cited</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usage.data.most_asked_documents.map((doc) => (
                          <tr key={doc.document_id} className="border-b border-border last:border-b-0">
                            <td className="py-2 pr-3">
                              <Link
                                href={`/documents/${doc.document_id}`}
                                className="type-callout text-text-1 underline-offset-2 hover:text-accent-text hover:underline"
                              >
                                {doc.title ?? "Untitled document"}
                              </Link>
                            </td>
                            <td className="py-2 text-right type-data tabular-nums text-text-2">
                              {doc.count}×
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Panel>
              </div>
            </div>
          </section>

          {/* ---- Quality lens (all time) ----------------------------------- */}
          <section aria-label="Quality">
            <div className="mb-4 flex items-baseline gap-2">
              <h2 className="type-title2 text-text-1">Quality</h2>
              <span className="type-caption text-text-3">all time</span>
            </div>
            {quality.isError ? (
              <ErrorPanel onRetry={() => quality.refetch()} />
            ) : quality.isPending ? (
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-24" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatTile
                  label="Answers rated up"
                  value={pctLabel(quality.data.answer_rating_pct)}
                  hint={
                    quality.data.ratings_count === 0
                      ? "no ratings yet"
                      : `of ${quality.data.ratings_count} rating${quality.data.ratings_count === 1 ? "" : "s"}`
                  }
                />
                <StatTile
                  label="Grounded answers"
                  value={pctLabel(quality.data.grounded_pct)}
                  hint={
                    quality.data.answers_count === 0
                      ? "no answers yet"
                      : `of ${quality.data.answers_count} answer${quality.data.answers_count === 1 ? "" : "s"}`
                  }
                />
                <StatTile
                  label="Avg retrieval"
                  value={latencyLabel(quality.data.avg_retrieval_ms)}
                  hint="question to answer"
                />
                <StatTile
                  label="Extraction success"
                  value={pctLabel(quality.data.extraction_success_pct)}
                  hint="of processing runs"
                />
              </div>
            )}
          </section>
        </div>
      )}
    </PageScaffold>
  );
}
