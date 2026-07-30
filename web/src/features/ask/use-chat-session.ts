"use client";

/**
 * useChatSession — one streaming chat turn-taker, shared by the full Ask screen
 * and the archive's docked "Ask this folder" panel. It owns the live thread
 * (optimistic user turn + assistant turn patched by SSE events), the
 * conversation id, and the replayed history that shows when there's no live
 * session.
 *
 * `scope` is what the turn is pinned to: a document (the document chat and
 * @-mentions) or a folder (a class slug and its subclasses). The server merges
 * and validates them — a pinned document is the narrower scope and wins.
 */

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAccount } from "@/lib/account/account-context";
import { streamSSE } from "@/lib/api/sse";
import { useMessages } from "@/features/ask/queries";
import type { AssistantTurn, Turn } from "@/features/ask/types";
import type { CitationGroup, MessageHistoryItem } from "@/lib/api/types";

export interface ChatScope {
  /** Pin the answer to one document (the document-scoped chat). */
  documentId?: string | null;
  /** Pin the answer to a folder — the class slug and its subclasses. */
  classSlug?: string | null;
}

function historyToTurns(msgs: MessageHistoryItem[] | undefined): Turn[] {
  return (msgs ?? []).map((m) =>
    m.role === "user"
      ? { role: "user", content: m.content ?? "" }
      : { role: "assistant", status: "done", steps: [], answer: m.content ?? "" },
  );
}

export function useChatSession({
  conversationId,
  scope = {},
  onConversationCreated,
}: {
  /** The conversation from the route, or null for a fresh chat. */
  conversationId: string | null;
  scope?: ChatScope;
  /** Fires once when a send creates a conversation (for a shallow URL update). */
  onConversationCreated?: (id: string) => void;
}) {
  const { account, request } = useAccount();
  const queryClient = useQueryClient();

  const [session, setSession] = useState<Turn[] | null>(null);
  const [streaming, setStreaming] = useState(false);

  // The conversation being shown. Held in state (seeded from the route) so a
  // brand-new chat can adopt its freshly created id WITHOUT a router
  // navigation — a navigation remounts the screen mid-stream and wipes the
  // optimistic thread (the send-from-new-chat vanishing-message bug).
  const [activeId, setActiveId] = useState(conversationId);
  // Real navigation (rail click, back/forward) → adopt the route's id. Render-
  // time reset (React's sanctioned derive-from-props pattern), not an effect.
  const [routeId, setRouteId] = useState(conversationId);
  if (routeId !== conversationId) {
    setRouteId(conversationId);
    setActiveId(conversationId);
    setSession(null);
  }

  const { data: history, isPending } = useMessages(activeId);

  const turns = useMemo(() => session ?? historyToTurns(history), [session, history]);

  const patchAssistant = (fn: (a: AssistantTurn) => AssistantTurn) =>
    setSession((prev) => {
      if (!prev) return prev;
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant") next[next.length - 1] = fn(last);
      return next;
    });

  const send = async (text: string, mentionIds: string[] = []) => {
    let convoId = activeId;
    const isNew = !convoId;
    if (!convoId) {
      const created = await request<{ id: string }>("/api/v1/conversations", {
        method: "POST",
      });
      convoId = created.id;
    }

    const started = Date.now();
    const base = session ?? historyToTurns(history);
    setSession([
      ...base,
      { role: "user", content: text },
      { role: "assistant", status: "streaming", steps: [], startedAt: started },
    ]);
    setStreaming(true);
    if (isNew) {
      setActiveId(convoId);
      onConversationCreated?.(convoId);
      queryClient.invalidateQueries({ queryKey: ["conversations", account.id] });
    }

    try {
      await streamSSE(`/api/v1/conversations/${convoId}/messages/stream`, {
        accountId: account.id,
        json: {
          content: text,
          // A pinned document (URL scope or @-mention) is the narrowest scope;
          // a folder scope pins retrieval to a class and its subclasses.
          ...(scope.documentId
            ? { scope: "document", document_id: scope.documentId }
            : scope.classSlug
              ? { scope: "folder", class_slug: scope.classSlug }
              : {}),
          ...(mentionIds.length > 0 ? { document_ids: mentionIds } : {}),
        },
        onEvent: (type, data) => {
          if (type === "done") {
            patchAssistant((a) => ({
              ...a,
              status: "done",
              answer: (data.answer as string) ?? "",
              supported: data.supported as boolean,
              escalated: data.escalated as boolean,
              model: data.model as string,
              citationGroups: (data.citation_groups as CitationGroup[]) ?? [],
              messageId: data.message_id as string,
              elapsedMs: Date.now() - started,
            }));
          } else if (type === "error") {
            // The backend saved the question; only the answer failed.
            patchAssistant((a) => ({ ...a, status: "error" }));
          } else if (type !== "conversation") {
            patchAssistant((a) => ({ ...a, steps: [...a.steps, { type, data }] }));
          }
        },
      });
    } catch {
      patchAssistant((a) => ({ ...a, status: "error" }));
    } finally {
      setStreaming(false);
      queryClient.invalidateQueries({ queryKey: ["conversations", account.id] });
      queryClient.invalidateQueries({ queryKey: ["messages", account.id, convoId] });
    }
  };

  return {
    turns,
    streaming,
    send,
    activeId,
    /** Drop the live thread so replayed history shows instead. */
    clearSession: () => setSession(null),
    historyPending: isPending,
  };
}
