"use client";

/** Document detail data. Shares the ["document", account, id] cache key with the
 *  review deck, so a doc fetched in one place is warm in the other. */

import { useQuery } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type { DocumentCard, FactRegion } from "@/lib/api/types";

export function useDocument(documentId: string | null) {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["document", account.id, documentId],
    queryFn: () => request<DocumentCard>(`/api/v1/documents/${documentId}`),
    enabled: !!documentId,
  });
}

/** Atomic facts with normalized bboxes — for click-to-source SourceGlow. */
export function useDocumentFacts(documentId: string, enabled = true) {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["document-facts", account.id, documentId],
    queryFn: () => request<FactRegion[]>(`/api/v1/documents/${documentId}/facts`),
    enabled,
    staleTime: 5 * 60_000,
  });
}
