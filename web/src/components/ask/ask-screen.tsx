"use client";

/**
 * AskScreen — grounded chat over the archive. A conversation rail (continue any
 * chat) beside a streaming thread. New turns POST to the SSE endpoint; step
 * events feed the live trace and the final `done` event carries the grounded
 * answer + grouped citations. The live thread is held in `session`; navigating
 * the rail clears it so replayed history shows instead.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, History, MessageSquareText, X } from "lucide-react";

import { ConversationList } from "@/components/ask/conversation-list";
import { Composer } from "@/components/ask/composer";
import { MessageThread } from "@/components/ask/message-thread";
import { Sheet } from "@/components/ui/sheet";
import { useAccount } from "@/lib/account/account-context";
import { streamSSE } from "@/lib/api/sse";
import { useMessages } from "@/features/ask/queries";
import { useDocument } from "@/features/documents/queries";
import type { AssistantTurn, Turn } from "@/features/ask/types";
import type { CitationGroup, MessageHistoryItem } from "@/lib/api/types";

function historyToTurns(msgs: MessageHistoryItem[] | undefined): Turn[] {
  return (msgs ?? []).map((m) =>
    m.role === "user"
      ? { role: "user", content: m.content ?? "" }
      : { role: "assistant", status: "done", steps: [], answer: m.content ?? "" },
  );
}

export function AskScreen({
  conversationId,
  scopedDocumentId,
}: {
  conversationId: string | null;
  scopedDocumentId: string | null;
}) {
  const { account, request } = useAccount();
  const queryClient = useQueryClient();

  const [session, setSession] = useState<Turn[] | null>(null);
  const [streaming, setStreaming] = useState(false);

  // The conversation being shown. Held in state (seeded from the route) so a
  // brand-new chat can adopt its freshly created id WITHOUT a router
  // navigation — a navigation remounts this component mid-stream and wipes the
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
  const { data: scopedDoc } = useDocument(scopedDocumentId);
  const bottomRef = useRef<HTMLDivElement>(null);

  const turns = useMemo(
    () => session ?? historyToTurns(history),
    [session, history],
  );

  // Keep the latest turn in view as the thread grows / streams.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const patchAssistant = (fn: (a: AssistantTurn) => AssistantTurn) =>
    setSession((prev) => {
      if (!prev) return prev;
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant") next[next.length - 1] = fn(last);
      return next;
    });

  const send = async (text: string) => {
    let convoId = activeId;
    const isNew = !convoId;
    if (!convoId) {
      const created = await request<{ id: string }>("/api/v1/conversations", {
        method: "POST",
      });
      convoId = created.id;
    }

    const base = session ?? historyToTurns(history);
    setSession([
      ...base,
      { role: "user", content: text },
      { role: "assistant", status: "streaming", steps: [] },
    ]);
    setStreaming(true);
    if (isNew) {
      // Shallow URL update — a router navigation would remount this screen
      // and drop the streaming thread. The route prop stays null; activeId
      // carries the truth until the next real navigation.
      setActiveId(convoId);
      window.history.replaceState(
        null,
        "",
        scopedDocumentId ? `/chat/${convoId}?doc=${scopedDocumentId}` : `/chat/${convoId}`,
      );
      queryClient.invalidateQueries({ queryKey: ["conversations", account.id] });
    }

    const started = Date.now();
    try {
      await streamSSE(`/api/v1/conversations/${convoId}/messages/stream`, {
        accountId: account.id,
        json: scopedDocumentId
          ? { content: text, scope: "document", document_id: scopedDocumentId }
          : { content: text },
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

  const clearSession = () => setSession(null);
  const [railOpen, setRailOpen] = useState(false);

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 overflow-y-auto border-r border-border bg-surface xl:block">
        <ConversationList activeId={activeId} onNavigate={clearSession} />
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col px-4 py-6 sm:px-6">
          {/* Narrow screens: the conversation rail lives in a bottom sheet. */}
          <button
            type="button"
            onClick={() => setRailOpen(true)}
            className="mb-4 flex min-h-11 w-fit items-center gap-2 rounded-lg border border-border bg-surface px-3.5 type-subhead text-text-2 transition-colors hover:bg-surface-2 hover:text-text-1 xl:hidden"
          >
            <History aria-hidden className="size-4" />
            Chats
          </button>
          <Sheet open={railOpen} onClose={() => setRailOpen(false)} title="Chats">
            <ConversationList
              activeId={activeId}
              onNavigate={() => {
                setRailOpen(false);
                clearSession();
              }}
            />
          </Sheet>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {turns.length === 0 && (!activeId || !isPending) ? (
              <EmptyAsk />
            ) : (
              <>
                <MessageThread
                  turns={turns}
                  scopeLabel={
                    scopedDocumentId
                      ? scopedDoc?.title?.trim() || "this document"
                      : undefined
                  }
                />
                <div ref={bottomRef} />
              </>
            )}
          </div>

          <div className="pt-4">
            {scopedDocumentId ? (
              <div className="mb-2 flex w-fit items-center gap-2 rounded-full border border-accent-300 bg-accent-50 py-1 pl-2.5 pr-1.5">
                <FileText aria-hidden className="size-3.5 text-accent" />
                <span className="max-w-[16rem] truncate type-caption text-accent">
                  Asking about {scopedDoc?.title?.trim() || "this document"}
                </span>
                <Link
                  href="/chat"
                  aria-label="Ask the whole archive instead"
                  className="flex size-5 items-center justify-center rounded-full text-accent hover:bg-accent-100"
                >
                  <X aria-hidden className="size-3.5" />
                </Link>
              </div>
            ) : null}
            <Composer onSend={send} disabled={streaming} />
            <p className="mt-1.5 text-center type-caption text-text-3">
              {scopedDocumentId
                ? "Scoped to one document — answers cite its pages."
                : "Answers are grounded in your documents, with citations."}
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

function EmptyAsk() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <span className="flex size-12 items-center justify-center rounded-lg bg-surface-2 text-accent">
        <MessageSquareText aria-hidden className="size-6" strokeWidth={1.5} />
      </span>
      <h1 className="mt-4 type-title1 text-text-1">Ask your archive</h1>
      <p className="mt-1 max-w-sm type-body text-text-2">
        Ask anything about your documents — totals, dates, terms, who signed what.
        Every answer cites the source.
      </p>
    </div>
  );
}
