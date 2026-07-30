"use client";

/**
 * AskScreen — grounded chat over the archive. A conversation rail (continue any
 * chat) beside a streaming thread. New turns POST to the SSE endpoint; step
 * events feed the live trace and the final `done` event carries the grounded
 * answer + grouped citations. The turn-taking itself lives in `useChatSession`
 * (shared with the archive's docked "Ask this folder" panel); this screen owns
 * the layout, the rail, and the document-scope chrome.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FileText, History, MessageSquareText, X } from "lucide-react";

import { ConversationList } from "@/components/ask/conversation-list";
import { Composer } from "@/components/ask/composer";
import { MessageThread } from "@/components/ask/message-thread";
import { Sheet } from "@/components/ui/sheet";
import { useChatSession } from "@/features/ask/use-chat-session";
import { useDocument } from "@/features/documents/queries";

export function AskScreen({
  conversationId,
  scopedDocumentId,
}: {
  conversationId: string | null;
  scopedDocumentId: string | null;
}) {
  const { turns, streaming, send, activeId, clearSession, historyPending } =
    useChatSession({
      conversationId,
      scope: { documentId: scopedDocumentId },
      // Shallow URL update — a router navigation would remount this screen and
      // drop the streaming thread. The route prop stays null; the hook's
      // activeId carries the truth until the next real navigation.
      onConversationCreated: (id) =>
        window.history.replaceState(
          null,
          "",
          scopedDocumentId ? `/chat/${id}?doc=${scopedDocumentId}` : `/chat/${id}`,
        ),
    });

  const { data: scopedDoc } = useDocument(scopedDocumentId);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Keep the latest turn in view as the thread grows / streams.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

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
            {turns.length === 0 && (!activeId || !historyPending) ? (
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
