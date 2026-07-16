"use client";

/**
 * Analytics data hooks. The server derives every number (thin-client contract);
 * these only fetch. Range switches keep the previous render on screen at
 * reduced emphasis instead of flashing a skeleton (dataviz: refetch keeps the
 * frame).
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type { AnalyticsQuality, AnalyticsUsage } from "@/lib/api/types";

export type UsageRange = "7d" | "30d" | "90d";

export function useAnalyticsUsage(range: UsageRange) {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["analytics-usage", account.id, range],
    queryFn: () =>
      request<AnalyticsUsage>(`/api/v1/analytics/usage?range=${range}`),
    placeholderData: keepPreviousData,
  });
}

export function useAnalyticsQuality() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["analytics-quality", account.id],
    queryFn: () => request<AnalyticsQuality>("/api/v1/analytics/quality"),
  });
}
