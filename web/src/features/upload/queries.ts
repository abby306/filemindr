"use client";

/**
 * Never-wait data hooks. The documents feed is a single global query (mounted by
 * the ProcessingDock, so it lives on every screen) that polls ~1s while any doc
 * is still processing and goes quiet once all are terminal — the same status
 * enum drives both the dock and the upload cards. The review-count feeds the
 * Review nav badge.
 */

import { useQuery } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type { DocumentListResponse, DocumentSummary } from "@/lib/api/types";
import { isProcessing } from "@/features/archive/taxonomy";

const FEED_LIMIT = 50;

export function feedHasProcessing(items: DocumentSummary[] | undefined): boolean {
  return !!items?.some((d) => isProcessing(d.status));
}

/** Recent documents, polled while any are processing. Shared across screens. */
export function useDocumentsFeed() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["documents", account.id, "feed"],
    queryFn: () =>
      request<DocumentListResponse>(`/api/v1/documents?limit=${FEED_LIMIT}`),
    refetchInterval: (query) =>
      feedHasProcessing(query.state.data?.items) ? 1000 : false,
    select: (data) => data.items,
  });
}

/** Count of documents awaiting human review (for the Review nav badge). */
export function useReviewCount(poll: boolean) {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["documents", account.id, "review-count"],
    queryFn: async () => {
      const r = await request<DocumentListResponse>(
        "/api/v1/documents?status=needs_review&limit=200",
      );
      return { count: r.items.length, hasMore: r.next_cursor != null };
    },
    refetchInterval: poll ? 4000 : false,
    staleTime: 15_000,
  });
}
