"use client";

/**
 * Billing — the current plan with usage meters (status ramp amber→red near a
 * limit), the pricing cards, and invoices (FRONTEND.md). All numbers come from
 * `GET /billing/subscription` — the same figures quota enforcement reads, so
 * what the meters show and what a 402 enforces can never disagree. Upgrading
 * follows the provider-hosted checkout shape: we navigate to `checkout_url`
 * (today the in-app mock page; with Stripe, its hosted page — see
 * `app/services/billing.py`).
 */

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Check, CreditCard, RefreshCw } from "lucide-react";
import clsx from "clsx";

import { PageScaffold } from "@/components/page-scaffold";
import { Skeleton } from "@/components/ui/skeleton";
import { UsageMeter } from "@/components/viz/usage-meter";
import {
  useBillingPlans,
  useInvoices,
  useStartCheckout,
  useSubscription,
} from "@/features/billing/queries";
import { formatBytes, formatCompact, formatDate, formatMoney } from "@/lib/format";
import type { Plan } from "@/lib/api/types";

const FEATURE_LABELS: Record<string, string> = {
  priority_ocr: "Priority OCR",
  shared_accounts: "Shared company accounts",
  audit: "Audit trail",
};

const GB = 1024 ** 3;

function limitLine(label: string, value: string): { label: string; value: string } {
  return { label, value };
}

function planLines(plan: Plan): { label: string; value: string }[] {
  const l = plan.limits;
  return [
    limitLine("Documents", l.documents == null ? "Unlimited" : formatCompact(l.documents)),
    limitLine("Storage", l.storage_gb == null ? "Unlimited" : `${l.storage_gb} GB`),
    limitLine(
      "Queries / month",
      l.queries_per_month == null ? "Unlimited" : formatCompact(l.queries_per_month),
    ),
  ];
}

/** Reads ?upgraded= (set by the checkout page) — isolated for Suspense. */
function UpgradedBanner() {
  const params = useSearchParams();
  const upgraded = params.get("upgraded");
  const [dismissed, setDismissed] = useState(false);
  if (!upgraded || dismissed) return null;
  return (
    <div
      role="status"
      className="mb-4 flex items-center justify-between gap-3 rounded-md border border-ok/30 bg-ok/10 px-3 py-2"
    >
      <span className="flex items-center gap-2 type-callout text-text-1">
        <Check aria-hidden className="size-4 text-ok" />
        You’re on the {upgraded} plan now.
      </span>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="type-caption text-text-3 hover:text-text-1"
      >
        Dismiss
      </button>
    </div>
  );
}

function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border-strong bg-card/60 px-6 py-14 text-center">
      <CreditCard aria-hidden className="size-8 text-text-3" strokeWidth={1.5} />
      <h2 className="mt-3 type-title3 text-text-1">Couldn’t load billing</h2>
      <p className="mt-1 type-callout text-text-2">Your plan is unchanged — this page just didn’t load.</p>
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

