"use client";

/** Document detail data. Shares the ["document", account, id] cache key with the
 *  review deck, so a doc fetched in one place is warm in the other. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type { DocumentCard, DocumentSummary, FactRegion } from "@/lib/api/types";

export function useDocument(documentId: string | null) {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["document", account.id, documentId],
    queryFn: () => request<DocumentCard>(`/api/v1/documents/${documentId}`),
    enabled: !!documentId,
  });
}

/** Re-drive a failed/stalled document through the pipeline. The response is
 *  the reset document (failed → received), so lists flip back to the live
 *  pipeline immediately and the never-wait polling resumes. */
export function useReprocess() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      request<DocumentSummary>(`/api/v1/documents/${documentId}/reprocess`, {
        method: "POST",
      }),
    onSuccess: (_data, documentId) => {
      qc.invalidateQueries({ queryKey: ["documents", account.id] });
      qc.invalidateQueries({ queryKey: ["document", account.id, documentId] });
    },
  });
}

/** Delete a document (its facts, labels, and stored file go with it). */
export function useDeleteDocument() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      request(`/api/v1/documents/${documentId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", account.id] });
      qc.invalidateQueries({ queryKey: ["classes", account.id] });
      qc.invalidateQueries({ queryKey: ["mentionable-documents", account.id] });
    },
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
