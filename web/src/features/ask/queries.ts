"use client";

/** Ask data: the conversation rail, replayed history, and answer ratings. Live
 *  turns stream over SSE (see ask-screen), not through these hooks. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type {
  ConversationListItem,
  DocumentListResponse,
  MessageHistoryItem,
} from "@/lib/api/types";

export function useConversations() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["conversations", account.id],
    queryFn: () => request<ConversationListItem[]>("/api/v1/conversations"),
  });
}

export function useDeleteConversation() {
  const { account, request } = useAccount();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) =>
      request(`/api/v1/conversations/${conversationId}`, { method: "DELETE" }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["conversations", account.id] }),
  });
}

export interface MentionableDocument {
  id: string;
  title: string;
  filename: string;
}

/** Lightweight id+title list for @-mentions (first 200 docs, cached). */
export function useMentionableDocuments() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["mentionable-documents", account.id],
    staleTime: 60_000,
    queryFn: async () => {
      const res = await request<DocumentListResponse>("/api/v1/documents?limit=200");
      return res.items.map<MentionableDocument>((d) => ({
        id: d.id,
        title: d.title?.trim() || d.original_filename,
        filename: d.original_filename,
      }));
    },
  });
}

export function useMessages(conversationId: string | null) {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["messages", account.id, conversationId],
    queryFn: () =>
      request<MessageHistoryItem[]>(
        `/api/v1/conversations/${conversationId}/messages`,
      ),
    enabled: !!conversationId,
  });
}

export interface RatingInput {
  messageId: string;
  rating: "up" | "down";
  stars?: number;
  reasons?: string[];
}

export function useRating() {
  const { request } = useAccount();
  return useMutation({
    mutationFn: ({ messageId, rating, stars, reasons }: RatingInput) =>
      request(`/api/v1/messages/${messageId}/rating`, {
        method: "POST",
        json: { rating, stars, reasons },
      }),
  });
}