export default function BillingPage() {
  const router = useRouter();
  const subscription = useSubscription();
  const plans = useBillingPlans();
  const invoices = useInvoices();
  const checkout = useStartCheckout();
  const [pendingPlan, setPendingPlan] = useState<string | null>(null);

  const startUpgrade = async (slug: string) => {
    setPendingPlan(slug);
    try {
      const session = await checkout.mutateAsync(slug);
      router.push(session.checkout_url);
    } catch {
      setPendingPlan(null);
    }
  };

  return (
    <PageScaffold
      eyebrow="Account"
      title="Billing"
      lede="Your plan, usage against limits, and invoices."
    >
      <Suspense fallback={null}>
        <UpgradedBanner />
      </Suspense>

      {subscription.isError ? (
        <ErrorPanel onRetry={() => subscription.refetch()} />
      ) : subscription.isPending ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-56" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="flex flex-col gap-8">
          {/* ---- current plan + meters ------------------------------------- */}
          <section
            aria-label="Current plan"
            className="rounded-lg border border-border bg-card p-5 shadow-e1"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <p className="type-subhead text-text-2">Current plan</p>
                <h2 className="type-title1 text-text-1">{subscription.data.plan.name}</h2>
              </div>
              <div className="text-right">
                <p className="type-title3 text-text-1">
                  {subscription.data.plan.price_cents === 0
                    ? "Free"
                    : `${formatMoney(subscription.data.plan.price_cents, subscription.data.plan.currency)} / mo`}
                </p>
                {subscription.data.period_end ? (
                  <p className="type-caption text-text-3">
                    renews {formatDate(subscription.data.period_end)}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-4">
              <UsageMeter
                label="Documents"
                used={subscription.data.usage.documents}
                limit={subscription.data.limits.documents}
                formatValue={formatCompact}
              />
              <UsageMeter
                label="Queries this month"
                used={subscription.data.usage.queries}
                limit={subscription.data.limits.queries_per_month}
                formatValue={formatCompact}
              />
              <UsageMeter
                label="Storage"
                used={subscription.data.usage.storage_bytes}
                limit={
                  subscription.data.limits.storage_gb == null
                    ? null
                    : subscription.data.limits.storage_gb * GB
                }
                formatValue={(n) => formatBytes(n) ?? "0 B"}
              />
            </div>
          </section>

          {/* ---- pricing cards --------------------------------------------- */}
          <section aria-label="Plans">
            <h2 className="mb-4 type-title2 text-text-1">Plans</h2>
            {plans.isPending ? (
              <div className="grid gap-4 sm:grid-cols-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-64" />
                ))}
              </div>
            ) : plans.isError ? (
              <ErrorPanel onRetry={() => plans.refetch()} />
            ) : (
              <div className="grid gap-4 sm:grid-cols-3">
                {plans.data.map((plan) => {
                  const current = plan.slug === subscription.data.plan.slug;
                  return (
                    <div
                      key={plan.slug}
                      className={clsx(
                        "flex flex-col rounded-lg border bg-card p-4 shadow-e1",
                        current ? "border-accent" : "border-border",
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <h3 className="type-title3 text-text-1">{plan.name}</h3>
                        {current ? (
                          <span className="rounded-full bg-accent-50 px-2 py-0.5 type-caption text-accent-text">
                            Current
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-[22px] font-semibold leading-7 text-text-1">
                        {plan.price_cents === 0
                          ? "Free"
                          : `${formatMoney(plan.price_cents, plan.currency)} `}
                        {plan.price_cents !== 0 ? (
                          <span className="type-caption font-normal text-text-3">/ month</span>
                        ) : null}
                      </p>
                      <dl className="mt-3 flex flex-col gap-1.5">
                        {planLines(plan).map((line) => (
                          <div key={line.label} className="flex justify-between gap-2">
                            <dt className="type-callout text-text-2">{line.label}</dt>
                            <dd className="type-data tabular-nums text-text-1">{line.value}</dd>
                          </div>
                        ))}
                      </dl>
                      {(plan.limits.features ?? []).length > 0 ? (
                        <ul className="mt-2 flex flex-col gap-1">
                          {(plan.limits.features ?? []).map((f) => (
                            <li key={f} className="flex items-center gap-1.5 type-callout text-text-2">
                              <Check aria-hidden className="size-3.5 text-ok" />
                              {FEATURE_LABELS[f] ?? f}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="mt-auto pt-4">
                        {current ? (
                          <p className="type-caption text-text-3">This is your plan.</p>
                        ) : plan.price_cents === 0 ? (
                          <p className="type-caption text-text-3">The starting point.</p>
                        ) : (
                          <button
                            type="button"
                            disabled={pendingPlan !== null}
                            onClick={() => startUpgrade(plan.slug)}
                            className="inline-flex min-h-11 w-full items-center justify-center rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
                          >
                            {pendingPlan === plan.slug
                              ? "Opening checkout…"
                              : `Upgrade to ${plan.name}`}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            {checkout.isError ? (
              <p role="alert" className="mt-2 type-callout text-danger">
                Couldn’t start checkout — try again.
              </p>
            ) : null}
          </section>

          {/* ---- invoices ---------------------------------------------------- */}
          <section aria-label="Invoices">
            <h2 className="mb-4 type-title2 text-text-1">Invoices</h2>
            {invoices.isPending ? (
              <Skeleton className="h-24" />
            ) : invoices.isError ? (
              <ErrorPanel onRetry={() => invoices.refetch()} />
            ) : invoices.data.items.length === 0 ? (
              <p className="rounded-md border border-border bg-surface-2 px-3 py-2 type-callout text-text-2">
                No invoices yet — they appear here after your first paid month.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-e1">
                <table className="w-full min-w-[28rem]">
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th scope="col" className="px-4 py-2.5 type-subhead text-text-2">Date</th>
                      <th scope="col" className="px-4 py-2.5 type-subhead text-text-2">Period</th>
                      <th scope="col" className="px-4 py-2.5 text-right type-subhead text-text-2">Amount</th>
                      <th scope="col" className="px-4 py-2.5 type-subhead text-text-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.data.items.map((invoice) => (
                      <tr key={invoice.id} className="border-b border-border last:border-b-0">
                        <td className="px-4 py-2.5 type-callout text-text-1">
                          {formatDate(invoice.created_at)}
                        </td>
                        <td className="px-4 py-2.5 type-data text-text-2">{invoice.period ?? "—"}</td>
                        <td className="px-4 py-2.5 text-right type-data tabular-nums text-text-1">
                          {formatMoney(invoice.amount_cents, invoice.currency)}
                        </td>
                        <td className="px-4 py-2.5">
                          <span
                            className={clsx(
                              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 type-caption",
                              invoice.status === "paid"
                                ? "bg-ok/10 text-ok"
                                : "bg-surface-2 text-text-2",
                            )}
                          >
                            {invoice.status === "paid" ? (
                              <Check aria-hidden className="size-3" />
                            ) : null}
                            {invoice.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </PageScaffold>
  );
}
