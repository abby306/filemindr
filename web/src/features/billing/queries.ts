"use client";

/**
 * Billing data hooks over the account-bound request seam. Checkout follows the
 * provider-hosted shape: POST /billing/checkout returns a `checkout_url` the
 * client navigates to (today the in-app mock page; with Stripe, its hosted
 * page), and completion invalidates the subscription so meters update.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type {
  CheckoutSession,
  InvoiceList,
  Plan,
  Subscription,
} from "@/lib/api/types";

export function useBillingPlans() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["billing-plans", account.id],
    queryFn: () => request<Plan[]>("/api/v1/billing/plans"),
  });
}

export function useSubscription() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["billing-subscription", account.id],
    queryFn: () => request<Subscription>("/api/v1/billing/subscription"),
  });
}

export function useInvoices() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["billing-invoices", account.id],
    queryFn: () => request<InvoiceList>("/api/v1/billing/invoices"),
  });
}

/** Start a checkout; the caller navigates to `checkout_url`. */
export function useStartCheckout() {
  const { request } = useAccount();
  return useMutation({
    mutationFn: (planSlug: string) =>
      request<CheckoutSession>("/api/v1/billing/checkout", {
        method: "POST",
        json: { plan_slug: planSlug },
      }),
  });
}

/** Confirm a mock checkout session (the stand-in for the provider webhook). */
export function useCompleteCheckout() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      request<Subscription>("/api/v1/billing/checkout/complete", {
        method: "POST",
        json: { session_id: sessionId },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billing-subscription", account.id] });
      qc.invalidateQueries({ queryKey: ["billing-invoices", account.id] });
    },
  });
}
