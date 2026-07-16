"use client";

/** Ask data: the conversation rail, replayed history, and answer ratings. Live
 *  turns stream over SSE (see ask-screen), not through these hooks. */

import { useMutation, useQuery } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import type {
  ConversationListItem,
  MessageHistoryItem,
} from "@/lib/api/types";

export function useConversations() {
  const { account, request } = useAccount();
  return useQuery({
    queryKey: ["conversations", account.id],
    queryFn: () => request<ConversationListItem[]>("/api/v1/conversations"),
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
