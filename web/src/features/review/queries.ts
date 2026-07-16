"use client";

/**
 * Review-deck data. The queue is the `needs_review` documents; the current
 * document's card supplies its summary + candidate classes. Confirming assigns
 * classes server-side (`POST /documents/{id}/classes`, `assigned_by=user`),
 * which clears the review flag and advances the doc to `indexed`.
 *
 * The queue query has its own key so confirming (which invalidates the shared
 * `["documents", account]` queries — feed, review-count, archive) does not
 * yank the deck out from under the user mid-review.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type { DocumentCard, DocumentListResponse } from "@/lib/api/types";

export interface NewClassInput {
  name: string;
  description?: string;
  parent_id?: string;
}

export interface AssignInput {
  documentId: string;
  classIds?: string[];
  newClass?: NewClassInput;
}

export function useReviewQueue() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["review-queue", account.id],
    queryFn: () =>
      request<DocumentListResponse>(
        "/api/v1/documents?status=needs_review&limit=200",
      ),
    select: (data) => data.items,
    staleTime: 60_000,
  });
}

export function useDocumentCard(documentId: string | undefined) {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["document", account.id, documentId],
    queryFn: () => request<DocumentCard>(`/api/v1/documents/${documentId}`),
    enabled: !!documentId,
  });
}

export function useAssignClasses() {
  const { account, request } = useAccount();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ documentId, classIds, newClass }: AssignInput) =>
      request<DocumentCard>(`/api/v1/documents/${documentId}/classes`, {
        method: "POST",
        json: {
          class_ids: classIds ?? [],
          new_class: newClass ?? null,
        },
      }),
    onSuccess: () => {
      // Refresh everything derived from documents/classes, except the deck's own
      // queue (kept stable so the user finishes the batch they started).
      queryClient.invalidateQueries({ queryKey: ["documents", account.id] });
      queryClient.invalidateQueries({ queryKey: ["classes", account.id] });
    },
  });
}
