"use client";

/**
 * Checkout stand-in — the mock "provider-hosted" payment page. It plays the
 * role Stripe Checkout will take over: `POST /billing/checkout` sent the user
 * here with a session id; "Complete purchase" confirms the session (the
 * webhook stand-in) and returns to /billing. Clearly badged as test mode —
 * no card fields, nothing real is charged. When Stripe lands, `checkout_url`
 * points at Stripe instead and this page is deleted.
 */

import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Lock } from "lucide-react";

import { PageScaffold } from "@/components/page-scaffold";
import { Skeleton } from "@/components/ui/skeleton";
import { useBillingPlans, useCompleteCheckout } from "@/features/billing/queries";
import { formatMoney } from "@/lib/format";

function CheckoutBody() {
  const router = useRouter();
  const params = useSearchParams();
  const sessionId = params.get("session_id");
  const planSlug = params.get("plan");
  const plans = useBillingPlans();
  const complete = useCompleteCheckout();

  const plan = plans.data?.find((p) => p.slug === planSlug);

  if (!sessionId || !planSlug) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-center shadow-e1">
        <p className="type-body text-text-1">This checkout link is incomplete.</p>
        <Link
          href="/billing"
          className="mt-3 inline-flex items-center gap-1.5 type-subhead text-accent hover:text-accent-hover"
        >
          <ArrowLeft aria-hidden className="size-4" /> Back to billing
        </Link>
      </div>
    );
  }

  const confirm = async () => {
    await complete.mutateAsync(sessionId);
    router.replace(`/billing?upgraded=${encodeURIComponent(plan?.name ?? planSlug)}`);
  };

  return (
    <div className="mx-auto w-full max-w-md">
      <div className="rounded-lg border border-border bg-card p-6 shadow-e2">
        <div className="mb-4 flex items-center justify-between">
          <span className="flex items-center gap-1.5 type-subhead text-text-2">
            <Lock aria-hidden className="size-4" /> Secure checkout
          </span>
          <span className="rounded-full bg-hl-wash px-2.5 py-0.5 type-caption uppercase text-hl-strong">
            Test mode
          </span>
        </div>

        {plans.isPending ? (
          <Skeleton className="h-20" />
        ) : (
          <dl className="flex flex-col gap-2 border-b border-border pb-4">
            <div className="flex justify-between">
              <dt className="type-body text-text-2">Plan</dt>
              <dd className="type-body text-text-1">{plan?.name ?? planSlug}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="type-body text-text-2">Billed</dt>
              <dd className="type-body text-text-1">Monthly</dd>
            </div>
            <div className="flex justify-between">
              <dt className="type-headline text-text-1">Due today</dt>
              <dd className="type-headline tabular-nums text-text-1">
                {plan ? formatMoney(plan.price_cents, plan.currency) : "—"}
              </dd>
            </div>
          </dl>
        )}

        <p className="mt-3 type-caption text-text-3">
          Test mode: no payment details are collected and nothing is charged.
          Completing activates the plan for this account.
        </p>

        <button
          type="button"
          onClick={confirm}
          disabled={complete.isPending || plans.isPending}
          className="mt-4 inline-flex min-h-11 w-full items-center justify-center rounded-md bg-accent px-4 type-subhead text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {complete.isPending ? "Completing…" : "Complete purchase"}
        </button>
        {complete.isError ? (
          <p role="alert" className="mt-2 type-callout text-danger">
            Couldn’t complete this checkout — go back and try again.
          </p>
        ) : null}
        <Link
          href="/billing"
          className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-1.5 rounded-md type-subhead text-text-2 hover:text-text-1"
        >
          <ArrowLeft aria-hidden className="size-4" /> Cancel and go back
        </Link>
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <PageScaffold eyebrow="Account" title="Checkout">
      <Suspense fallback={<Skeleton className="mx-auto h-80 w-full max-w-md" />}>
        <CheckoutBody />
      </Suspense>
    </PageScaffold>
  );
}
